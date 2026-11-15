# Chat and Memory page: talk to Data360 as a learner, approve memories, inspect the prompt and
# manage your memory.
import uuid

import pandas as pd
import streamlit as st

from data360 import knowledge
from data360.answer import MEMORY_NOTE, reply
from data360.extract import propose
from data360.prompting import build_prompt
from data360.timeutil import iso, now
from data360.ui import DISCLAIMER, NEW_USER, clean_user_id, llm_choice, manager, sidebar, visible_learners

st.set_page_config(page_title="Chat and Memory", page_icon="💬", layout="wide")
# Every page shares one cached memory manager, so all pages see the same store.
mm = manager()
# Same sidebar everywhere: dataset buttons, reset and the reply model switch.
sidebar(mm)
st.title("Chat and Memory")
st.caption(DISCLAIMER)

# Chat history, pending memory cards and the last retrieval are kept per learner in session state.
ss = st.session_state
ss.setdefault("chat", {})
ss.setdefault("pending", {})
ss.setdefault("last", {})

# Pick which learner you are. Memory is always looked up for this learner only.
# I keep the choice in my own session key ("learner_pick"). Without this, Streamlit reset the box to
# the first learner whenever the list of learners changed (for example right after a new learner's
# first memory was saved), so later questions could silently run as a different learner.
# The list shows the fictional demo learners plus the users created in THIS browser session, not
# every classmate's user, so on the shared class app nobody browses other people's memory by
# accident. A returning classmate types the same name again to get their memory back. This is a
# convenience, not a login: anyone who knows a name can open it, which the caption says.
ss.setdefault("my_users", [])
learners = visible_learners(mm, ss["my_users"])
options = learners + [NEW_USER]
if ss.get("learner_pick") not in options:
    ss["learner_pick"] = options[0]
# Before the box is drawn I copy my saved choice into the widget's own key when the widget has lost
# it (page change), holds a stale value, or the app asked to select a learner (after a first save).
if ss.pop("_force_learner", False) or ss.get("_learner_widget") not in options:
    ss["_learner_widget"] = ss["learner_pick"]


def _pick_learner():
    ss["learner_pick"] = ss["_learner_widget"]


c1, c2, c3 = st.columns([2, 2, 2])
choice = c1.selectbox("Learner", options, key="_learner_widget", on_change=_pick_learner,
                      help="Pick a demo learner, or choose '+ new learner' to create your own user.")
if choice == NEW_USER:
    # Creating a user is just typing a name: the user exists as soon as you chat. Every user sees the
    # same shared R reference notes and has a private memory that starts empty.
    # A random starting name, so two classmates who do not change it never share a memory.
    ss.setdefault("new_learner_id", f"user_{uuid.uuid4().hex[:4]}")
    new = c1.text_input("New learner id (pseudonym only)", value=ss["new_learner_id"],
                        help="Letters, numbers, _ or -, up to 30 characters. Use a nickname, not your NetID. "
                             "Type the same name next time to get your memory back.")
    clean = clean_user_id(new)
    if new.strip() and clean != new.strip():
        c1.caption(f"Using `{clean}` (only letters, numbers, _ and - are kept).")
    ss["new_learner_id"] = clean or ss["new_learner_id"]
    learner = ss["new_learner_id"]
    if learner not in ss["my_users"]:
        ss["my_users"].append(learner)
    known = len(mm.store.list(learner))
    c1.caption(f"Welcome back, `{learner}`: {known} memories found." if known else
               f"New user `{learner}`: your private memory is empty; the R reference notes are ready.")
else:
    learner = choice
# Each chat gets a session id, so approved memories record which session they came from.
ss.setdefault("session_ids", {})
ss["session_ids"].setdefault(learner, f"live_{uuid.uuid4().hex[:4]}")
if c2.button("Start a new session"):
    ss["session_ids"][learner] = f"live_{uuid.uuid4().hex[:4]}"
    ss["chat"][learner] = []
c2.caption(f"Session `{ss['session_ids'][learner]}`. Memories approved now carry this session id.")
# Memory on/off switch for the live comparison with a normal chatbot. Like the learner, the value
# lives in my own session keys, so it survives switching provider, switching page and reruns; it only
# changes when the learner flips it.
ss.setdefault("memory_on", True)
ss.setdefault("use_refs", True)


def _flip(name):
    ss[name] = ss[f"_{name}_widget"]


