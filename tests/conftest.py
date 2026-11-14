import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("DATA360_LLM_PROVIDER", None)
os.environ.setdefault("DATA360_EMBEDDER", "tfidf")


@pytest.fixture()
def mm(tmp_path):
    from data360.memory import MemoryManager
    from data360.store import MemoryStore

    m = MemoryManager(MemoryStore(tmp_path / "t.db"))
    yield m
    m.store.close()
