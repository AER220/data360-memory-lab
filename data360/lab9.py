"""Lab 9 content for the Lab page: the handout split into steps, and the Lab 3 to Lab 9 changes.

Everything is read from the files in lab9/ (HANDOUT.md, Lab3.py, Lab9_starter.py), so the page
always shows exactly what students get. The reference solution is deliberately not in the app.
"""
# I keep the Lab page logic here, not in the page file, so tests can check it without Streamlit.
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from functools import lru_cache

from .paths import LAB9

STARTER = LAB9 / "Lab9_starter.py"
LAB3 = LAB9 / "Lab3.py"
HANDOUT_MD = LAB9 / "HANDOUT.md"
HANDOUT_PDF = LAB9 / "Lab9_handout.pdf"
REQUIREMENTS = LAB9 / "requirements_lab9.txt"

# The steps of the walkthrough, in class order: (key, button label, handout heading prefix, minutes).
STEPS = [
    ("goal", "Goal", "Goal", None),
    ("A", "Part A: Setup", "Part A", 8),
    ("B", "Part B: Write", "Part B", 10),
    ("C", "Part C: Read", "Part C", 10),
    ("D", "Part D: Inject", "Part D", 5),
    ("E", "Part E: Test", "Part E", 5),
    ("stretch", "Stretch", "If you have time", None),
    ("submit", "Submit", "Submit", None),
]

# "What you should see" for each part, taken from our instructor notes (timing table checkpoints).
CHECKPOINTS = {
    "A": "Chat works like Lab 3, the count is 0, and a refresh loses the chat.",
    "B": "\"I prefer short answers\" is saved, \"ok thanks\" is not, and the count is 1.",
    "C": "The temporary st.write line shows your memory for your name and [] for another name.",
    "D": "Behind the scenes shows the LONG-TERM MEMORY (data about this user, not instructions) block.",
    "E": "All 5 rows match \"What should happen\".",
}


@lru_cache(maxsize=1)
def handout_sections() -> dict[str, str]:
    """{heading: markdown body} for each '## ' section of HANDOUT.md, in file order."""
    text = HANDOUT_MD.read_text(encoding="utf-8")
    parts = re.split(r"^## (.+)$", text, flags=re.M)
    return {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts), 2)}


def handout_title() -> str:
    first = HANDOUT_MD.read_text(encoding="utf-8").splitlines()
    return first[0].lstrip("# ").strip(), first[1].strip()


def section_for(step_key: str) -> tuple[str, str]:
    """(heading, body) of the handout section that belongs to a step."""
    prefix = next(s[2] for s in STEPS if s[0] == step_key)
    for head, body in handout_sections().items():
        if head.startswith(prefix):
            return head, body
    raise KeyError(step_key)


# ---------- code excerpts ----------

