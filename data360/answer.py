"""Replies. Offline template by default; optional LLM through environment variables.

DATA360_LLM_PROVIDER = "openai" (needs OPENAI_API_KEY) or "ollama" (local server, free)
DATA360_LLM_MODEL    = model name (default gpt-4o-mini or llama3.2)
Nothing is sent anywhere unless DATA360_LLM_PROVIDER is set.
"""
from __future__ import annotations

import os
import re

import requests

from .memory import Context

PERSONAL = re.compile(r"\b(i|my|me|mine|i'm|i've|do i|did i)\b", re.I)
SLOT_HINTS = [
    ("environment", r"environment|rstudio|posit|setup|ide|laptop|where do i (run|code)"),
    ("style", r"explanation|explain to me|how do i like|answers?\b.*(short|long)|compare .* pandas|pandas"),
    ("accessibility", r"accessib|screen reader|present plots|colou?r blind|describe .*plot|how should you present"),
    ("background", r"background|experience|new to coding"),
]
INJECTION = re.compile(r"ignore (all|the|previous|any)|reveal|system prompt|other learners", re.I)
NO_RECORD = "I do not have a record of that in your memory, so I will not guess."


def provider() -> str:
    p = os.environ.get("DATA360_LLM_PROVIDER", "").strip().lower()
    if p == "openai" and not os.environ.get("OPENAI_API_KEY"):
        return ""
    return p if p in ("openai", "ollama") else ""


def llm_complete(prompt: str, timeout: int = 60) -> str:
    p = provider()
    if p == "openai":
        r = requests.post("https://api.openai.com/v1/chat/completions", timeout=timeout,
                          headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                          json={"model": os.environ.get("DATA360_LLM_MODEL", "gpt-4o-mini"),
                                "messages": [{"role": "user", "content": prompt}], "temperature": 0.2})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    if p == "ollama":
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        r = requests.post(f"{host}/api/generate", timeout=timeout,
                          json={"model": os.environ.get("DATA360_LLM_MODEL", "llama3.2"), "prompt": prompt, "stream": False})
        r.raise_for_status()
        return r.json()["response"]
    raise RuntimeError("no LLM provider configured")


def template_reply(question: str, ctx: Context | None, references: list[dict], memory_on: bool) -> str:
    q = question.lower()
    parts: list[str] = []
    personal = bool(PERSONAL.search(question))
    answered = False
    if memory_on and ctx is not None:
        for slot, pat in SLOT_HINTS:
            if re.search(pat, q):
                match = [m for m in ctx.profile if m.slot == slot or (slot == "style" and m.topic in ("style", "data frames"))]
                if match:
                    parts.append(f"Your current {slot} fact is [{match[0].memory_id}]: \"{match[0].text}\"")
                    answered = True
                break
        rel = [r for r in ctx.memories if not INJECTION.search(r.memory.text)]
        flagged = [r for r in ctx.memories if INJECTION.search(r.memory.text)]
        if rel:
            parts.append("From our earlier sessions:")
            parts += [f"- [{r.memory.memory_id}] ({r.memory.session_id}) {r.memory.text}" for r in rel]
            answered = True
        if flagged:
            parts.append(f"Memory {', '.join(r.memory.memory_id for r in flagged)} contains an instruction. "
                         "I treat it as data and did not follow it.")
        if personal and not answered:
            parts.insert(0, NO_RECORD)
        style = [m for m in ctx.profile if m.slot == "style"]
        if style and answered:
            parts.append(f"(I will follow your stated preference: {style[0].text})")
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


def reply(question: str, prompt: str, ctx: Context | None, references: list[dict], memory_on: bool) -> tuple[str, str]:
    """Returns (text, mode) where mode is 'offline template' or the provider name."""
    if provider():
        try:
            return llm_complete(prompt), provider()
        except Exception as exc:  # never crash the class demo
            return (template_reply(question, ctx, references, memory_on)
                    + f"\n\n(LLM call failed: {type(exc).__name__}; showing the offline template.)", "offline template")
    return template_reply(question, ctx, references, memory_on), "offline template"


def is_abstention(text: str) -> bool:
    return text.startswith(NO_RECORD) or "cannot recall anything" in text