memory_on = c3.toggle("Use long-term memory", value=ss["memory_on"], key="_memory_on_widget",
                      on_change=_flip, args=("memory_on",),
                      help="Off: no personal memory is read or written. The R reference notes stay available.")
use_refs = c3.toggle("Use R reference notes (RAG)", value=ss["use_refs"], key="_use_refs_widget",
                     on_change=_flip, args=("use_refs",))

if not learners:
    st.info("Type a name in **New learner id** and start chatting to create your own user, or click "
            "**Load course set (3 learners)** in the sidebar for the demo learners.")

chat_col, insp_col = st.columns([3, 2])

with chat_col:
    st.markdown("#### Chat")
    st.caption("Try: `Which R environment do I use now?`, `Why do I keep getting could not find function %>%?`, "
               "`How do I make a word cloud?`, `I prefer comments on every line of R code.`, `What is my favourite colour?`")
    # Redraw the conversation, including any fallback warning and the 'Answered by' label of each
    # reply.
    for msg in ss["chat"].get(learner, []):
        with st.chat_message(msg["role"]):
            if msg.get("warning"):
                st.warning(msg["warning"])
            st.markdown(msg["content"])
            if msg.get("answered_by"):
                # Each reply records who answered AND whether memory was on for that turn, so a
                # transcript always shows the real memory state.
                mem = "on" if msg.get("memory_on", True) else "off"
                st.caption(f"Answered by: {msg['answered_by']} | memory {mem}")
    question = st.chat_input("Ask Data360 an R question, or tell it something about you")
    # The memory loop for one question: retrieve, build the prompt, reply, then propose a memory.
    if question:
        # Retrieve this learner's profile and top memories (only if memory is on). touch=True records
        # that they were used.
        ctx = mm.context(learner, question, touch=True) if memory_on else None
        refs = knowledge.search(question) if use_refs else []
        # The prompt is built before choosing a provider, so it is identical for offline, OpenAI and
        # Anthropic.
        prompt = build_prompt(question, ctx, refs, memory_on=memory_on, budget=mm.policy.k)
        # Whatever is picked in the sidebar right now answers this turn; switching later does not
        # touch memory.
        chosen, model = llm_choice()
        with st.spinner(f"Writing the reply ({chosen}) ..."):
            ans = reply(question, prompt, ctx, refs, memory_on, provider_name=chosen, model=model)
        ss["chat"].setdefault(learner, []).extend([
            {"role": "user", "content": question},
            # The stored reply ends with the Sources block (ids, titles, verified links).
            {"role": "assistant", "content": ans.full_text, "answered_by": ans.label, "warning": ans.warning,
             "memory_on": memory_on}])
        ss["last"][learner] = {"ctx": ctx, "prompt": prompt, "refs": refs, "answered_by": ans.label,
                               "requested": chosen, "warning": ans.warning, "memory_on": memory_on}
        # Propose a memory from the message, but do not save it. The learner decides below.
        # New proposals are ADDED to the waiting cards, each with its own id. Before this fix a new
        # message replaced the card, but the text box kept the old text (same widget key), so
        # approving saved "I prefer short answers" as an episodic question instead of a semantic
        # preference, and it never reached the learner's profile.
        if memory_on:
            ss["pending"].setdefault(learner, [])
            ss["pending"][learner] += [dict(c, cid=uuid.uuid4().hex[:8]) for c in propose(question)]
        st.rerun()

    # Human in the loop: nothing enters long-term memory until the learner approves (and can edit) the
    # card.
    pend = ss["pending"].get(learner) or []
    if pend:
        st.markdown("##### Review before saving")
        for cand in list(pend):
            # Every card has its own id, so its text box, its buttons and the saved memory always
            # belong to the same proposal.
            cid = cand.get("cid", "x")
            with st.container(border=True):
                st.caption(f"Proposed {cand['memory_type']} memory ({cand['event_type']}, topic {cand['topic']}, "
                           f"importance {cand['importance']}). Nothing is stored until you approve.")
                text = st.text_area("Memory text", cand["text"], key=f"pend_{learner}_{cid}")
                b1, b2 = st.columns(2)
                if b1.button("Approve", key=f"ok_{learner}_{cid}", type="primary"):
                    ev = {k: v for k, v in cand.items() if k != "cid"}
                    ev.update(text=text, learner_id=learner, session_id=ss["session_ids"][learner],
                              timestamp=iso(now()), synthetic=True)
                    # Only now is the memory written to the persistent store.
                    status, mid = mm.write(ev)
                    ss["pending"][learner] = [c for c in pend if c.get("cid") != cid]
                    # A brand-new learner now exists in the store; keep them selected.
                    ss["learner_pick"] = learner
                    ss["_force_learner"] = True
                    st.toast(f"{status}: {mid}" if mid else status)
                    st.rerun()
                if b2.button("Reject", key=f"no_{learner}_{cid}"):
                    ss["pending"][learner] = [c for c in pend if c.get("cid") != cid]
                    st.rerun()