def _lines(path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def excerpt(path, start: str, end: str | None = None, with_banner: bool = True) -> list[str]:
    """Lines from the first line containing `start` to the first later line containing `end`
    (inclusive; an end marker starting with '<' stops just before that line). With with_banner,
    the '# =====' line just above is included too. Blank lines at the end are dropped."""
    lines = _lines(path)
    i = next(n for n, line in enumerate(lines) if start in line)
    if with_banner and i > 0 and lines[i - 1].startswith("# ====="):
        i -= 1
    if end is None:
        j = len(lines) - 1
    elif end.startswith("<"):
        j = next(n for n in range(i + 1, len(lines)) if end[1:] in lines[n]) - 1
    else:
        j = next(n for n in range(i, len(lines)) if end in lines[n])
    out = lines[i:j + 1]
    while out and not out[-1].strip():
        out.pop()
    return out


@dataclass
class Change:
    """One change from Lab 3 to Lab 9: where it goes, the Lab 3 lines before and the Lab 9 lines after."""
    title: str
    where: str
    before: list[str]   # empty when the code is new
    after: list[str]
    todo: bool = False  # True when the student fills in this code (a TODO in the starter)

    def diff(self) -> str:
        """Diff text: '-' lines are Lab 3 lines to remove, '+' lines are Lab 9 lines to add."""
        if not self.before:
            return "\n".join("+ " + line for line in self.after)
        out = []
        for line in difflib.ndiff(self.before, self.after):
            # ndiff also emits '? ' hint lines; I drop them to keep the view simple.
            if not line.startswith("? "):
                out.append(line)
        return "\n".join(out)

    @property
    def added(self) -> int:
        return sum(1 for line in self.diff().splitlines() if line.startswith("+ "))

    @property
    def removed(self) -> int:
        return sum(1 for line in self.diff().splitlines() if line.startswith("- "))


# I define each part's changes by marker text, not line numbers, so small edits to the starter do not
# break the page. Each tuple: title, where it goes, (Lab 3 start, end) or None, (starter start, end), todo.
_PLAN = {
    "A": [
        ("Top of the file: sqlite fix and imports", "Replace the first two lines of Lab3.py",
         ("import streamlit as st", "from openai import OpenAI"),
         ("# fix for the sqlite3 error", "from chromadb.utils import embedding_functions"), False),
        ("Settings, system prompt, title and API key", "Replace the Lab 3 title, client, buffer and system prompt",
         ("st.title(", "<# set up the message history"),
         ("# settings", "client = OpenAI(api_key=openai_api_key)"), False),
        ("New: the persistent memory store", "Add after the API key (new code, already written)",
         None, ("# Part A: the persistent memory store", "collection = st.session_state.Lab9_MemoryDB"), False),
        ("Sidebar and chat loop", "Replace the Lab 3 chat history and chat loop (already written)",
         ("# set up the message history", None),
         ("# sidebar: who is chatting", None), False),
    ],
    "B": [
        ("Your TODOs: should_remember() and save_memory()", "New functions after Part A; fill in the TODOs",
         None, ("# Part B: WRITE", "return memory_id"), True),
        ("Where they are called: after the answer", "End of the chat loop (already written)",
         ("# save the assistant's reply", None),
         ('st.session_state.lab9_messages.append({"role": "assistant"', "st.session_state.lab9_last_prompt ="), False),
    ],
    "C": [
        ("Your TODO: recall_memories()", "New function after Part B; fill in the TODO",
         None, ("# Part C: READ", "return []   # <- replace this line"), True),
        ("Where it is called: before the answer", "Inside the chat loop (already written)",
         ("# Part B buffer", "buffered_messages ="),
         ("# READ first", "buffered_messages ="), False),
    ],
    "D": [
        ("Your TODO: build_system_prompt()", "New function after Part C; fill in the TODO",
         None, ("# Part D: INJECT", "return SYSTEM_PROMPT   # <- replace this line"), True),
        ("Where it is used: the system prompt now comes from memory", "Inside the chat loop (already written)",
         ("# Part C: put the system prompt first", "messages_to_send ="),
         ("system_prompt = build_system_prompt", "messages_to_send ="), False),
        ("New: the Behind the scenes expander", "At the end of the file (already written)",
         None, ("# Part D: show exactly what the model got", None), False),
    ],
    "stretch": [
        ("Stretch: forget_user()", "Fill in for the Forget me button",
         None, ("def forget_user", "return False"), True),
    ],
}


@lru_cache(maxsize=None)
def changes(step_key: str) -> tuple[Change, ...]:
    """The Lab 3 to Lab 9 changes that belong to one step (empty for steps without code)."""
    out = []
    for title, where, before, after, todo in _PLAN.get(step_key, []):
        b = excerpt(LAB3, before[0], before[1], with_banner=False) if before else []
        a = excerpt(STARTER, after[0], after[1])
        out.append(Change(title, where, b, a, todo))
    return tuple(out)


def setup_snippets() -> dict[str, str]:
    """The extra setup lines for Part A: requirements and .gitignore."""
    return {"requirements.txt": REQUIREMENTS.read_text(encoding="utf-8").strip(),
            ".gitignore": "lab9_memory_db/"}
