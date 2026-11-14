"""Shared Streamlit helpers (sidebar, cached manager)."""
# Shared Streamlit pieces used by every page: the cached memory manager and the sidebar, including
# the model switch.
from __future__ import annotations

import streamlit as st

from . import datasets
from .answer import (DEFAULT_MODELS, KEY_NAMES, LABELS, MEMORY_NOTE, OFFLINE, STRONGER_MODELS, available_providers,
                     default_model, default_provider, describe)
from .config import load_dotenv
from .memory import MemoryManager
from .paths import db_path
from .store import MemoryStore

# Read .env once when any page imports this module.
load_dotenv()

# Shown on every page: all learners are fictional and real student data must not be typed in.
DISCLAIMER = ("All learners in this app are fictional (synthetic). Reference material is real public documentation "
              "and public Stack Overflow questions. Do not type real names, grades, NetIDs or classmates' work.")


# cache_resource keeps one MemoryManager per database file for the whole server, so the embedder is
# fitted once, not on every rerun.
@st.cache_resource(show_spinner="Opening the memory store and fitting local embeddings ...")
def get_manager(path: str) -> MemoryManager:
    return MemoryManager(MemoryStore(path))


# Pages call this to get the shared manager for the configured database.
def manager() -> MemoryManager:
    return get_manager(str(db_path()))


# Loads a synthetic dataset; I delete those learners first so loading twice does not duplicate
# memories.
def load_dataset_into_store(mm: MemoryManager, name: str, replace: bool = True) -> dict:
    events, _ = datasets.load_dataset(name)
    if replace:
        for lid in sorted({e["learner_id"] for e in events}):
            mm.store.delete_learner(lid)
    return mm.load_events(events)


# The sidebar is the same on every page: store size, dataset buttons, reset, embedder and the model
# switch.
def sidebar(mm: MemoryManager) -> None:
    st.sidebar.markdown("### Data360-Memory")
    st.sidebar.caption("Building Human-Centered AI Applications, Syracuse University. Long-term memory lab.")
    n = mm.store.count()
    st.sidebar.metric("Memories in store", n, help=f"SQLite file: {mm.store.path}")
    if st.sidebar.button("Load course set (3 learners)", width="stretch", help="3 hand-written learners, 28 events (from the proposal)"):
        r = load_dataset_into_store(mm, "canonical")
        # I keep the message in session state because st.rerun() would otherwise wipe it.
        st.session_state["load_msg"] = f"Course set: saved {r['saved']}, skipped {r['skipped']} distractors."
        st.rerun()
    if st.sidebar.button("Load generated learners", width="stretch", help="Seeded synthetic learners (data/synthetic/generated_events.jsonl)"):
        r = load_dataset_into_store(mm, "generated")
        st.session_state["load_msg"] = f"Generated set: saved {r['saved']}, skipped {r['skipped']} distractors."
        st.rerun()
    if st.session_state.get("load_msg"):
        st.sidebar.success(st.session_state["load_msg"])
    # Reset also clears the chat, so no reply refers to memories that no longer exist.
    if st.sidebar.button("Reset all memories", type="secondary", width="stretch"):
        mm.store.clear()
        st.session_state.pop("load_msg", None)
        st.session_state.pop("chat", None)
        st.rerun()
    st.sidebar.divider()
    st.sidebar.caption(f"Embeddings: **{mm.embedder.name}** (local, no key)")
    llm_selector()


# Returns the provider and model picked in the sidebar. The Chat page calls this right before
# replying.
def llm_choice() -> tuple[str, str]:
    """(provider, model) currently picked in the sidebar; shared by every page through session state."""
    ss = st.session_state
    avail = available_providers()
    # If the saved choice is no longer available (for example a key was removed), go back to the
    # default.
    if ss.get("llm_provider") not in avail:
        ss["llm_provider"] = default_provider()
    p = ss["llm_provider"]
    model = (ss.get("llm_models", {}).get(p) or "").strip() or default_model(p)
    return p, model


# The live model switch. Streamlit forgets widget values when you change page, so I copy each choice
# into my own session keys and rebuild the widget from them.
def llm_selector() -> None:
    """Sidebar model switch. Values live in plain session keys (not widget keys) so they survive page changes."""
    ss = st.session_state
    ss.setdefault("llm_models", {})
    avail = available_providers()
    p, _ = llm_choice()

    # Called when the learner picks a provider; stores it under a key Streamlit will not clean up.
    def _set_provider():
        ss["llm_provider"] = ss["_llm_provider_widget"]

    st.sidebar.markdown("**Reply model**")
    st.sidebar.selectbox("Provider", avail, index=avail.index(p), format_func=lambda k: LABELS.get(k, k),
                         key="_llm_provider_widget", on_change=_set_provider,
                         help="Only providers whose API key is configured are listed. Keys are never shown.")
    p = ss["llm_provider"]
    # Tell the user which providers are hidden and which key would enable them, without ever showing a
    # key.
    missing = [LABELS[k] for k, name in KEY_NAMES.items() if k not in avail]
    if missing:
        st.sidebar.caption("Not configured: " + ", ".join(
            f"{LABELS[k]} (add {KEY_NAMES[k]})" for k in KEY_NAMES if k not in avail) + ".")
    if p != OFFLINE:
        # One model box per provider, so switching back and forth keeps each provider's model name.
        wkey = f"_llm_model_widget_{p}"

        def _set_model():
            ss["llm_models"][p] = ss[wkey].strip()

        st.sidebar.text_input("Model name (optional)", value=ss["llm_models"].get(p, ""), key=wkey,
                              placeholder=default_model(p) or DEFAULT_MODELS.get(p, ""), on_change=_set_model,
                              help=f"Leave empty for the default ({default_model(p)})."
                              + (f" For stronger but pricier answers try {STRONGER_MODELS[p]}." if p in STRONGER_MODELS else ""))
        _, model = llm_choice()
        # Privacy notice: with a cloud model, the question, memories and excerpts leave the app.
        st.sidebar.warning(f"LLM: {describe(p, model)}. Questions, memories and reference excerpts "
                           "are sent to this provider.")
    else:
        st.sidebar.info("LLM: off. Replies use the offline template; nothing leaves the app.")
    st.sidebar.caption(MEMORY_NOTE)
