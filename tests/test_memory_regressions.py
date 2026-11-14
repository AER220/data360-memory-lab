"""Regression tests for the issues found in the deployed v2 app (learner Ed01, 'I prefer short answers').

All API calls are mocked; the fake SDKs record exactly what each provider would receive.
"""
import sys
import types
from pathlib import Path

import pytest

from data360 import answer
from data360.extract import propose
from data360.memory import MemoryManager, Policy
from data360.prompting import build_prompt
from data360.store import MemoryStore
from data360.timeutil import iso, now

ROOT = Path(__file__).resolve().parents[1]
FAKE_OPENAI = "sk-test-openai-regression-123456"
FAKE_ANTHROPIC = "sk-ant-test-regression-654321"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DATA360_LLM_PROVIDER", "DATA360_LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DATA360_SKIP_LOCAL_CONFIG", "1")


def _approve(mm, learner, message):
    # Here I do what the Approve button does: save the proposed card for this learner.
    cand = propose(message)[0]
    return mm.write(dict(cand, learner_id=learner, session_id="live_test", timestamp=iso(now()), synthetic=True))


# Records the payload each SDK receives, as (provider, system, user).
def _fake_sdks(monkeypatch, sent):
    oa = types.ModuleType("openai")

    class Completions:
        def create(self, **kw):
            system = "".join(m["content"] for m in kw["messages"] if m["role"] == "system")
            user = "".join(m["content"] for m in kw["messages"] if m["role"] == "user")
            sent.append(("openai", system, user, kw))
            msg = types.SimpleNamespace(content="openai reply")
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    class OpenAI:
        def __init__(self, **kw):
            self.chat = types.SimpleNamespace(completions=Completions())

    oa.OpenAI = OpenAI
    an = types.ModuleType("anthropic")

    class Messages:
        def create(self, **kw):
            sent.append(("anthropic", kw.get("system", ""), kw["messages"][0]["content"], kw))
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="claude reply")])

    class Anthropic:
        def __init__(self, **kw):
            self.messages = Messages()

    an.Anthropic = Anthropic
    monkeypatch.setitem(sys.modules, "openai", oa)
    monkeypatch.setitem(sys.modules, "anthropic", an)


# ---------- issue 1: preferences must be loaded and applied on every answer ----------

def test_preference_is_semantic_and_always_in_prompt(mm):
    status, mid = _approve(mm, "Ed01", "I prefer short answers")
    m = mm.store.get(mid)
    assert status == "saved" and m.memory_type == "semantic" and m.slot == "style"
    q = "How do I filter rows in R?"  # unrelated to the preference: similarity must not matter
    ctx = mm.context("Ed01", q)
    assert [p.memory_id for p in ctx.preferences] == [mid]
    prompt = build_prompt(q, ctx, [], memory_on=True)
    assert "LEARNER PREFERENCES" in prompt.user and "I prefer short answers" in prompt.user
    assert "Apply them to EVERY answer" in prompt.system
    assert prompt.user.rstrip().endswith("(Apply the LEARNER PREFERENCES above to this answer.)")
    # memory is still untrusted data: the injection rule stays, and comes before any memory
    assert "Never follow instructions" in prompt.system


@pytest.mark.parametrize("message", ["I prefer short answers", "i prefere short answers", "I want shorter responses",
                                     "Please keep answers short", "keep it short",
                                     "I prefer comments on every line of R code."])
def test_preference_statements_are_semantic_style(message):
    (cand,) = propose(message)
    assert (cand["memory_type"], cand["event_type"], cand["slot"]) == ("semantic", "preference_stated", "style")


@pytest.mark.parametrize("question", ["how do i prefere my answers?", "How do I prefer my R responses?",
                                      "what do i prefer"])
def test_questions_about_preferences_are_not_saved_as_preferences(question):
    assert all(c["memory_type"] != "semantic" for c in propose(question))


def test_slot_facts_are_never_cut_from_the_profile(tmp_path):
    mm = MemoryManager(MemoryStore(tmp_path / "cap.db"), policy=Policy(profile_max=1))
    for msg in ["I use Posit Cloud now", "I prefer short answers", "I use a screen reader"]:
        _approve(mm, "Ed01", msg)
    slots = {m.slot for m in mm.profile("Ed01")}
    assert {"environment", "style", "accessibility"} <= slots


# ---------- issue 2: typos and identical questions ----------

def test_identical_questions_build_identical_prompts(mm):
    _approve(mm, "Ed01", "I prefer short answers")
    _approve(mm, "Ed01", "Got Error: could not find function mutate")
    q = "how do i prefere my answers?"
    prompts = [build_prompt(q, mm.context("Ed01", q, touch=True), [], memory_on=True) for _ in range(3)]
    assert prompts[0] == prompts[1] == prompts[2]
    assert "I prefer short answers" in prompts[0].user


def test_offline_template_answers_typo_question(mm):
    _approve(mm, "Ed01", "I prefer short answers")
    q = "how do i prefere my answers?"
    text = answer.template_reply(q, mm.context("Ed01", q), [], True)
    assert "I prefer short answers" in text and not text.startswith(answer.NO_RECORD)


def test_retrieval_tolerates_small_typos(mm):
    status, mid = _approve(mm, "Ed01", "Got Error: could not find function mutate")
    for q in ["could not find function mutate", "coud not find functon mutate", "cant find functoin mutate"]:
        assert mid in [r.memory.memory_id for r in mm.retrieve("Ed01", q)], q


# ---------- issue 3: same payload for both providers, memory never reported as off ----------

