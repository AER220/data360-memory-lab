# Evaluation page: compares no memory, naive memory and the Data360 policy, and runs the PASS/FAIL
# policy checks.
import altair as alt
import pandas as pd
import streamlit as st

from data360.evaluate import CONDITIONS, evaluate, policy_checks
from data360.ui import manager, sidebar

st.set_page_config(page_title="Evaluation", page_icon="📊", layout="wide")
# Every page shares one cached memory manager, so all pages see the same store.
mm = manager()
# Same sidebar everywhere: dataset buttons, reset and the reply model switch.
sidebar(mm)
st.title("Evaluation: memory vs no memory")
st.markdown("""
Each condition builds a **throwaway** store from the same synthetic events (your chat store is not touched) and
answers the probe questions. Abilities follow LongMemEval's categories (information extraction, multi-session,
knowledge update, temporal reasoning, abstention) plus privacy isolation.

* **recall@context**: share of expected memory ids that were placed in the prompt (profile + top 3).
* **repetition burden**: share of answerable probes where nothing useful was in the prompt, so the learner must explain again.
* **stale fact / other learner's memory**: probes whose prompt contained a superseded fact or another learner's memory. Should be 0.
* **correct abstentions**: probes with no stored answer where the reply said it does not know. The no-memory baseline
  abstains on everything personal, so its 100% here is trivial.
""")
c1, c2 = st.columns([2, 3])
# Choose the dataset and which conditions to compare.
dataset = c1.radio("Dataset", ["canonical", "generated"], horizontal=True,
                   format_func=lambda x: {"canonical": "Course set (14 probes)", "generated": "Generated (seeded)"}[x])
conds = c2.multiselect("Conditions", CONDITIONS, default=CONDITIONS)
# Results are kept in session state so the charts stay after other widgets cause a rerun.
if st.button("Run evaluation", type="primary"):
    with st.spinner("Building stores and answering probes ..."):
        st.session_state["eval"] = evaluate(dataset, conds)
        st.session_state["eval_ds"] = dataset

if "eval" in st.session_state:
    summary, detail = st.session_state["eval"]
    st.markdown(f"#### Results ({st.session_state['eval_ds']})")
    st.dataframe(summary, hide_index=True, width="stretch")
    # Reshape the summary so each metric becomes a small bar chart per condition.
    long = summary.melt(id_vars="condition", value_vars=["recall@context", "probes answered from memory", "repetition burden"])
    st.altair_chart(alt.Chart(long).mark_bar().encode(
        x=alt.X("condition:N", sort=CONDITIONS, title=None), y=alt.Y("value:Q", scale=alt.Scale(domain=[0, 1])),
        color="condition:N", column=alt.Column("variable:N", title=None), tooltip=["condition", "variable", "value"]
    ).properties(width=230, height=240))
    # Stale facts and cross-learner leaks: the Data360 policy should be at zero here.
    leaks = summary.melt(id_vars="condition", value_vars=["probes with stale fact", "probes with other learner's memory"])
    st.altair_chart(alt.Chart(leaks).mark_bar().encode(
        x=alt.X("condition:N", sort=CONDITIONS, title=None), y="value:Q", color="variable:N", xOffset="variable:N",
        tooltip=["condition", "variable", "value"]).properties(height=240), width="stretch")
    # Recall broken down by ability (knowledge update, multi-session, and so on).
    by_ab = detail.groupby(["condition", "ability"]).apply(
        lambda g: g.hits.sum() / max(1, g.n_expected.sum()), include_groups=False).reset_index(name="recall")
    st.markdown("**Recall by ability**")
    st.dataframe(by_ab.pivot(index="ability", columns="condition", values="recall").round(2), width="stretch")
    with st.expander("Probe-level detail"):
        cond = st.selectbox("Condition", detail.condition.unique())
        st.dataframe(detail[detail.condition == cond], hide_index=True, width="stretch")

st.markdown("### Policy checks (PASS / FAIL)")
# The restart checks can open the store from a separate Python process to prove persistence.
fresh = st.checkbox("Use a separate Python process for restart checks", value=True)
if st.button("Run policy checks"):
    with st.spinner("Running checks ..."):
        st.session_state["checks"] = policy_checks(fresh_process=fresh)
if "checks" in st.session_state:
    chk = pd.DataFrame(st.session_state["checks"])
    n = (chk.result == "PASS").sum()
    # Green when every check passes, red otherwise.
    (st.success if n == len(chk) else st.error)(f"{n}/{len(chk)} checks passed")
    st.dataframe(chk, hide_index=True, width="stretch")
