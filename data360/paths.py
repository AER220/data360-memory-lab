"""Central file locations. Override the store location with DATA360_DB."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REAL = DATA / "real"
SYNTH = DATA / "synthetic"
STORE_DIR = DATA / "store"
LAB = ROOT / "lab"


def db_path() -> Path:
    p = Path(os.environ.get("DATA360_DB", STORE_DIR / "memory.db"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
