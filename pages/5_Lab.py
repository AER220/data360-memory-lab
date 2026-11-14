# Lab page: the 40 minute student lab, with checkpoints that can be run from the browser.
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from data360.paths import LAB
from data360.ui import manager, sidebar

st.set_page_config(page_title="Lab", page_icon="🧪", layout="wide")
# Every page shares one cached memory manager, so all pages see the same store.
mm = manager()
# Same sidebar everywhere: dataset buttons, reset and the reply model switch.
sidebar(mm)
st.title("Lab: build and test a long-term memory loop")

# lab/ is not a package, so I add it to the import path to reuse lab/check.py.
sys.path.insert(0, str(LAB))
from check import run_checks  # noqa: E402

t_lab, t_check, t_exam, t_inst = st.tabs(["Handout", "Run checkpoints", "Exam questions", "Instructor guide"])

# Tab 1: the student handout, read straight from lab/LAB.md.
with t_lab:
    st.markdown((LAB / "LAB.md").read_text(encoding="utf-8"))

# Tab 2: run the lab's pytest checkpoints on the starter or the solution file from the browser.
with t_check:
    st.markdown("Runs `lab/checks` against your file, exactly like `python lab/check.py`.")
    c1, c2 = st.columns(2)
    target = c1.radio("File to check", ["starter", "solutions"], horizontal=True,
                      format_func=lambda x: f"lab/{x}/memory_lab.py")
    only = c2.selectbox("Exercise", ["all", "ex1", "ex2", "ex3", "ex4", "ex5", "ex6", "stretch_a", "stretch_b"])
    if st.button("Run checkpoints", type="primary"):
        with st.spinner("Running pytest ..."):
            st.session_state["lab_rows"] = run_checks(target, None if only == "all" else only)
    rows = st.session_state.get("lab_rows")
    if rows:
        df = pd.DataFrame(rows)
        n = (df.status == "PASS").sum()
        (st.success if n == len(df) else st.info)(f"{n}/{len(df)} checks pass")
        st.dataframe(df, hide_index=True, width="stretch")
    with st.expander("Starter code (read only here; edit it in your editor)"):
        st.code((LAB / "starter" / "memory_lab.py").read_text(encoding="utf-8"), language="python")

# Tab 3: exam questions, with answers hidden until revealed.
with t_exam:
    text = (LAB / "EXAM_QUESTIONS.md").read_text(encoding="utf-8")
    # I parse the question, body and answer out of EXAM_QUESTIONS.md, so the markdown file stays the
    # single source.
    blocks = re.findall(r"\*\*(\d)\. (.*?)\*\* (.*?)\n<details><summary>Answer</summary>(.*?)</details>", text, re.S)
    for num, title, body, ans in blocks:
        with st.container(border=True):
            st.markdown(f"**{num}. {title}** {body}")
            if st.toggle("Reveal answer", key=f"ans{num}"):
                st.success(ans.strip())

# Tab 4: the instructor guide for the presenting team and TAs.
with t_inst:
    st.caption("For the presenting team and TAs.")
    st.markdown((LAB / "INSTRUCTOR_GUIDE.md").read_text(encoding="utf-8"))