# Memory inspector: shows exactly what was retrieved and the exact prompt, so the behaviour is
# transparent.
with insp_col:
    st.markdown("#### Memory inspector")
    last = ss["last"].get(learner)
    if last:
        # Shows which provider and model wrote the last reply, plus the note that memory is the same
        # for all of them.
        st.markdown(f"**Answered by:** {last.get('answered_by', 'offline template')}")
        if last.get("warning"):
            st.warning(last["warning"])
        st.caption(MEMORY_NOTE)
        ctx = last["ctx"]
        if ctx is None or not last.get("memory_on", True):
            st.info("Memory was off for the last turn: nothing personal was read.")
        else:
            # Preferences and facts are always injected when memory is on, whatever the question. The
            # 'kind' column shows which ones the model is told to apply to every answer.
            st.markdown("**Profile injected on every turn (preferences are applied to every answer)**")
            st.dataframe(pd.DataFrame([{"kind": "preference" if m in ctx.preferences else "fact", "id": m.memory_id,
                                        "session": m.session_id, "text": m.text} for m in ctx.profile]),
                         width="stretch", hide_index=True)
            st.markdown(f"**Retrieved memories** (max {mm.policy.k}; score = relevance + {mm.policy.w_rec} x recency + "
                        f"{mm.policy.w_imp} x importance)")
            st.dataframe(pd.DataFrame([r.row() for r in ctx.memories]), width="stretch", hide_index=True)
        if last["refs"]:
            st.markdown("**Shared references (R notes, docs, Stack Overflow; not memory)**")
            st.dataframe(pd.DataFrame([{"id": r["chunk_id"], "kind": r.get("kind"), "title": r.get("title", ""),
                                        "sim": r["similarity"], "source": r.get("source_url")}
                                       for r in last["refs"]]), width="stretch", hide_index=True,
                         column_config={"source": st.column_config.LinkColumn()})
        else:
            st.caption("No reference note matched the last question, so the answer says the notes do not cover it.")
        # The prompt is shown as SYSTEM part + user part, exactly as sent to every provider.
        with st.expander("Exact prompt sent to the model (same for every provider)", expanded=False):
            st.code(last["prompt"], language="text")
    else:
        st.caption("Ask a question to see what was retrieved and the exact prompt.")

    # Learner control: view, edit and delete your own memories.
    st.markdown("#### My memory (view, edit, delete)")
    show_hist = st.checkbox("Include history (superseded, archived, consolidated)")
    mems = mm.store.list(learner)
    rows = []
    for m in mems:
        # Label each row as current, superseded, archived or consolidated.
        state = "current" if mm.is_valid(m) else ("superseded" if m.valid_to else m.status)
        if show_hist or state == "current":
            rows.append({"id": m.memory_id, "state": state, "type": m.memory_type, "session": m.session_id,
                         "importance": m.importance, "text": m.text})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=260)
    ids = [r["id"] for r in rows]
    if ids:
        sel = st.selectbox("Select a memory", ids)
        m = mm.store.get(sel)
        new_text = st.text_area("Edit text", m.text, key=f"edit_{sel}")
        e1, e2 = st.columns(2)
        if e1.button("Save as a new current memory"):
            # An edit does not overwrite: it writes a new current memory and keeps the old one as
            # history.
            nid = mm.correct(sel, new_text)
            st.success(f"{nid} now supersedes {sel}; the old text is kept as history.")
            st.rerun()
        # Deletion asks for confirmation because it cannot be undone.
        if e2.button("Delete this record", type="secondary"):
            ss["confirm_delete"] = sel
        if ss.get("confirm_delete") == sel:
            st.warning(f"Delete {sel}? This removes the text and the vector. It cannot be undone.")
            if st.button("Confirm delete", type="primary"):
                mm.delete(sel)
                ss.pop("confirm_delete", None)
                st.rerun()
