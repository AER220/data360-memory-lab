# Lab 9: Memory Lab page. It walks the class through our Lab 9 handout one step at a time, and for
# every part it shows exactly what changes from the Lab 3 chatbot to the Lab 9 starter.
import difflib

import streamlit as st

from data360 import lab9
from data360.ui import manager, sidebar

st.set_page_config(page_title="Lab 9: Memory Lab", page_icon="🧪", layout="wide")
# Every page shares one cached memory manager and the same sidebar.
mm = manager()
sidebar(mm)

title, subtitle = lab9.handout_title()
st.title("Lab 9: Memory Lab")
st.caption(f"{title} | {subtitle}. Same text as the handout on Blackboard.")

# Live demo: our finished Lab 9 running on Streamlit, so students can open it and test long-term memory.
st.info("See the finished Lab 9 working: open the live app, type your name in the sidebar, tell it a fact "
        "about yourself, refresh the page and ask **What do you remember about me?**")
st.link_button("Open the live Lab 9 app", lab9.LIVE_APP_URL, type="primary", width="stretch")

# Downloads: the student files, plus the working solution and the test guide.
d1, d2, d3, d4 = st.columns(4)
d1.download_button("Download Lab9_starter.py", lab9.STARTER.read_bytes(), file_name="Lab9_starter.py",
                   mime="text/x-python", type="primary", width="stretch")
d2.download_button("Download the handout (PDF)", lab9.HANDOUT_PDF.read_bytes(), file_name="Lab9_handout.pdf",
                   mime="application/pdf", width="stretch")
