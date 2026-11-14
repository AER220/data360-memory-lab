# Shared pytest fixtures for the lab checkpoints.
import importlib.util
import os
from pathlib import Path

import pytest

# The lab folder, one level above this checks folder.
LAB = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
# I load the module straight from its file path, so the same checks can grade either the starter or
# the solutions.
def lab():
    """Import the student's module (LAB_TARGET=starter, default) or the solutions."""
    target = os.environ.get("LAB_TARGET", "starter")
    path = LAB / target / "memory_lab.py"
    spec = importlib.util.spec_from_file_location(f"memory_lab_{target}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
# Each test gets a fresh empty store in its own temporary folder, so tests never affect each other.
def store(lab, tmp_path):
    return lab.LabStore(tmp_path / "lab_store.json")


@pytest.fixture()
# A store already filled with the 28 course-set events, for tests that need data.
def full_store(lab, store):
    for e in lab.load_events():
        lab.write_memory(store, e)
    return store
