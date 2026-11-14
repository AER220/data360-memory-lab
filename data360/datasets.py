"""Loaders for the cached real data and the synthetic learner data."""
# Loaders for every data file in the project. Pages and the memory system read data only through
# these functions.
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .paths import REAL, SYNTH


# My data files are JSON Lines: one record per line. A missing file returns an empty list instead of
# crashing the app.
def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@lru_cache(maxsize=1)
# I cache the read-only reference files, so they are loaded from disk once per process, not on every
# click.
def reference_docs() -> tuple[dict, ...]:
    """Chunks of real R documentation pages (tidyverse, base R, jsonlite, palmerpenguins)."""
    return tuple(_jsonl(REAL / "reference_docs.jsonl"))


@lru_cache(maxsize=1)
# Real public questions about the errors beginners hit, used as shared reference material (never as
# memory).
def stackoverflow_questions() -> tuple[dict, ...]:
    """Real Stack Overflow questions tagged [r] about common beginner errors (CC BY-SA)."""
    return tuple(_jsonl(REAL / "stackoverflow_r_errors.jsonl"))


@lru_cache(maxsize=1)
# Short notes I wrote for the lab, each one linking to its public source.
def lab_notes() -> tuple[dict, ...]:
    """Short notes written for the lab, each pointing to a public source."""
    return tuple(_jsonl(REAL / "lab_reference_notes.jsonl"))


# The real palmerpenguins table (CC0), shown on the Data Explorer page.
def penguins() -> pd.DataFrame:
    return pd.read_csv(REAL / "penguins.csv")


# manifest.json records when and from where the real data was fetched, so the app can show it.
def manifest() -> dict:
    p = REAL / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else {}


# The synthetic learners are not cached, because the Data Explorer can regenerate them while the app
# runs.
def canonical_events() -> list[dict]:
    """The hand-written course set: 3 learners, 12 sessions, 28 events (from the proposal)."""
    return _jsonl(SYNTH / "canonical_events.jsonl")


# Probe questions with the memory ids that should come back, used by the evaluation.
def canonical_probes() -> list[dict]:
    return _jsonl(SYNTH / "canonical_probes.jsonl")


# Larger seeded synthetic set, produced by data360/synthetic.py.
def generated_events() -> list[dict]:
    return _jsonl(SYNTH / "generated_events.jsonl")


def generated_probes() -> list[dict]:
    return _jsonl(SYNTH / "generated_probes.jsonl")


# One entry point so pages can say 'canonical' or 'generated' without knowing file names.
def load_dataset(name: str) -> tuple[list[dict], list[dict]]:
    """name: 'canonical' or 'generated'."""
    if name == "canonical":
        return canonical_events(), canonical_probes()
    if name == "generated":
        return generated_events(), generated_probes()
    raise ValueError(f"unknown dataset {name!r}")
