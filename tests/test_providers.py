"""Provider selection, Streamlit secrets and fallback. All API calls are mocked; no key or network needed."""
# Tests for the model switch: provider selection, secrets, fallback and the sidebar. All API calls
# are mocked.
import sys
import types
from pathlib import Path

import pytest

from data360 import answer, config
from data360.prompting import build_prompt

ROOT = Path(__file__).resolve().parents[1]
# Fake keys: if one ever appears in the UI or a message, a test fails.
FAKE_OPENAI = "sk-test-openai-1234567890abcdef"
FAKE_ANTHROPIC = "sk-ant-test-0987654321fedcba"


@pytest.fixture(autouse=True)
# Start every test with no keys and local settings ignored.
def clean_env(monkeypatch):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DATA360_LLM_PROVIDER", "DATA360_LLM_MODEL",
              "DATA360_OPENAI_MODEL", "DATA360_ANTHROPIC_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DATA360_SKIP_LOCAL_CONFIG", "1")


# ---------- selection ----------

# No keys: only the offline template is offered.
def test_offline_when_no_keys():
    assert answer.available_providers() == ["offline"]
    assert answer.default_provider() == "offline"
    assert answer.provider() == ""


# Both keys: OpenAI is the default, Anthropic is also offered.
def test_openai_preferred_when_both_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_OPENAI)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_ANTHROPIC)
    assert answer.available_providers() == ["offline", "openai", "anthropic"]
    assert answer.default_provider() == "openai"


# Only the Anthropic key: Anthropic becomes the default.
def test_anthropic_when_only_its_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_ANTHROPIC)
    assert answer.available_providers() == ["offline", "anthropic"]
    assert answer.default_provider() == "anthropic"
    assert answer.default_model("anthropic") == "claude-haiku-5-5"


# Environment settings can force a provider or a model.
def test_explicit_provider_and_model_overrides(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_OPENAI)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_ANTHROPIC)
    monkeypatch.setenv("DATA360_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("DATA360_OPENAI_MODEL", "gpt-x")
    assert answer.default_provider() == "anthropic"
    assert answer.default_model("openai") == "gpt-x"
    monkeypatch.setenv("DATA360_LLM_PROVIDER", "offline")
    assert answer.default_provider() == "offline"


# Asking for a provider without its key falls back to offline.
def test_unkeyed_provider_request_is_ignored(monkeypatch):
    monkeypatch.setenv("DATA360_LLM_PROVIDER", "openai")  # asked for, but no key
    assert answer.default_provider() == "offline"


# ---------- secrets ----------

# Keys in Streamlit secrets (as on Streamlit Cloud) are found.
def test_reads_streamlit_secrets(monkeypatch):
    monkeypatch.delenv("DATA360_SKIP_LOCAL_CONFIG")
    import streamlit as st

    class FakeSecrets(dict):
        def load_if_toml_exists(self):
            return True

    monkeypatch.setattr(st, "secrets", FakeSecrets(ANTHROPIC_API_KEY=FAKE_ANTHROPIC))
    assert config.setting("ANTHROPIC_API_KEY") == FAKE_ANTHROPIC
    assert "anthropic" in answer.available_providers()


# A missing or broken secrets file never crashes the app.
def test_missing_or_broken_secrets_never_crash(monkeypatch):
    monkeypatch.delenv("DATA360_SKIP_LOCAL_CONFIG")
    import streamlit as st

    class Broken:
        def load_if_toml_exists(self):
            raise RuntimeError("malformed secrets.toml")

    monkeypatch.setattr(st, "secrets", Broken())
    assert config.setting("OPENAI_API_KEY", "fallback") == "fallback"

    class Missing:
        def load_if_toml_exists(self):
            return False

        def get(self, name):  # must not be reached
            raise AssertionError("read secrets without a file")

    monkeypatch.setattr(st, "secrets", Missing())
    assert config.setting("OPENAI_API_KEY") == ""


# The real st.secrets with no file just returns nothing.
def test_real_streamlit_secrets_without_file(monkeypatch, tmp_path):
    monkeypatch.delenv("DATA360_SKIP_LOCAL_CONFIG")
    monkeypatch.chdir(tmp_path)  # no .streamlit/secrets.toml here
    assert isinstance(config.setting("SOME_UNSET_NAME_12345"), str)


# ---------- calls (mocked SDKs) ----------

# Stand-in for the openai package that records what was sent and returns a canned reply.
def _fake_openai(calls, text="OpenAI says hi", fail=None):
    mod = types.ModuleType("openai")

    class Completions:
        def create(self, **kw):
            calls.append(("openai", kw))
            if fail:
                raise fail
            msg = types.SimpleNamespace(content=text)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    class OpenAI:
        def __init__(self, api_key=None, **kw):
            assert api_key == FAKE_OPENAI
            self.chat = types.SimpleNamespace(completions=Completions())

    mod.OpenAI = OpenAI
    return mod


# Stand-in for the anthropic package; it also returns a thinking block to check that only text is
# kept.
def _fake_anthropic(calls, text="Claude says hi", fail=None):
    mod = types.ModuleType("anthropic")

    class Messages:
        def create(self, **kw):
            calls.append(("anthropic", kw))
            if fail:
                raise fail
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="thinking", thinking="..."),
                                                  types.SimpleNamespace(type="text", text=text)])

    class Anthropic:
        def __init__(self, api_key=None, **kw):
            assert api_key == FAKE_ANTHROPIC
            self.messages = Messages()

    mod.Anthropic = Anthropic
    return mod


