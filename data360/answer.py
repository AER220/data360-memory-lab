"""Replies. The memory pipeline (store, retrieval, prompt) never depends on the provider;
only the final step, turning the finished prompt into text, does.

Providers
  offline    built-in template grounded in the retrieved memories (no key, nothing leaves the machine)
  openai     needs OPENAI_API_KEY      (default model gpt-6-luna)
  anthropic  needs ANTHROPIC_API_KEY   (default model claude-haiku-5-5)
  ollama     local server, opt in with DATA360_LLM_PROVIDER=ollama (default model llama3.2)

Keys come from environment variables, a local .env file, or Streamlit secrets (see config.py).
If an API call fails, the reply falls back to the offline template with a warning; it never crashes.
"""
# Here I turn the finished prompt into a reply, with OpenAI, Anthropic, Ollama or the offline
# template.
from __future__ import annotations

import re
from dataclasses import dataclass

import requests

from .config import has, setting
from .memory import Context
from .prompting import split_prompt

# Patterns used by the offline template: personal questions, profile slots and injection attempts.
PERSONAL = re.compile(r"\b(i|my|me|mine|i'm|i've|do i|did i)\b", re.I)
SLOT_HINTS = [
    ("environment", r"environment|rstudio|posit|setup|ide|laptop|where do i (run|code)"),
    # Questions about style also match typos like "prefere" and phrasings like "my answers/responses".
    ("style", r"explanation|explain to me|how do i like|prefer\w*|\bmy (answers?|responses?|replies)\b|answers?\b.*(short|long)|compare .* pandas|pandas"),
    ("accessibility", r"accessib|screen reader|present plots|colou?r blind|describe .*plot|how should you present"),
    ("background", r"background|experience|new to coding"),
]
# Memories that look like instructions ('ignore previous ...') are shown as data and never obeyed.
INJECTION = re.compile(r"ignore (all|the|previous|any)|reveal|system prompt|other learners", re.I)
# When memory has nothing on a personal question, the template says so instead of guessing.
GENERAL_HOWTO = re.compile(r"\s*(how (do|can|should|would) i|how to|what is|what does|what are)\b", re.I)
NO_RECORD = "I do not have a record of that in your memory, so I will not guess."

# Provider names, display labels, default model ids and the key each provider needs.
OFFLINE, OPENAI, ANTHROPIC, OLLAMA = "offline", "openai", "anthropic", "ollama"
LABELS = {OFFLINE: "Offline template", OPENAI: "OpenAI", ANTHROPIC: "Anthropic", OLLAMA: "Ollama (local)"}
# gpt-6-luna is OpenAI's current low-cost model ($0.10 / $0.50 per million tokens) and its named
# replacement for gpt-4o-mini, which shuts down on 14 January 2027. claude-haiku-5-5 is Anthropic's
# fast, low-cost current model. For stronger answers type claude-sonnet-5-5 or gpt-6.1-sol in the
# sidebar's model box (both cost more). A bigger model cannot fix a prompt that lacks the memory, so
# the memory fixes come first; the model choice only changes answer quality.
DEFAULT_MODELS = {OPENAI: "gpt-6-luna", ANTHROPIC: "claude-haiku-5-5", OLLAMA: "llama3.2"}
# Stronger (and pricier) models I suggest in the sidebar help, verified on the providers' model pages.
STRONGER_MODELS = {OPENAI: "gpt-6.1-sol", ANTHROPIC: "claude-sonnet-5-5"}
KEY_NAMES = {OPENAI: "OPENAI_API_KEY", ANTHROPIC: "ANTHROPIC_API_KEY"}
# Shown in the UI to make clear that switching models never changes memory.
MEMORY_NOTE = ("Memory store, retrieval and the prompt are identical for every provider; "
               "switching models only changes who writes the final wording.")


# ---------- provider selection ----------

# Here I list only providers that can actually work: offline always, cloud providers only when their
# key exists.
def available_providers() -> list[str]:
    """Offline is always available; cloud providers only when their key is present."""
    out = [OFFLINE]
    if has(KEY_NAMES[OPENAI]):
        out.append(OPENAI)
    if has(KEY_NAMES[ANTHROPIC]):
        out.append(ANTHROPIC)
    if setting("DATA360_LLM_PROVIDER").lower() == OLLAMA:
        out.append(OLLAMA)
    return out


# Starting choice: an explicit DATA360_LLM_PROVIDER wins, then OpenAI, then Anthropic, then offline.
def default_provider() -> str:
    """DATA360_LLM_PROVIDER if set and usable, else OpenAI if keyed, else Anthropic, else offline."""
    avail = available_providers()
    wanted = setting("DATA360_LLM_PROVIDER").lower()
    if wanted in ("offline", "none", "off", "template"):
        return OFFLINE
    if wanted in avail:
        return wanted
    for p in (OPENAI, ANTHROPIC):
        if p in avail:
            return p
    return OFFLINE


