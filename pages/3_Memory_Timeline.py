from datetime import datetime, time, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from data360.timeutil import iso, parse
from data360.ui import manager, sidebar

st.set_page_config(page_title="Memory Timeline", page_icon="🕒", layout="wide")
mm = manager()
sidebar(mm)
st.title("Memory Timeline")
st.caption("How one learner's memory changes over the semester: written, superseded, consolidated, forgotten.")

learners = mm.store.learners()
if not learners:
    st.warning("The store is empty. Click **Load course set (3 learners)** in the sidebar.")
    st.stop()
c1, c2 = st.columns(2)
learner = c1.selectbox("Learner", learners)
as_of_date = c2.date_input("View the store as of", value=datetime.now().date())
as_of = iso(datetime.combine(as_of_date, time(23, 59)).astimezone())

mems = mm.store.list(learner)


def state(m):
    if parse(m.created_at) > parse(as_of):
        return "not yet written"
    if m.valid_to and parse(m.valid_to) <= parse(as_of):
        return "superseded"
    return "current" if m.status == "active" else m.status


df = pd.DataFrame([{"id": m.memory_id, "created": parse(m.created_at).isoformat(), "type": m.memory_type,
                    "event": m.event_type, "state": state(m), "importance": m.importance, "session": m.session_id,
                    "text": m.text, "superseded_by": m.superseded_by, "strength": round(mm.strength(m, as_of), 3)}
                   for m in mems])
c = st.columns(5)
for i, s in enumerate(["current", "superseded", "consolidated", "archived", "not yet written"]):
    c[i].metric(s, int((df.state == s).sum()))

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

sup = df[df.superseded_by != ""]
if not sup.empty:
    st.markdown("**Updates (corrections)**: the old fact is kept as history and is skipped by retrieval after the correction.")
    st.dataframe(sup[["id", "text", "superseded_by"]], hide_index=True, width="stretch")

st.markdown("### Forgetting curve")
st.markdown("strength = importance/10 x 0.5^(age / half-life), where the half-life grows by 50% each time the memory "
            "is retrieved (a spacing effect). Weak episodic memories can be archived; profile facts are kept.")
half = st.slider("Decay half-life (days)", 5, 90, int(mm.policy.decay_half_life_days))
mm_view = mm.with_policy(decay_half_life_days=float(half))
cur = [m for m in mems if state(m) == "current"]
if cur:
    start = min(parse(m.created_at) for m in cur)
    end = parse(as_of) + timedelta(days=60)
    pts = []
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
    if st.button("Consolidate now"):
        ids = mm.consolidate(learner, as_of=as_of)
        st.success(f"Created {ids}" if ids else "Nothing to consolidate.")
        st.rerun()
with m2:
    thr = st.slider("Forget threshold", 0.0, 0.5, 0.1, 0.01)
    if st.button("Forget weak episodic memories"):
        ids = mm_view.forget(learner, as_of=as_of, threshold=thr)
        st.success(f"Archived {ids}" if ids else "Nothing below the threshold.")
        st.rerun()
with m3:
    hidden = [m.memory_id for m in mems if m.status in ("archived", "consolidated")]
    if hidden:
        r = st.selectbox("Restore an archived or consolidated memory", hidden)
        if st.button("Restore"):
            mm.restore(r)
            st.rerun()
    else:
        st.caption("No archived or consolidated memories.")

st.markdown("### Audit log")
st.dataframe(pd.DataFrame(mm.store.audit(learner)), width="stretch", hide_index=True, height=260)