# Pulls (system, user) out of whatever was sent to an SDK, so payloads from different providers can be
# compared directly.
def _payload(name, kw):
    if name == "openai":
        system = "".join(m["content"] for m in kw["messages"] if m["role"] == "system")
        user = "".join(m["content"] for m in kw["messages"] if m["role"] == "user")
        return system, user
    return kw.get("system", ""), kw["messages"][0]["content"]


@pytest.fixture()
def both_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_OPENAI)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_ANTHROPIC)


# The key promise: the exact same prompt goes to every provider, and replying never changes memory.
def test_same_prompt_and_memory_for_every_provider(mm, monkeypatch, both_keys):
    from data360 import datasets

    events, _ = datasets.load_dataset("canonical")
    mm.load_events(events)
    q = "Which R environment do I use now?"
    ctx = mm.context("syn_L01", q)
    prompt = build_prompt(q, ctx, [], memory_on=True, budget=mm.policy.k)
    calls = []
    monkeypatch.setitem(sys.modules, "openai", _fake_openai(calls))
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(calls))
    a = answer.reply(q, prompt, ctx, [], True, provider_name="openai")
    b = answer.reply(q, prompt, ctx, [], True, provider_name="anthropic", model="claude-sonnet-5-5")
    c = answer.reply(q, prompt, ctx, [], True, provider_name="offline")
    assert (a.provider, a.model, a.text) == ("openai", "gpt-6-luna", "OpenAI says hi")
    assert (b.provider, b.model, b.text) == ("anthropic", "claude-sonnet-5-5", "Claude says hi")
    assert c.provider == "offline" and "e009" in c.text
    sent = [_payload(name, kw) for name, kw in calls]
    # identical system text and identical user text regardless of provider
    assert sent == [(prompt.system, prompt.user), (prompt.system, prompt.user)]
    assert str(prompt) == f"SYSTEM: {prompt.system}\n\n{prompt.user}"
    assert calls[1][1]["model"] == "claude-sonnet-5-5"
    assert "e009" in prompt and not a.warning and not b.warning
    assert a.label == "OpenAI gpt-6-luna" and b.label == "Anthropic claude-sonnet-5-5"
    # nothing about the store changed by replying
    after = mm.context("syn_L01", q)
    assert build_prompt(q, after, [], memory_on=True, budget=mm.policy.k) == prompt


@pytest.mark.parametrize("prov", ["openai", "anthropic"])
# A rejected key falls back to the template with a warning that never contains the key.
def test_api_failure_falls_back_without_leaking_key(monkeypatch, both_keys, prov):
    class AuthenticationError(Exception):
        status_code = 401

    err = AuthenticationError(f"Incorrect API key provided: {FAKE_OPENAI} {FAKE_ANTHROPIC}")
    calls = []
    monkeypatch.setitem(sys.modules, "openai", _fake_openai(calls, fail=err))
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(calls, fail=err))
    r = answer.reply("Why do I keep getting could not find function %>%?", "PROMPT", None, [], False, provider_name=prov)
    assert r.provider == "offline" and r.requested == prov
    assert r.warning and "HTTP 401" in r.warning and "offline template" in r.warning
    assert FAKE_OPENAI not in r.warning + r.text and FAKE_ANTHROPIC not in r.warning + r.text


# A missing SDK package falls back instead of crashing.
def test_missing_sdk_falls_back(monkeypatch, both_keys):
    monkeypatch.setitem(sys.modules, "anthropic", None)  # import raises ImportError
    r = answer.reply("hello", "PROMPT", None, [], False, provider_name="anthropic")
    assert r.provider == "offline" and "pip install" in r.warning


# An empty answer also falls back.
def test_empty_reply_falls_back(monkeypatch, both_keys):
    monkeypatch.setitem(sys.modules, "openai", _fake_openai([], text=""))
    r = answer.reply("hello", "PROMPT", None, [], False, provider_name="openai")
    assert r.provider == "offline" and "empty" in r.warning