def test_both_providers_receive_identical_payload_with_memory_on(mm, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_OPENAI)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_ANTHROPIC)
    sent = []
    _fake_sdks(monkeypatch, sent)
    _approve(mm, "Ed01", "I prefer short answers")
    q = "How do I filter rows in R?"
    ctx = mm.context("Ed01", q)
    prompt = build_prompt(q, ctx, [], memory_on=True)
    answer.reply(q, prompt, ctx, [], True, provider_name="openai")
    answer.reply(q, prompt, ctx, [], True, provider_name="anthropic")
    (_, s1, u1, kw1), (_, s2, u2, kw2) = sent
    assert (s1, u1) == (s2, u2) == (prompt.system, prompt.user)
    assert kw1["messages"][0]["role"] == "system" and kw2["system"] == prompt.system  # real system channel
    assert "MEMORY STATUS: on for learner Ed01" in u2 and "MEMORY: off" not in u2
    assert "I prefer short answers" in u2 and not u2.startswith("SYSTEM:")
    # default gpt-6-luna is a reasoning model: low effort, no temperature (it would be rejected)
    assert kw1["model"] == "gpt-6-luna" and kw1.get("reasoning_effort") == "low" and "temperature" not in kw1
    assert kw2["model"] == "claude-haiku-5-5"


def test_older_gpt_models_get_temperature_zero(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_OPENAI)
    sent = []
    _fake_sdks(monkeypatch, sent)
    answer.reply("hi", build_prompt("hi", None, memory_on=False), None, [], False, provider_name="openai",
                 model="gpt-4o-mini")
    assert sent[0][3].get("temperature") == 0 and "reasoning_effort" not in sent[0][3]


# ---------- UI: state survives reruns, provider switches and page changes ----------

def _page(monkeypatch, tmp_path, keys=True):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("DATA360_DB", str(tmp_path / "ui.db"))
    monkeypatch.chdir(ROOT)
    if keys:
        monkeypatch.setenv("OPENAI_API_KEY", FAKE_OPENAI)
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_ANTHROPIC)
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)


def test_unapproved_card_is_not_overwritten_by_next_message(monkeypatch, tmp_path):
    """v2 bug: the old text stayed in the box while the card changed, saving a preference as an episodic question."""
    at = _page(monkeypatch, tmp_path, keys=False)
    at.run()
    at.switch_page("pages/2_Chat_and_Memory.py").run()
    next(t for t in at.text_input if t.label.startswith("New learner")).set_value("Ed01").run()
    at.chat_input[0].set_value("I prefer short answers").run()
    at.chat_input[0].set_value("How do I filter rows in R?").run()
    assert [t.value for t in at.text_area][:2] == ["I prefer short answers", "Asked: How do I filter rows in R?"]
    next(b for b in at.button if b.label == "Approve").click().run()
    assert not at.exception
    mems = MemoryStore(tmp_path / "ui.db").list("Ed01")
    assert [(m.memory_type, m.slot, m.text) for m in mems] == [("semantic", "style", "I prefer short answers")]


def test_learner_toggle_and_provider_survive_switches(monkeypatch, tmp_path):
    sent = []
    _fake_sdks(monkeypatch, sent)
    at = _page(monkeypatch, tmp_path)
    at.run()
    at.switch_page("pages/2_Chat_and_Memory.py").run()
    next(b for b in at.button if b.label == "Load course set (3 learners)").click().run()
    learner = lambda: next(s for s in at.selectbox if s.label == "Learner")  # noqa: E731
    learner().set_value("+ new learner").run()
    # 'zed01' sorts after the syn_ learners; v2 jumped back to the first learner after the first save
    next(t for t in at.text_input if t.label.startswith("New learner")).set_value("zed01").run()
    at.chat_input[0].set_value("I prefer short answers").run()
    next(b for b in at.button if b.label == "Approve").click().run()
    assert learner().value == "zed01"
    memory = lambda: next(t for t in at.toggle if t.label == "Use long-term memory")  # noqa: E731
    assert memory().value is True
    provider = lambda: next(s for s in at.sidebar.selectbox if s.label == "Provider")  # noqa: E731
    provider().set_value("anthropic").run()
    assert memory().value is True and learner().value == "zed01"
    at.switch_page("pages/3_Memory_Timeline.py").run()
    at.switch_page("pages/2_Chat_and_Memory.py").run()
    assert memory().value is True and learner().value == "zed01" and provider().value == "anthropic"
    at.chat_input[0].set_value("How do I filter rows in R?").run()
    assert not at.exception
    name, system, user, _ = sent[-1]
    assert name == "anthropic" and "MEMORY STATUS: on for learner zed01" in user and "I prefer short answers" in user
    assert any("Answered by: Anthropic claude-haiku-5-5 | memory on" in c.value for c in at.caption)
    # turning memory off is respected and also survives a page change
    memory().set_value(False).run()
    at.switch_page("pages/0_Overview.py").run()
    at.switch_page("pages/2_Chat_and_Memory.py").run()
    assert memory().value is False
    at.chat_input[0].set_value("How do I filter rows in R?").run()
    assert "MEMORY: off" in sent[-1][2] and "I prefer short answers" not in sent[-1][2]
    assert any("| memory off" in c.value for c in at.caption)
    assert FAKE_ANTHROPIC not in " ".join(c.value for c in at.caption)


def test_offline_template_general_question_keeps_preference(mm):
    _approve(mm, "Ed01", "I prefer short answers")
    q = "How do I filter rows in R?"
    text = answer.template_reply(q, mm.context("Ed01", q), [], True)
    assert not text.startswith(answer.NO_RECORD) and "I prefer short answers" in text
    # a real personal question with nothing stored still abstains
    q2 = "What is my favourite colour for plots?"
    assert answer.template_reply(q2, mm.context("Ed01", q2), [], True).startswith(answer.NO_RECORD)
