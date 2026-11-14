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
from data360.ui import DISCLAIMER, llm_choice, manager, sidebar

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

# Pick which fictional learner you are. Memory is always looked up for this learner only.
learners = mm.store.learners()
c1, c2, c3 = st.columns([2, 2, 2])
choice = c1.selectbox("Learner", learners + ["+ new learner"], index=0 if learners else 0)
if choice == "+ new learner":
    new = c1.text_input("New learner id (pseudonym only)", value="syn_new01")
    learner = new.strip() or "syn_new01"
else:
    learner = choice
# Each chat gets a session id, so approved memories record which session they came from.
ss.setdefault("session_ids", {})
ss["session_ids"].setdefault(learner, f"live_{uuid.uuid4().hex[:4]}")
if c2.button("Start a new session"):
    ss["session_ids"][learner] = f"live_{uuid.uuid4().hex[:4]}"
    ss["chat"][learner] = []
c2.caption(f"Session `{ss['session_ids'][learner]}`. Memories approved now carry this session id.")
# Memory on/off switch for the live comparison with a normal chatbot.
memory_on = c3.toggle("Use long-term memory", value=True,
                      help="Off: no personal memory is read or written. Reference docs stay available.")
use_refs = c3.toggle("Use reference docs (RAG)", value=True)

if not learners:
    st.warning("The store is empty. Click **Load course set (3 learners)** in the sidebar, or create a new learner and start talking.")

chat_col, insp_col = st.columns([3, 2])

with chat_col:
    st.markdown("#### Chat")
    st.caption("Try: `Which R environment do I use now?`, `Why do I keep getting could not find function %>%?`, "
               "`I prefer comments on every line of R code.`, `What is my favourite colour?`")
    # Redraw the conversation, including any fallback warning and the 'Answered by' label of each
    # reply.
    for msg in ss["chat"].get(learner, []):
        with st.chat_message(msg["role"]):
            if msg.get("warning"):
                st.warning(msg["warning"])
            st.markdown(msg["content"])
            if msg.get("answered_by"):
                st.caption(f"Answered by: {msg['answered_by']}")
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
            {"role": "assistant", "content": ans.text, "answered_by": ans.label, "warning": ans.warning}])
        ss["last"][learner] = {"ctx": ctx, "prompt": prompt, "refs": refs, "answered_by": ans.label,
                               "requested": chosen, "warning": ans.warning}
        # Propose a memory from the message, but do not save it. The learner decides below.
        ss["pending"][learner] = [dict(c, text=c["text"]) for c in propose(question)] if memory_on else []
        st.rerun()

    # Human in the loop: nothing enters long-term memory until the learner approves (and can edit) the
    # card.
    pend = ss["pending"].get(learner) or []
    if pend:
        st.markdown("##### Review before saving")
        for i, cand in enumerate(pend):
            with st.container(border=True):
                st.caption(f"Proposed {cand['memory_type']} memory ({cand['event_type']}, topic {cand['topic']}, "
                           f"importance {cand['importance']}). Nothing is stored until you approve.")
                text = st.text_area("Memory text", cand["text"], key=f"pend_{learner}_{i}")
                b1, b2 = st.columns(2)
                if b1.button("Approve", key=f"ok_{learner}_{i}", type="primary"):
                    ev = dict(cand, text=text, learner_id=learner, session_id=ss["session_ids"][learner],
                              timestamp=iso(now()), synthetic=True)
                    # Only now is the memory written to the persistent store.
                    status, mid = mm.write(ev)
                    ss["pending"][learner] = []
                    st.toast(f"{status}: {mid}" if mid else status)
                    st.rerun()
                if b2.button("Reject", key=f"no_{learner}_{i}"):
                    ss["pending"][learner] = []
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
        if ctx is None:
            st.info("Memory was off for the last turn: nothing personal was read.")
        else:
            st.markdown("**Profile injected (current facts)**")
            st.dataframe(pd.DataFrame([{"id": m.memory_id, "session": m.session_id, "text": m.text} for m in ctx.profile]),
                         width="stretch", hide_index=True)
            st.markdown(f"**Retrieved memories** (max {mm.policy.k}; score = relevance + {mm.policy.w_rec} x recency + "
                        f"{mm.policy.w_imp} x importance)")
            st.dataframe(pd.DataFrame([r.row() for r in ctx.memories]), width="stretch", hide_index=True)
        if last["refs"]:
            st.markdown("**Reference docs (shared, not memory)**")
            st.dataframe(pd.DataFrame([{"id": r["chunk_id"], "sim": r["similarity"], "source": r.get("source_url")}
                                       for r in last["refs"]]), width="stretch", hide_index=True,
                         column_config={"source": st.column_config.LinkColumn()})
        with st.expander("Exact prompt sent to the model", expanded=False):
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
