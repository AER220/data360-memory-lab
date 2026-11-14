"""Shared reference knowledge (RAG, not memory): real R docs + real Stack Overflow threads.

The same for every learner, read-only, never written by the agent.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from . import datasets
from .embeddings import get_embedder


@lru_cache(maxsize=2)
def _index(signature: str):
    emb = get_embedder()
    docs = [dict(d, kind="doc") for d in datasets.reference_docs()]
    docs += [dict(n, kind="note", title=f"Lab note {n['note_id']}", chunk_id=n["note_id"]) for n in datasets.lab_notes()]
    so = [dict(q, kind="stackoverflow", text=f"{q['title']}. {q['body_excerpt']}", chunk_id=f"so{q['question_id']}",
               source_url=q["link"]) for q in datasets.stackoverflow_questions()]
    items = docs + so
    mat = emb.encode([i["text"] for i in items]) if items else np.zeros((0, 1), dtype=np.float32)
    return items, mat


def search(query: str, k_docs: int = 2, k_so: int = 1, min_sim: float = 0.08) -> list[dict]:
    emb = get_embedder()
    items, mat = _index(emb.signature)
    if not items:
        return []
    q = emb.encode([query])[0]
    sims = mat @ q
    order = np.argsort(-sims)
    out, nd, ns = [], 0, 0
    for i in order:
        it, s = items[i], float(sims[i])
        if s < min_sim:
            break
        if it["kind"] == "stackoverflow":
            if ns < k_so:
                out.append(dict(it, similarity=round(s, 3)))
                ns += 1
        elif nd < k_docs:
            out.append(dict(it, similarity=round(s, 3)))
            nd += 1
        if nd >= k_docs and ns >= k_so:
            break
    return out