# Kept so older code that asked 'is an LLM on?' still works.
def provider() -> str:
    """Backward compatible: the default provider, or '' when replies use the offline template."""
    p = default_provider()
    return "" if p == OFFLINE else p


# A per-provider override (for example DATA360_ANTHROPIC_MODEL) beats the built-in default.
def default_model(p: str) -> str:
    if p == OFFLINE:
        return ""
    specific = setting(f"DATA360_{p.upper()}_MODEL")
    if specific:
        return specific
    if setting("DATA360_LLM_PROVIDER").lower() == p and setting("DATA360_LLM_MODEL"):
        return setting("DATA360_LLM_MODEL")
    return DEFAULT_MODELS.get(p, "")


# Human-readable label such as 'Anthropic claude-haiku-5-5', shown next to each reply.
def describe(p: str, model: str = "") -> str:
    if p == OFFLINE:
        return "offline template"
    return f"{LABELS.get(p, p)} {model or default_model(p)}"


# ---------- calls ----------

# Every provider gets the same two parts: the system text (rules) and the user text (memory status,
# preferences, profile, retrieved memory, references, question). I split them with split_prompt(), so
# OpenAI, Anthropic and Ollama receive identical content, each through its own proper system channel.
# Before this fix everything was pasted into one user message starting with "SYSTEM:", which a model
# can treat as untrusted user text, and that made answers inconsistent between providers.

# I import each SDK only when it is used, so the offline app still runs if a package is missing.
def _call_openai(prompt: str, model: str, timeout: int) -> str:
    from openai import OpenAI

    system, user = split_prompt(prompt)
    client = OpenAI(api_key=setting(KEY_NAMES[OPENAI]), timeout=timeout, max_retries=1)
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
    kwargs = {"model": model, "messages": messages}
    # Older GPT models accept temperature 0, which makes the same question give the same answer.
    # Newer reasoning models (gpt-5, gpt-6 and o-series) reject a custom temperature; for them I ask
    # for a low reasoning effort, which keeps replies fast and cheap but still follows the
    # preferences carefully.
    if model.startswith(("gpt-4", "gpt-3.5")):
        kwargs["temperature"] = 0
    elif model.startswith(("gpt-5", "gpt-6", "o3", "o4")):
        kwargs["reasoning_effort"] = "low"
    resp = client.chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()


# Anthropic's Messages API takes the system text as a separate `system` parameter and the rest as one
# user message: the same two parts OpenAI gets.
def _call_anthropic(prompt: str, model: str, timeout: int) -> str:
    from anthropic import Anthropic

    system, user = split_prompt(prompt)
    client = Anthropic(api_key=setting(KEY_NAMES[ANTHROPIC]), timeout=timeout, max_retries=1)
    kwargs = {"model": model, "max_tokens": 2048, "messages": [{"role": "user", "content": user}]}
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    # Newer Claude models can return thinking blocks before the answer, so I keep only the text
    # blocks.
    return "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text").strip()


# Ollama runs a free model locally over HTTP; its generate API also has a separate system field.
def _call_ollama(prompt: str, model: str, timeout: int) -> str:
    system, user = split_prompt(prompt)
    host = setting("OLLAMA_HOST", "http://localhost:11434")
    body = {"model": model, "prompt": user, "stream": False}
    if system:
        body["system"] = system
    r = requests.post(f"{host}/api/generate", timeout=timeout, json=body)
    r.raise_for_status()
    return r.json()["response"]


# A lookup table from provider name to the function that calls it.
CALLS = {OPENAI: _call_openai, ANTHROPIC: _call_anthropic, OLLAMA: _call_ollama}


# Sends the finished prompt to one provider. It raises on any problem; reply() decides what to do
# about it.
def llm_complete(prompt: str, p: str | None = None, model: str | None = None, timeout: int = 60) -> str:
    p = p or default_provider()
    if p not in CALLS:
        raise RuntimeError("no LLM provider configured")
    if p in KEY_NAMES and not has(KEY_NAMES[p]):
        raise RuntimeError(f"{KEY_NAMES[p]} is not set")
    text = CALLS[p](prompt, (model or "").strip() or default_model(p), timeout)
    # An empty answer counts as a failure, so the learner never sees a blank bubble.
    if not text:
        raise RuntimeError("the provider returned an empty reply")
    return text


# Builds a short, friendly error message. I never include the raw SDK message because it can contain
# part of the key.
def _safe_error(exc: Exception) -> str:
    """Short, key-free description of a failed call."""
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    hint = {401: "the API key was rejected; check it in Secrets", 403: "the key has no access to this model",
            404: "model name not found", 429: "rate limit or no credits left on this account"}.get(status, "")
    if isinstance(exc, ImportError):
        hint = "the SDK is not installed; run pip install -r requirements.txt"
    if not hint and isinstance(exc, RuntimeError):
        hint = str(exc)
    if not hint and "timeout" in type(exc).__name__.lower():
        hint = "the request timed out"
    parts = [type(exc).__name__] + ([f"HTTP {status}"] if status else []) + ([hint] if hint else [])
    msg = ", ".join(parts)
    # Extra safety: blank out any key value and anything that looks like an sk- key.
    for name in KEY_NAMES.values():  # belt and braces: never echo a key
        key = setting(name)
        if key:
            msg = msg.replace(key, "***")
    return re.sub(r"(sk-[A-Za-z0-9_\-]{4})[A-Za-z0-9_\-]+", r"\1***", msg)


