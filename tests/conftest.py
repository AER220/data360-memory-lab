# Shared test setup. I make sure no test can ever call a real paid API.
import os
import sys
from pathlib import Path

import pytest

# Make the project importable from the tests folder.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Never call a real API from the tests: drop keys and ignore any local .env or secrets.toml.
for _k in ("DATA360_LLM_PROVIDER", "DATA360_LLM_MODEL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
           "DATA360_OPENAI_MODEL", "DATA360_ANTHROPIC_MODEL", "DATA360_OLLAMA_MODEL"):
    os.environ.pop(_k, None)
os.environ["DATA360_SKIP_LOCAL_CONFIG"] = "1"
# TF-IDF keeps the tests fast and offline.
os.environ.setdefault("DATA360_EMBEDDER", "tfidf")


@pytest.fixture()
# A fresh memory manager on a temporary database for each test that asks for it.
def mm(tmp_path):
    from data360.memory import MemoryManager
    from data360.store import MemoryStore

    m = MemoryManager(MemoryStore(tmp_path / "t.db"))
    yield m
    m.store.close()
