"""Local text embeddings. No API key and no model download by default.

* ``tfidf`` (default): word + character TF-IDF fitted on a fixed background corpus
  (the cached real R documentation, the Stack Overflow questions and the synthetic
  event texts). Deterministic, fast, about 1 second to fit.
* ``minilm`` (optional): sentence-transformers ``all-MiniLM-L6-v2``, the model named in
  the proposal. Set ``DATA360_EMBEDDER=minilm`` and ``pip install sentence-transformers``.

Every embedder returns L2-normalised dense float32 vectors, so cosine similarity is a dot product.
"""
# Embeddings turn text into vectors so I can measure how similar a question is to each memory.
from __future__ import annotations

import hashlib
import os
from functools import lru_cache

import numpy as np

# I keep R operators like %>% and |> as whole tokens, because they matter a lot in R error questions.
TOKEN_PATTERN = r"(?u)%>%|\|>|[A-Za-z_][A-Za-z0-9_.]*[A-Za-z0-9_]|[A-Za-z]"


# I scale every vector to length 1, so cosine similarity becomes a simple dot product later.
def _normalise(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    if m.ndim == 1:
        m = m[None, :]
    n = np.linalg.norm(m, axis=1, keepdims=True)
    # An empty text gives an all-zero vector; dividing by 1 avoids a divide-by-zero.
    n[n == 0] = 1.0
    return m / n


# Default embedder: TF-IDF needs no download and no key, so the class can run the app offline.
class TfidfEmbedder:
    name = "tfidf"

    def __init__(self, corpus: list[str], max_features: int = 3000):
        from sklearn.feature_extraction.text import TfidfVectorizer

        # I fit on a fixed background corpus, so the same text always gets the same vector.
        corpus = [c for c in corpus if c and c.strip()] or ["empty corpus"]
        # Word features catch shared vocabulary; character features catch typos and partial names like
        # 'ggplot' vs 'ggplot2'.
        self.word = TfidfVectorizer(token_pattern=TOKEN_PATTERN, lowercase=True, stop_words="english",
                                    ngram_range=(1, 2), sublinear_tf=True, min_df=1, max_features=max_features)
        self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True,
                                    sublinear_tf=True, min_df=2, max_features=max_features)
        self.word.fit(corpus)
        self.char.fit(corpus)
        # The signature changes when the corpus changes, which tells the store to re-embed old
        # memories.
        h = hashlib.sha1()
        for c in corpus:
            h.update(c.encode("utf-8"))
        self.signature = f"tfidf-{max_features}-{h.hexdigest()[:12]}"

    def encode(self, texts: list[str]) -> np.ndarray:
        # I blend word (60 percent) and character (40 percent) features, then normalise again.
        w = _normalise(self.word.transform(texts).toarray()) * np.sqrt(0.6)
        c = _normalise(self.char.transform(texts).toarray()) * np.sqrt(0.4)
        return _normalise(np.hstack([w, c]))


# Optional embedder from the proposal (all-MiniLM-L6-v2). It understands meaning better but needs a
# large download.
class MiniLMEmbedder:
    name = "minilm"
    signature = "minilm-all-MiniLM-L6-v2"

    def __init__(self):
        from sentence_transformers import SentenceTransformer  # optional dependency

        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def encode(self, texts: list[str]) -> np.ndarray:
        return _normalise(self.model.encode(list(texts), normalize_embeddings=True))


# The corpus TF-IDF learns its vocabulary from: real docs, Stack Overflow questions, lab notes and
# synthetic event texts.
def background_corpus() -> list[str]:
    # I import inside the function to avoid a circular import between embeddings, datasets and
    # synthetic.
    from . import datasets
    from .synthetic import template_texts

    texts = [d["text"] for d in datasets.reference_docs()]
    texts += [f"{q['title']} {q['body_excerpt']}" for q in datasets.stackoverflow_questions()]
    texts += [n["text"] for n in datasets.lab_notes()]
    texts += [e["text"] for e in datasets.canonical_events()]
    texts += [q["question"] for q in datasets.canonical_probes()]
    texts += template_texts()
    return texts


@lru_cache(maxsize=2)
# I cache the embedder so it is fitted once per process. DATA360_EMBEDDER picks which one.
def get_embedder(kind: str | None = None):
    kind = (kind or os.environ.get("DATA360_EMBEDDER", "tfidf")).lower()
    if kind == "minilm":
        try:
            return MiniLMEmbedder()
        # If MiniLM is not installed, I fall back to TF-IDF rather than breaking a live demo.
        except Exception as exc:  # fall back rather than crash the class demo
            print(f"[data360] MiniLM unavailable ({exc}); falling back to TF-IDF")
    return TfidfEmbedder(background_corpus())