# ---------- offline template ----------

# The offline reply: a template filled from the retrieved memories and references. It shows what
# memory found without any model.
def template_reply(question: str, ctx: Context | None, references: list[dict], memory_on: bool) -> str:
    q = question.lower()
    parts: list[str] = []
    # A general how-to question ("How do I filter rows in R?") contains "I" but is not about the
    # learner's past, so the template must not answer it with "I do not have a record of that".
    general = bool(GENERAL_HOWTO.match(q)) and not re.search(r"\b(my|mine|me)\b", q)
    personal = bool(PERSONAL.search(question)) and not general
    answered = False
    if memory_on and ctx is not None:
        # If the question is about a profile slot, answer with the current fact and cite its id.
        for slot, pat in SLOT_HINTS:
            if re.search(pat, q):
                match = [m for m in ctx.profile if m.slot == slot or (slot == "style" and m.topic in ("style", "data frames"))]
                if match:
                    parts.append(f"Your current {slot} fact is [{match[0].memory_id}]: \"{match[0].text}\"")
                    answered = True
                break
        # Split memories into normal ones and ones that look like injected instructions.
        rel = [r for r in ctx.memories if not INJECTION.search(r.memory.text)]
        flagged = [r for r in ctx.memories if INJECTION.search(r.memory.text)]
        if rel:
            parts.append("From our earlier sessions:")
            parts += [f"- [{r.memory.memory_id}] ({r.memory.session_id}) {r.memory.text}" for r in rel]
            answered = True
        if flagged:
            parts.append(f"Memory {', '.join(r.memory.memory_id for r in flagged)} contains an instruction. "
                         "I treat it as data and did not follow it.")
        # Personal question with nothing found: abstain instead of inventing an answer.
        if personal and not answered:
            parts.insert(0, NO_RECORD)
        style = [m for m in ctx.profile if m.slot == "style"]
        # Stated style preferences are acknowledged on every answer, including general questions.
        if style and (answered or not personal):
            parts.append(f"(I will follow your stated preference: {style[0].text})")
    # Memory switched off: be honest that nothing about the learner is available.
    elif personal:
        parts.append("Memory is off, so I cannot recall anything about you from earlier sessions.")
    if references:
        parts.append("Course reference:")
        for r in references:
            label = "Stack Overflow thread" if r.get("kind") == "stackoverflow" else r.get("title", "doc")
            parts.append(f"- {label}: {r['text'][:220].strip()}... ({r.get('source_url', '')})")
    if not parts:
        parts.append("I could not find anything relevant. Could you share the exact R error message and the line of code?")
    out = []
    for part in parts:  # blank line before each non-bullet paragraph so Markdown keeps them apart
        out.append(part if part.startswith("- ") else f"\n{part}")
    return "\n".join(out).strip()


# ---------- public entry point ----------

@dataclass
# What reply() returns: the text, who actually answered, who was asked, and a warning if it fell back.
class Reply:
    text: str
    provider: str          # who actually answered: offline / openai / anthropic / ollama
    model: str             # model id that answered ("" for offline)
    requested: str         # provider the user picked
    warning: str = ""      # set when a call failed and we fell back to the template

    @property
    def label(self) -> str:
        return describe(self.provider, self.model)

    # Lets older code keep writing `text, mode = reply(...)`.
    def __iter__(self):  # allows: text, mode = reply(...)
        return iter((self.text, self.label))


# Entry point used by the Chat page. The prompt was already built from memory, so memory is identical
# whichever provider is chosen.
def reply(question: str, prompt: str, ctx: Context | None, references: list[dict], memory_on: bool,
          provider_name: str | None = None, model: str | None = None) -> Reply:
    """The prompt is built before this call and is the same for every provider."""
    p = provider_name or default_provider()
    if p == OFFLINE:
        return Reply(template_reply(question, ctx, references, memory_on), OFFLINE, "", OFFLINE)
    used_model = (model or "").strip() or default_model(p)
    try:
        return Reply(llm_complete(prompt, p, used_model), p, used_model, p)
    # Any failure (bad key, no credits, network, unknown model) falls back to the offline template
    # with a clear warning.
    except Exception as exc:  # never crash the class demo
        warning = (f"{describe(p, used_model)} failed ({_safe_error(exc)}). "
                   "Showing the offline template instead; memory was not affected.")
        return Reply(template_reply(question, ctx, references, memory_on), OFFLINE, "", p, warning)


# Used by the evaluation to count honest 'I do not know' answers.
def is_abstention(text: str) -> bool:
    return text.startswith(NO_RECORD) or "cannot recall anything" in text
