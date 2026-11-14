"""Loaders for the cached real data and the synthetic learner data."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .paths import REAL, SYNTH


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@lru_cache(maxsize=1)
def reference_docs() -> tuple[dict, ...]:
    """Chunks of real R documentation pages (tidyverse, base R, jsonlite, palmerpenguins)."""
    return tuple(_jsonl(REAL / "reference_docs.jsonl"))


@lru_cache(maxsize=1)
def stackoverflow_questions() -> tuple[dict, ...]:
    """Real Stack Overflow questions tagged [r] about common beginner errors (CC BY-SA)."""
    return tuple(_jsonl(REAL / "stackoverflow_r_errors.jsonl"))


@lru_cache(maxsize=1)
def lab_notes() -> tuple[dict, ...]:
    """Short notes written for the lab, each pointing to a public source."""
    return tuple(_jsonl(REAL / "lab_reference_notes.jsonl"))


def penguins() -> pd.DataFrame:
    return pd.read_csv(REAL / "penguins.csv")


def manifest() -> dict:
    p = REAL / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else {}


def canonical_events() -> list[dict]:
    """The hand-written course set: 3 learners, 12 sessions, 28 events (from the proposal)."""
    return _jsonl(SYNTH / "canonical_events.jsonl")


def canonical_probes() -> list[dict]:
    return _jsonl(SYNTH / "canonical_probes.jsonl")


def generated_events() -> list[dict]:
    return _jsonl(SYNTH / "generated_events.jsonl")


def generated_probes() -> list[dict]:
    return _jsonl(SYNTH / "generated_probes.jsonl")


def load_dataset(name: str) -> tuple[list[dict], list[dict]]:
    """name: 'canonical' or 'generated'."""
    if name == "canonical":
        return canonical_events(), canonical_probes()
    if name == "generated":
        return generated_events(), generated_probes()
    raise ValueError(f"unknown dataset {name!r}")