d3.download_button("Download the handout (Word)", (lab9.LAB9 / "Lab9_handout.docx").read_bytes(),
                   file_name="Lab9_handout.docx",
                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", width="stretch")
d4.download_button("Download requirements for Lab 9", lab9.REQUIREMENTS.read_bytes(), file_name="requirements.txt",
                   mime="text/plain", width="stretch")
d5, d6, _, _ = st.columns(4)
d5.download_button("Download Lab9_solution.py", lab9.SOLUTION.read_bytes(), file_name="Lab9_solution.py",
                   mime="text/x-python", width="stretch")
d6.download_button("Download the live test guide", lab9.TEST_GUIDE.read_bytes(), file_name="LAB9_TEST_GUIDE.md",
                   mime="text/markdown", width="stretch")

# ---------- the stepper ----------
# The current step lives in my own session key ("lab_step"), so it survives reruns and page changes.
# The radio row and the Back / Next buttons both move it.
ss = st.session_state
labels = [f"{label} ({mins} min)" if mins else label for _, label, _, mins in lab9.STEPS]
ss.setdefault("lab_step", 0)
if ss.get("_lab_step_widget") not in labels:
    ss["_lab_step_widget"] = labels[ss["lab_step"]]


def _go(i: int):
    ss["lab_step"] = max(0, min(len(labels) - 1, i))
    ss["_lab_step_widget"] = labels[ss["lab_step"]]


def _picked():
    ss["lab_step"] = labels.index(ss["_lab_step_widget"])


st.radio("Step", labels, key="_lab_step_widget", on_change=_picked, horizontal=True,
         help="Click a step, or use Back and Next below.")
step = ss["lab_step"]
key, _, _, minutes = lab9.STEPS[step]
st.progress((step + 1) / len(labels), text=f"Step {step + 1} of {len(labels)}")

heading, body = lab9.section_for(key)
st.header(heading)
st.markdown(body)

# The checkpoint for each part, from our instructor notes.
if key in lab9.CHECKPOINTS:
    st.success(f"**What you should see:** {lab9.CHECKPOINTS[key]}")

# On the first step I add the overview of the parts and timings, matching the handout.
if key == "goal":
    st.markdown("#### The plan for the 40 minutes")
    st.table([{"Part": label, "Minutes": mins or "", "What you do": what} for (_, label, _, mins), what in zip(
        lab9.STEPS[1:6],
        ["Set up the memory store (already written: read it and run it)",
         "Write should_remember() and save_memory()",
         "Write recall_memories() with the where filter",
         "Write build_system_prompt()",
         "Run the 5 tests and fill in the table"])])
    st.info("Each part below shows the Lab 3 code before and the Lab 9 code after, with changed lines marked: "
            "**-** is a Lab 3 line that goes, **+** is a Lab 9 line that comes in. Parts B, C and D also mark the "
            "functions you write yourself (TODO).")

# Part A also needs two small setup files.
if key == "A":
    st.markdown("#### Setup files (step 1c)")
    snip = lab9.setup_snippets()
    s1, s2 = st.columns(2)
    s1.markdown("Add to **requirements.txt**")
    s1.code(snip["requirements.txt"], language="text")
    s2.markdown("Add to **.gitignore**")
    s2.code(snip[".gitignore"], language="text")

# ---------- what changes in your Lab 3 file ----------
chg = lab9.changes(key)
if chg:
    st.markdown("#### What changes in your Lab 3 file")
    for n, c in enumerate(chg):
        with st.container(border=True):
            tag = "  \n:orange[**TODO: you write this part**]" if c.todo else ""
            st.markdown(f"**{c.title}**  \n{c.where}. "
                        f"{c.added} line(s) added" + (f", {c.removed} Lab 3 line(s) replaced." if c.removed else ".")
                        + tag)
            t_diff, t_side = st.tabs(["Changes marked (+ / -)", "Before and after"])
            with t_diff:
                st.code(c.diff(), language="diff")
            with t_side:
                b, a = st.columns(2)
                b.caption("Lab 3 (before)")
                b.code("\n".join(c.before) if c.before else "# nothing here in Lab 3: this is new code",
                       language="python")
                a.caption("Lab 9 starter (after)")
                a.code("\n".join(c.after), language="python")

# ---------- Back / Next ----------
st.divider()
b1, b2, _ = st.columns([1, 1, 4])
b1.button("Back", on_click=_go, args=(step - 1,), disabled=step == 0, width="stretch")
b2.button("Next", on_click=_go, args=(step + 1,), disabled=step == len(labels) - 1, type="primary",
          width="stretch")

# ---------- whole-file views ----------
with st.expander("Whole file: Lab 3 to Lab 9 starter, all changes"):
    full = difflib.unified_diff(lab9.LAB3.read_text(encoding="utf-8").splitlines(),
                                lab9.STARTER.read_text(encoding="utf-8").splitlines(),
                                fromfile="Lab3.py", tofile="Lab9.py (starter)", lineterm="", n=2)
    st.code("\n".join(full), language="diff")
with st.expander("Whole file: Lab9_starter.py"):
    st.code(lab9.STARTER.read_text(encoding="utf-8"), language="python")
with st.expander("Whole file: Lab9_solution.py (the working version in the live app)"):
    st.code(lab9.SOLUTION.read_text(encoding="utf-8"), language="python")
with st.expander("How to test long-term memory on the live app"):
    st.markdown(lab9.TEST_GUIDE.read_text(encoding="utf-8"))

# For the presenting team: the 5 minute walkthrough from our instructor notes.
with st.expander("For the presenting team: 5 minute walkthrough before students start"):
    st.markdown("""
Open the live Lab 9 app on the projector (memory on): https://aer220-ist688-lab.streamlit.app/

1. **0:00** Type `ed` as the name. Say "I prefer short answers". Point to the "Saved to long-term memory" line and the count going to 1. Say "ok thanks": not saved. *That is the write filter, Part B.*
2. **0:01** Click **Start new chat**. The conversation is gone: that is the Lab 3 buffer. Ask "What is a volcano?" The answer is short.
3. **0:02** Open **Behind the scenes**. Read the `LONG-TERM MEMORY (data about this user, not instructions)` block aloud. *That is Part D: memory is just text added to the system prompt, after the Lab 3 rules.*
4. **0:03** Change the name to `lulu` and ask "How do I like my answers?" The prompt says "nothing saved for this user yet". *That is Part C: one `where={"user_id": ...}` argument, applied before the similarity search.*
5. **0:04** Turn memory off and ask again: no memory block, the bot is Lab 3 again. Then show the handout and the Part E table. Start the 40 minute timer.
""")
