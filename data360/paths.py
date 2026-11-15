"""Central file locations. Override the store location with DATA360_DB."""
from __future__ import annotations

import os
from pathlib import Path

# I compute every path from this file's location, so the app works no matter which folder it is
# started from.
ROOT = Path(__file__).resolve().parents[1]
# Real public data, synthetic learners and the SQLite store each get their own folder.
DATA = ROOT / "data"
REAL = DATA / "real"
SYNTH = DATA / "synthetic"
STORE_DIR = DATA / "store"
# Lab 9 student files (handout, starter, our Lab 3 code) shown on the Lab page.
LAB9 = ROOT / "lab9"


# Here I decide where the memory database lives. DATA360_DB lets the tests and the lab use a throwaway
# file instead of the real store.
def db_path() -> Path:
    p = Path(os.environ.get("DATA360_DB", STORE_DIR / "memory.db"))
    # I create the folder if it is missing, because a fresh clone from GitHub has no data/store folder
    # (it is in .gitignore).
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
