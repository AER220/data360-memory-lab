"""Shared reference knowledge (RAG, not memory): our R reference notes, real R documentation excerpts
and real Stack Overflow threads.

The same for every learner, read-only, never written by the app.
"""
# Reference knowledge is the same for every learner and is never written by the app. Keeping it
# separate from personal memory is a key design choice.
from __future__ import annotations

from functools import lru_cache

import numpy as np

from . import datasets
from .embeddings import TOKEN_PATTERN, get_embedder

# A note must reach this word-level similarity before I treat the question as covered by the notes.
# Below it, the answer says plainly that the reference notes do not cover the question. I picked the
# value by checking course questions (all above it) against off-topic ones such as "What is the
# capital of France?" (all below it); tests/test_reference_notes.py keeps both sides honest.
COVER_MIN = 0.10

# Words that say nothing about the R topic. Without this list "How do I make ..." would match any note
# that happens to contain "make".
EXTRA_STOP = {"r", "use", "using", "used", "make", "makes", "way", "want", "get", "getting", "got", "keep", "need",
              "does", "do", "did", "work", "works", "thing", "things", "good", "best", "tell", "explain", "help",
              "question", "please", "like", "know", "mean", "means", "difference", "example", "code",
              "write", "writing", "me"}


@lru_cache(maxsize=1)
# Notes get their own word-level TF-IDF index. Word matches (not character fragments) decide whether
# the notes cover a question, so "photosynthesis" cannot sneak in through shared letters. Title and
# keywords are repeated to weigh them more than the body text.
def _note_index():
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

    notes = list(datasets.r_notes())
    texts = [f"{n['title']} {n['title']} {n.get('keywords', '')} {n.get('keywords', '')} {n['text']}" for n in notes]
    vec = TfidfVectorizer(token_pattern=TOKEN_PATTERN, lowercase=True, ngram_range=(1, 2), sublinear_tf=True,
                          stop_words=list(ENGLISH_STOP_WORDS | EXTRA_STOP))
    mat = vec.fit_transform(texts) if notes else None
    return notes, vec, mat


@lru_cache(maxsize=2)
# The doc excerpts and Stack Overflow threads use the same embedder as memory (cached by its
# signature), as in v3.
def _index(signature: str):
    emb = get_embedder()
    docs = [dict(d, kind="doc") for d in datasets.reference_docs()]
    so = [dict(q, kind="stackoverflow", text=f"{q['title']}. {q['body_excerpt']}", chunk_id=f"so{q['question_id']}",
               source_url=q["link"]) for q in datasets.stackoverflow_questions()]
    items = docs + so
    mat = emb.encode([i["text"] for i in items]) if items else np.zeros((0, 1), dtype=np.float32)
    return items, mat


# The best reference notes for a question, each with its similarity; empty when nothing passes COVER_MIN.
def search_notes(query: str, k: int = 3, min_sim: float = COVER_MIN) -> list[dict]:
    notes, vec, mat = _note_index()
    if not notes:
        return []
    sims = (mat @ vec.transform([query]).T).toarray().ravel()
    out = []
    top = float(sims.max()) if len(sims) else 0.0
    for i in np.argsort(-sims)[:k]:
        # Besides the absolute floor, a note must score at least half of the best note, so a weak
        # side match (for example "cloud" in Posit Cloud for a word cloud question) is left out.
        if sims[i] < min_sim or sims[i] < 0.5 * top:
            break
        out.append(dict(notes[i], kind="note", chunk_id=notes[i]["note_id"], similarity=round(float(sims[i]), 3)))
    return out


# Classic RAG search over shared course material: up to 3 notes (our main, verified source), then 1
# documentation excerpt and 1 Stack Overflow thread. Docs and threads are only added when a note
# matched, so a question the notes do not cover gets no references at all and the answer says so.
# Their bar (0.20) is higher than in v3 (0.08): with the notes doing the main work, I only add an
# excerpt or thread when it is clearly on topic.
def search(query: str, k_notes: int = 3, k_docs: int = 1, k_so: int = 1, min_sim: float = 0.20) -> list[dict]:
    notes = search_notes(query, k_notes)
    if not notes:
        return []
    emb = get_embedder()
    items, mat = _index(emb.signature)
    out, nd, ns = [], 0, 0
    if len(items):
        sims = mat @ emb.encode([query])[0]
        for i in np.argsort(-sims):
            it, s = items[i], float(sims[i])
            # Items are sorted best first, so once one is below the threshold all the rest are too.
            if s < min_sim or (nd >= k_docs and ns >= k_so):
                break
            if it["kind"] == "stackoverflow" and ns < k_so:
                out.append(dict(it, similarity=round(s, 3)))
                ns += 1
            elif it["kind"] == "doc" and nd < k_docs:
                out.append(dict(it, similarity=round(s, 3)))
                nd += 1
    return notes + out


# True when at least one reference note was found for the question.
def covered(refs: list[dict]) -> bool:
    return any(r.get("kind") == "note" for r in refs)
