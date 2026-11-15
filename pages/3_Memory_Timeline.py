# Memory Timeline page: how one learner's memory changes over the term, plus maintenance
# (consolidate, forget, restore).
from datetime import datetime, time, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from data360.timeutil import iso, parse
from data360.ui import manager, sidebar, visible_learners

st.set_page_config(page_title="Memory Timeline", page_icon="🕒", layout="wide")
# Every page shares one cached memory manager, so all pages see the same store.
mm = manager()
# Same sidebar everywhere: dataset buttons, reset and the reply model switch.
sidebar(mm)
st.title("Memory Timeline")
st.caption("How one learner's memory changes over the semester: written, superseded, consolidated, forgotten.")

# Nothing to show until a dataset is loaded, so I stop early with a hint. Like the Chat page, I list the
# demo learners and the users created in this browser session (with saved memories), not every
# classmate's user.
stored = set(mm.store.learners())
learners = [lid for lid in visible_learners(mm, st.session_state.get("my_users", [])) if lid in stored]
if not learners:
    st.warning("No memories to show yet. Click **Load course set (3 learners)** in the sidebar, or save a memory "
               "on the Chat page first.")
    st.stop()
c1, c2 = st.columns(2)
learner = c1.selectbox("Learner", learners)
# The date picker lets you view memory as it was on any day, which shows supersede and forgetting over
# time.
as_of_date = c2.date_input("View the store as of", value=datetime.now().date())
as_of = iso(datetime.combine(as_of_date, time(23, 59)).astimezone())

mems = mm.store.list(learner)


# Works out a memory's state on the chosen date, mirroring MemoryManager.is_valid.
def state(m):
    if parse(m.created_at) > parse(as_of):
        return "not yet written"
    if m.valid_to and parse(m.valid_to) <= parse(as_of):
        return "superseded"
    return "current" if m.status == "active" else m.status


# One row per memory with its state and strength on the chosen date.
df = pd.DataFrame([{"id": m.memory_id, "created": parse(m.created_at).isoformat(), "type": m.memory_type,
                    "event": m.event_type, "state": state(m), "importance": m.importance, "session": m.session_id,
                    "text": m.text, "superseded_by": m.superseded_by, "strength": round(mm.strength(m, as_of), 3)}
                   for m in mems])
c = st.columns(5)
for i, s in enumerate(["current", "superseded", "consolidated", "archived", "not yet written"]):
    c[i].metric(s, int((df.state == s).sum()))

# Timeline chart: position = when it was written, colour = its state on the chosen date.
chart = alt.Chart(df).mark_point(filled=True, opacity=0.8).encode(
    x=alt.X("created:T", title="written at"), y=alt.Y("event:N", title="event type"),
    shape=alt.Shape("type:N", title="memory type"),
    size=alt.Size("importance:Q", scale=alt.Scale(domain=[1, 10], range=[40, 420])),
    color=alt.Color("state:N", scale=alt.Scale(domain=["current", "superseded", "consolidated", "archived", "not yet written"],
                                                range=["#1f7a4d", "#c2410c", "#6d5bd0", "#8a8a8a", "#d9d9d9"])),
    tooltip=["id", "session", "event", "state", "importance", "strength", "text"]).properties(height=260)
st.altair_chart(chart, width="stretch")
st.caption("Text description: each mark is one memory, placed by the time it was written and its event type. "
           "Colour shows its state on the chosen date, shape its memory type, size its importance.")

# List of corrections: which fact replaced which.
sup = df[df.superseded_by != ""]
if not sup.empty:
    st.markdown("**Updates (corrections)**: the old fact is kept as history and is skipped by retrieval after the correction.")
    st.dataframe(sup[["id", "text", "superseded_by"]], hide_index=True, width="stretch")

st.markdown("### Forgetting curve")
st.markdown("strength = importance/10 x 0.5^(age / half-life), where the half-life grows by 50% each time the memory "
            "is retrieved (a spacing effect). Weak episodic memories can be archived; profile facts are kept.")
# The slider changes the half-life on a copy of the policy, so exploring the curve never changes the
# stored data.
half = st.slider("Decay half-life (days)", 5, 90, int(mm.policy.decay_half_life_days))
mm_view = mm.with_policy(decay_half_life_days=float(half))
cur = [m for m in mems if state(m) == "current"]
if cur:
    start = min(parse(m.created_at) for m in cur)
    end = parse(as_of) + timedelta(days=60)
    pts = []
    # Sample 41 points between the first memory and 60 days after the chosen date to draw each
    # strength curve.
    for i in range(41):
        t = start + (end - start) * i / 40
        for m in cur:
            if parse(m.created_at) <= t:
                pts.append({"date": t.isoformat(), "id": m.memory_id, "type": m.memory_type,
                            "strength": mm_view.strength(m, t)})
    curve = alt.Chart(pd.DataFrame(pts)).mark_line().encode(
        x="date:T", y=alt.Y("strength:Q", scale=alt.Scale(domain=[0, 1])), color="type:N", detail="id:N",
        tooltip=["id", "type", "strength"])
    st.altair_chart(curve, width="stretch")

st.markdown("### Maintenance")
m1, m2, m3 = st.columns(3)
with m1:
    st.markdown("**Consolidate**: merge 2+ episodic memories on the same topic into one semantic summary.")
    # Maintenance buttons call the same MemoryManager operations the evaluation tests.
    if st.button("Consolidate now"):
        ids = mm.consolidate(learner, as_of=as_of)
        st.success(f"Created {ids}" if ids else "Nothing to consolidate.")
        st.rerun()
with m2:
    thr = st.slider("Forget threshold", 0.0, 0.5, 0.1, 0.01)
    # Forgetting archives (does not delete) episodic memories below the threshold.
    if st.button("Forget weak episodic memories"):
        ids = mm_view.forget(learner, as_of=as_of, threshold=thr)
        st.success(f"Archived {ids}" if ids else "Nothing below the threshold.")
        st.rerun()
with m3:
    # Anything archived or consolidated can be restored, so maintenance is reversible.
    hidden = [m.memory_id for m in mems if m.status in ("archived", "consolidated")]
    if hidden:
        r = st.selectbox("Restore an archived or consolidated memory", hidden)
        if st.button("Restore"):
            mm.restore(r)
            st.rerun()
    else:
        st.caption("No archived or consolidated memories.")

# The audit log shows every write, supersede, consolidate, archive and delete for this learner.
st.markdown("### Audit log")
st.dataframe(pd.DataFrame(mm.store.audit(learner)), width="stretch", hide_index=True, height=260)
