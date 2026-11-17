"""Tests for the Lab 9: Memory Lab page and the lab9/ files it shows."""
# I check that the page loads, that every step from the handout can be reached by clicking, that each
# part shows its Lab 3 to Lab 9 changes, and that the solution and live demo link are offered.
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from data360 import lab9

ROOT = Path(__file__).resolve().parents[1]
DASHES = re.compile("[\u2013\u2014]")


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA360_DB", str(tmp_path / "lab.db"))
    monkeypatch.chdir(ROOT)


def _page():
    at = AppTest.from_file(str(ROOT / "pages/5_Lab.py"), default_timeout=120)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _text(at):
    parts = [m.value for m in at.markdown] + [h.value for h in at.header] + [c.value for c in at.code]
    parts += [s.value for s in at.success] + [i.value for i in at.info]
    return "\n".join(parts)


# The student files, the solution and the test guide are all in the repo.
def test_lab9_files_present():
    for f in ["HANDOUT.md", "Lab9_starter.py", "Lab3.py", "Lab9_handout.pdf", "Lab9_handout.docx", "requirements_lab9.txt",
              "Lab9_solution.py", "LAB9_TEST_GUIDE.md"]:
        assert (ROOT / "lab9" / f).exists(), f
    assert lab9.LIVE_APP_URL in lab9.TEST_GUIDE.read_text(encoding="utf-8")
    assert not (ROOT / "lab").exists(), "the old Data360 lab is retired"


# The handout markdown has the same sections and timings as the PDF handout.
def test_handout_sections_and_timings():
    heads = list(lab9.handout_sections())
    assert heads[0] == "Goal" and heads[-2:] == ["If you have time (stretch)", "Submit"]
    for part, mins in [("A", 8), ("B", 10), ("C", 10), ("D", 5), ("E", 5)]:
        head, body = lab9.section_for(part)
        assert head.startswith(f"Part {part}:") and f"about {mins} minutes" in head
    assert "| 5. Restart |" in lab9.section_for("E")[1]
    submit = lab9.section_for("submit")[1]
    assert "(1) What can the Lab 3 buffer do" in submit and "(2) Name one risk" in submit
    assert not DASHES.search((ROOT / "lab9" / "HANDOUT.md").read_text(encoding="utf-8"))


# Every part with code shows Lab 3 before and Lab 9 after; the student's TODO functions are marked.
def test_changes_per_part():
    todo_funcs = {"B": ["def should_remember", "def save_memory"], "C": ["def recall_memories"],
                  "D": ["def build_system_prompt"], "stretch": ["def forget_user"]}
    for part, funcs in todo_funcs.items():
        chg = lab9.changes(part)
        todo = "\n".join("\n".join(c.after) for c in chg if c.todo)
        for f in funcs:
            assert f in todo, (part, f)
    a = lab9.changes("A")
    assert any("PersistentClient" in "\n".join(c.after) for c in a)
    # The Lab 3 chat call is replaced: the system prompt now comes from build_system_prompt().
    d = "\n".join(c.diff() for c in lab9.changes("D"))
    assert '-     messages_to_send = [{"role": "system", "content": SYSTEM_PROMPT}]' in d
    assert '+     messages_to_send = [{"role": "system", "content": system_prompt}]' in d
    # Starter TODO lines are shown, never filled-in solution code.
    shown = "\n".join(c.diff() for k in ("A", "B", "C", "D", "stretch") for c in lab9.changes(k))
    assert "collection.upsert(" not in shown.replace("call collection.upsert(", "")
    assert "return []   # <- replace this line" in shown


# The page loads, starts at the Goal and has download buttons for the starter and the handout.
def test_lab_page_loads():
    at = _page()
    assert at.title[0].value == "Lab 9: Memory Lab"
    assert "Goal" in _text(at) and "Lab9_starter.py" in _text(at)
    radio = at.radio[0]
    assert radio.options[:6] == ["Goal", "Part A: Setup (8 min)", "Part B: Write (10 min)", "Part C: Read (10 min)",
                                 "Part D: Inject (5 min)", "Part E: Test (5 min)"]
    assert radio.options[6:] == ["Stretch", "Submit"]


# Clicking through every step shows Parts A to E, the test table, the stretch and the submit text.
def test_click_through_all_steps():
    at = _page()
    expect = {1: ("Part A: Set up the memory store", "PersistentClient"),
              2: ("Part B: Write memories", "def should_remember"),
              3: ("Part C: Read memories", 'where={"user_id": user_id}'),
              4: ("Part D: Inject memories into the prompt", "def build_system_prompt"),
              5: ("Part E: Test it", "| 4. Second user |"),
              6: ("If you have time (stretch)", "def forget_user"),
              7: ("Submit", "Upload `Lab9.py` to Blackboard")}
    for i in range(1, 8):
        next(b for b in at.button if b.label == "Next").click().run()
        assert not at.exception
        head, needle = expect[i]
        assert at.header[0].value.startswith(head), (i, at.header[0].value)
        assert needle in _text(at) or any(needle in t.value for t in at.table), (i, needle)
    # Back returns to the stretch step, and the radio can jump straight to Part C.
    next(b for b in at.button if b.label == "Back").click().run()
    assert at.header[0].value.startswith("If you have time")
    at.radio[0].set_value("Part C: Read (10 min)").run()
    assert at.header[0].value.startswith("Part C") and "What you should see" in _text(at)


# The navigation title in the entry point is the one Edouard asked for.
def test_navigation_title():
    assert 'title="Lab 9: Memory Lab"' in (ROOT / "app.py").read_text(encoding="utf-8")


# The page links the live Lab 9 app and offers the solution and the test guide for download.
def test_live_link_and_solution_downloads():
    at = _page()
    src = (ROOT / "pages/5_Lab.py").read_text(encoding="utf-8")
    assert "lab9.LIVE_APP_URL" in src and "st.link_button" in src
    assert "Download Lab9_solution.py" in src and "Download the live test guide" in src
    assert "def should_remember" in "\n".join(c.value for c in at.code)


# The working solution has all four TODO parts filled in.
def test_solution_complete():
    sol = lab9.SOLUTION.read_text(encoding="utf-8")
    assert "collection.upsert(" in sol and 'where = {"user_id": user_id}' in sol
    assert "# <- replace this line" not in sol
