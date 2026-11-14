"""Shared Streamlit helpers (sidebar, cached manager)."""
from __future__ import annotations

import os

import streamlit as st

from . import datasets
from .answer import provider
from .memory import MemoryManager
from .paths import db_path
from .paths import ROOT
from .store import MemoryStore


def _load_dotenv() -> None:
    """Read KEY=VALUE lines from .env (if present) without extra dependencies."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

DISCLAIMER = ("All learners in this app are fictional (synthetic). Reference material is real public documentation "
              "and public Stack Overflow questions. Do not type real names, grades, NetIDs or classmates' work.")


@st.cache_resource(show_spinner="Opening the memory store and fitting local embeddings ...")
def get_manager(path: str) -> MemoryManager:
    return MemoryManager(MemoryStore(path))


def manager() -> MemoryManager:
    return get_manager(str(db_path()))


def load_dataset_into_store(mm: MemoryManager, name: str, replace: bool = True) -> dict:
    events, _ = datasets.load_dataset(name)
    if replace:
        for lid in sorted({e["learner_id"] for e in events}):
            mm.store.delete_learner(lid)
    return mm.load_events(events)


def sidebar(mm: MemoryManager) -> None:
    st.sidebar.markdown("### Data360-Memory")
    st.sidebar.caption("Building Human-Centered AI Applications, Syracuse University. Long-term memory lab.")
    n = mm.store.count()
    st.sidebar.metric("Memories in store", n, help=f"SQLite file: {mm.store.path}")
    if st.sidebar.button("Load course set (3 learners)", width="stretch", help="3 hand-written learners, 28 events (from the proposal)"):
        r = load_dataset_into_store(mm, "canonical")
        st.session_state["load_msg"] = f"Course set: saved {r['saved']}, skipped {r['skipped']} distractors."
        st.rerun()
    if st.sidebar.button("Load generated learners", width="stretch", help="Seeded synthetic learners (data/synthetic/generated_events.jsonl)"):
        r = load_dataset_into_store(mm, "generated")
        st.session_state["load_msg"] = f"Generated set: saved {r['saved']}, skipped {r['skipped']} distractors."
        st.rerun()
    if st.session_state.get("load_msg"):
        st.sidebar.success(st.session_state["load_msg"])
    if st.sidebar.button("Reset all memories", type="secondary", width="stretch"):
        mm.store.clear()
        st.session_state.pop("load_msg", None)
        st.session_state.pop("chat", None)
        st.rerun()
    st.sidebar.divider()
    st.sidebar.caption(f"Embeddings: **{mm.embedder.name}** (local, no key)")
    p = provider()
    if p:
        st.sidebar.warning(f"LLM: {p} ({os.environ.get('DATA360_LLM_MODEL', 'default model')}). "
                           "Questions, memories and reference excerpts are sent to this provider.")
    else:
        st.sidebar.info("LLM: off. Replies use the offline template. Set DATA360_LLM_PROVIDER to enable one.")
