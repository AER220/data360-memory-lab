"""Data360-Memory: Overview page. Run with:  streamlit run app.py"""
# Overview page: what long-term memory is, the loop diagram and what data the project contains.
import streamlit as st

from data360 import datasets
from data360.ui import DISCLAIMER, manager, sidebar

st.set_page_config(page_title="Overview", page_icon="🧠", layout="wide")
# Every page shares one cached memory manager, so all pages see the same store.
mm = manager()
# Same sidebar everywhere: dataset buttons, reset and the reply model switch.
sidebar(mm)

st.title("Data360-Memory")
st.subheader("Long-term memory for an R data science study companion, with a hands-on student lab")
# I show the synthetic-data disclaimer up front, because the app must never hold real student records.
st.info(DISCLAIMER)

st.markdown("""
A normal chatbot forgets a learner when the session ends, so students repeat their setup, their errors and
their preferences every time. **Data360-Memory** keeps approved facts **outside the model**, in a persistent
store, and reads them back in later sessions, even after the program restarts.

It keeps three kinds of memory per learner:

| Type | Example | Behaviour |
|---|---|---|
| **Episodic** | `Got Error: could not find function "%>%"` | past events; can be consolidated or forgotten |
| **Semantic** | `I switched to Posit Cloud` | current facts and preferences; a correction supersedes the old fact |
| **Procedural** | `Checking loaded packages before debugging the pipe helped` | tutoring moves that worked |
""")

# A diagram of the loop the other pages demonstrate: filter, score, prompt, reply, propose, approve,
# store.
st.markdown("### The memory loop")
st.graphviz_chart("""
digraph G {
  rankdir=TB; nodesep=0.5; node [shape=box, style="rounded,filled", fillcolor="#E7EEF6", fontname="Helvetica", fontsize=13];
  Q [label="Learner question"]; F [label="Filter: this learner,\\ncurrent records only"];
  S [label="Score: relevance +\\nrecency + importance"]; P [label="Prompt: profile + top 3\\nmemories + reference notes\\n(labelled as data)"];
  A [label="Reply + Sources block\\n(offline, OpenAI or Anthropic;\\nsame prompt)"]; W [label="Propose memory\\nlearner approves"];
  DB [label="Persistent store\\n(SQLite + vectors)", shape=cylinder, fillcolor="#F6E7D8"];
  R [label="Reference knowledge (shared)\\nR reference notes + R docs\\n+ Stack Overflow", shape=cylinder, fillcolor="#E3F1E3"];
  M [label="Maintenance: update,\\nconsolidate, forget, delete", fillcolor="#FCEBD5"];
  {rank=same; Q; F; S;} {rank=same; P; R;} {rank=same; A; W; DB; M;}
  Q -> F -> S -> P -> A -> W -> DB; DB -> F [style=dashed, label=" read"]; R -> P; M -> DB;
}
""", width="content")

# Counts come straight from the data files, so the numbers on screen are always true.
st.markdown("### What is in this project")
m = datasets.manifest()
ev_c, ev_g = datasets.canonical_events(), datasets.generated_events()
c = st.columns(6)
notes = datasets.r_notes()
c[0].metric("R reference notes", len(notes), help=f"Our own wording, {len({n['source_url'] for n in notes})} verified "
            "official documentation links, covering lectures 1 to 12 of IST 387/687")
c[1].metric("Real doc chunks", len(datasets.reference_docs()), help="tidyverse, base R, jsonlite, palmerpenguins pages")
c[2].metric("Real Stack Overflow questions", len(datasets.stackoverflow_questions()))
c[3].metric("Penguins rows (real, CC0)", len(datasets.penguins()))
c[4].metric("Course-set events", len(ev_c), help="3 fictional learners, written by hand")
c[5].metric("Generated events", len(ev_g), help=f"{len({e['learner_id'] for e in ev_g})} seeded synthetic learners")
# Shows when the real data was fetched, from data/real/manifest.json.
if m:
    st.caption(f"Real data fetched {m.get('fetched_utc', '?')} (UTC) and cached in data/real/. See DATA_SOURCES.md.")

st.markdown("""
### How to use the pages
1. **Data Explorer**: browse the real reference data and the synthetic learner histories; generate new learners with a seed.
2. **Chat and Memory**: talk to Data360 as a learner (or create your own user with **+ new learner**), approve memories, and inspect the exact prompt. Every answer ends with a **Sources** block.
3. **Memory Timeline**: see facts being written, superseded, consolidated and forgotten over the semester.
4. **Evaluation**: compare no memory, naive memory and the Data360 policy, and run the PASS/FAIL policy checks.
5. **Lab 9: Memory Lab**: the 40 minute student lab as clickable steps, showing what changes from the Lab 3 chatbot to Lab 9 in every part.

Start by clicking **Load course set (3 learners)** in the sidebar.
""")
st.caption("Use Data360 only where the instructor and the assignment allow AI help. Never for prohibited assessments.")