# Requesting a provider without a key falls back with a clear message.
def test_provider_without_key_falls_back(monkeypatch):
    r = answer.reply("hello", "PROMPT", None, [], False, provider_name="anthropic")
    assert r.provider == "offline" and "ANTHROPIC_API_KEY is not set" in r.warning


# Older code that unpacks (text, mode) still works.
def test_reply_still_unpacks_as_tuple():
    text, mode = answer.reply("hello", "PROMPT", None, [], False)
    assert mode == "offline template" and text


# ---------- UI (headless Streamlit) ----------

# Helper: the Chat page under AppTest with optional fake keys.
def _app(monkeypatch, tmp_path, keys=()):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("DATA360_DB", str(tmp_path / "ui.db"))
    monkeypatch.chdir(ROOT)
    if "openai" in keys:
        monkeypatch.setenv("OPENAI_API_KEY", FAKE_OPENAI)
    if "anthropic" in keys:
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_ANTHROPIC)
    return AppTest.from_file(str(ROOT / "pages/2_Chat_and_Memory.py"), default_timeout=120)


def _all_text(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption] + [w.value for w in at.warning]
    parts += [i.value for i in at.info] + [str(t.value) for t in at.text_input]
    return " ".join(parts)


# Without keys the switch offers only the offline template, and the memory note is shown.
def test_sidebar_offline_only(monkeypatch, tmp_path):
    at = _app(monkeypatch, tmp_path)
    at.run()
    assert not at.exception
    sel = next(s for s in at.sidebar.selectbox if s.label == "Provider")
    assert sel.options == ["Offline template"]
    assert "identical for every provider" in _all_text(at)


# Switch provider live in the sidebar; each reply shows who answered and both got the same prompt.
def test_sidebar_switch_and_answered_by(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setitem(sys.modules, "openai", _fake_openai(calls))
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(calls))
    at = _app(monkeypatch, tmp_path, keys=("openai", "anthropic"))
    at.run()
    sel = next(s for s in at.sidebar.selectbox if s.label == "Provider")
    assert sel.options == ["Offline template", "OpenAI", "Anthropic"] and sel.value == "openai"
    next(b for b in at.button if b.label == "Load course set (3 learners)").click().run()
    learner = next(s for s in at.selectbox if s.label == "Learner")
    learner.set_value("syn_L01").run()
    at.chat_input[0].set_value("Which R environment do I use now?").run()
    assert not at.exception
    text = _all_text(at)
    assert "OpenAI says hi" in text and "Answered by: OpenAI gpt-6-luna" in text
    # switch to Anthropic: same memory, same prompt
    next(s for s in at.sidebar.selectbox if s.label == "Provider").set_value("anthropic").run()
    at.chat_input[0].set_value("Which R environment do I use now?").run()
    assert not at.exception
    text = _all_text(at)
    assert "Claude says hi" in text and "Answered by: Anthropic claude-haiku-5-5" in text
    assert _payload(*calls[0]) == _payload(*calls[1])
    assert FAKE_OPENAI not in text and FAKE_ANTHROPIC not in text


# A network failure shows a warning in the chat and the offline answer.
def test_ui_fallback_warning(monkeypatch, tmp_path):
    class APIConnectionError(Exception):
        pass

    monkeypatch.setitem(sys.modules, "openai", _fake_openai([], fail=APIConnectionError("network down")))
    at = _app(monkeypatch, tmp_path, keys=("openai",))
    at.run()
    at.chat_input[0].set_value("Why do I keep getting could not find function %>%?").run()
    assert not at.exception
    warnings = " ".join(w.value for w in at.warning)
    assert "failed (APIConnectionError)" in warnings and "offline template" in warnings
    assert "Answered by: offline template" in _all_text(at)


# Keys provided only through Streamlit secrets enable both providers.
def test_keys_from_streamlit_secrets_enable_providers(monkeypatch, tmp_path):
    """Same shape as Streamlit Community Cloud: top-level keys in Secrets, no env vars."""
    at = _app(monkeypatch, tmp_path)
    monkeypatch.delenv("DATA360_SKIP_LOCAL_CONFIG")
    at.secrets["OPENAI_API_KEY"] = FAKE_OPENAI
    at.secrets["ANTHROPIC_API_KEY"] = FAKE_ANTHROPIC
    at.run()
    assert not at.exception
    sel = next(s for s in at.sidebar.selectbox if s.label == "Provider")
    assert sel.options == ["Offline template", "OpenAI", "Anthropic"]
    assert FAKE_OPENAI not in _all_text(at) and FAKE_ANTHROPIC not in _all_text(at)
