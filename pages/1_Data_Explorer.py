# Data Explorer page: browse the real reference data and the synthetic learners, and generate new
# learners.
import altair as alt
import pandas as pd
import streamlit as st

from data360 import datasets
from data360.synthetic import generate, write
from data360.ui import manager, sidebar

st.set_page_config(page_title="Data Explorer", page_icon="🔎", layout="wide")
# Every page shares one cached memory manager, so all pages see the same store.
mm = manager()
# Same sidebar everywhere: dataset buttons, reset and the reply model switch.
sidebar(mm)
st.title("Data Explorer")
# Key distinction for the audience: real data is shared reference knowledge, synthetic data is private
# memory.
st.caption("Real data is reference knowledge (the same for every learner). Synthetic data is memory (private to one learner).")

t_docs, t_so, t_pen, t_syn, t_gen = st.tabs(
    ["Real R documentation", "Real Stack Overflow errors", "Penguins (analysis data)", "Synthetic learners", "Generator"])

# Tab 1: the real R documentation chunks used for RAG, with a filter and text search.
with t_docs:
    docs = pd.DataFrame(datasets.reference_docs())
    if docs.empty:
        st.warning("No cached docs. Run `python scripts/fetch_real_data.py` once with internet access.")
    else:
        st.markdown(f"**{len(docs)} chunks** from **{docs.doc_id.nunique()} pages**. Licences in DATA_SOURCES.md.")
        st.altair_chart(alt.Chart(docs).mark_bar().encode(x=alt.X("count()", title="chunks"),
                        y=alt.Y("package", sort="-x"), color="package", tooltip=["package", "count()"]),
                        width="stretch")
        pkg = st.multiselect("Package", sorted(docs.package.unique()))
        q = st.text_input("Search text", key="docq")
        view = docs[docs.package.isin(pkg)] if pkg else docs
        if q:
            view = view[view.text.str.contains(q, case=False, regex=False)]
        st.dataframe(view[["chunk_id", "package", "topic", "text", "source_url"]], width="stretch", height=380,
                     column_config={"source_url": st.column_config.LinkColumn()})

# Tab 2: the real Stack Overflow questions, keeping author and link for the CC BY-SA licence.
with t_so:
    so = pd.DataFrame(datasets.stackoverflow_questions())
    if not so.empty:
        st.markdown(f"**{len(so)} real questions** tagged `[r]` on Stack Overflow, found with error-message searches. "
                    "User content is licensed CC BY-SA (version by post date): each row keeps its author and link.")
        st.altair_chart(alt.Chart(so).mark_bar().encode(x=alt.X("count()", title="questions"),
                        y=alt.Y("error_query", sort="-x", title="error searched"), color="topic"),
                        width="stretch")
        st.dataframe(so[["title", "score", "answer_count", "error_query", "author", "created_utc", "link"]],
                     width="stretch", height=360, column_config={"link": st.column_config.LinkColumn()})
        st.caption("These real errors are what the synthetic generator models its learners' error events on.")

# Tab 3: the penguins data, which is analysis data, neither memory nor reference.
with t_pen:
    pen = datasets.penguins()
    st.markdown("The **palmerpenguins** data (CC0) is what IST 387/687 style examples analyse in R. "
                "It is analysis data: neither memory nor reference text.")
    c = st.columns(3)
    c[0].metric("Rows", len(pen))
    c[1].metric("Species", pen.species.nunique())
    c[2].metric("Rows with missing values", int(pen.isna().any(axis=1).sum()))
    st.altair_chart(alt.Chart(pen.dropna()).mark_circle(size=50, opacity=0.7).encode(
        x=alt.X("flipper_length_mm", scale=alt.Scale(zero=False)), y=alt.Y("body_mass_g", scale=alt.Scale(zero=False)),
        color="species", shape="species", tooltip=list(pen.columns)), width="stretch")
    # Every chart gets a text description for accessibility.
    st.caption("Text description (for screen readers): body mass rises with flipper length for all three species; "
               "Gentoo penguins have the longest flippers and heaviest bodies.")
    st.code('library(dplyr)\npenguins |>\n  group_by(species) |>\n  summarise(mass = mean(body_mass_g, na.rm = TRUE))', language="r")
    st.dataframe(pen.groupby("species")[["bill_length_mm", "flipper_length_mm", "body_mass_g"]].mean().round(1))

# Tab 4: browse the fictional learners' event histories and the probe questions used by the
# evaluation.
with t_syn:
    which = st.radio("Dataset", ["canonical", "generated"], horizontal=True,
                     format_func=lambda x: {"canonical": "Course set (hand written, 3 learners)",
                                            "generated": "Generated (seeded)"}[x])
    events, probes = datasets.load_dataset(which)
    ev = pd.DataFrame(events)
    if ev.empty:
        st.warning("No events. Use the Generator tab.")
    else:
        c = st.columns(4)
        c[0].metric("Learners", ev.learner_id.nunique())
        c[1].metric("Sessions", ev.session_id.nunique())
        c[2].metric("Events", len(ev))
        c[3].metric("Probe questions", len(probes))
        st.altair_chart(alt.Chart(ev).mark_bar().encode(x="learner_id", y="count()", color="event_type",
                        tooltip=["learner_id", "event_type", "count()"]), width="stretch")
        lid = st.selectbox("Learner", sorted(ev.learner_id.unique()))
        cols = [c for c in ["event_id", "session_id", "timestamp", "topic", "event_type", "memory_type", "importance",
                            "supersedes", "text", "source_url"] if c in ev.columns]
        st.dataframe(ev[ev.learner_id == lid][cols], width="stretch", height=320,
                     column_config={"source_url": st.column_config.LinkColumn("real SO thread")})
        st.markdown("**Probe questions** (used by the Evaluation page)")
        st.dataframe(pd.DataFrame(probes).query("learner_id == @lid"), width="stretch")

# Tab 5: generate new learners with a seed. The preview updates live; nothing is saved until the
# button is pressed.
with t_gen:
    st.markdown("Generate new fictional learners. Same seed, same data. Error events are modelled on the real "
                "Stack Overflow questions and link to one of them.")
    c = st.columns(4)
    n = c[0].slider("Learners", 2, 40, 12)
    seed = c[1].number_input("Seed", 0, 10_000, 360)
    p_env = c[2].slider("P(environment change)", 0.0, 1.0, 0.5)
    p_rep = c[3].slider("P(repeated error)", 0.0, 1.0, 0.4)
    ev2, pr2 = generate(n, int(seed), p_env_change=p_env, p_repeat=p_rep)
    st.write(f"Preview: **{len(ev2)} events**, **{len(pr2)} probes**.")
    st.dataframe(pd.DataFrame(ev2).head(30), width="stretch", height=280)
    # Saving writes the files only. Loading them into memory is a separate sidebar button, so the
    # learner store is never changed by surprise.
    if st.button("Save as the generated dataset", type="primary"):
        write(ev2, pr2)
        st.success("Saved to data/synthetic/generated_events.jsonl and generated_probes.jsonl. "
                   "Click 'Load generated learners' in the sidebar to put them in the memory store.")
