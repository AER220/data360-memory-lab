"""Persistent memory store: one SQLite file holds each memory's text, metadata and vector.

Survives restarts (a new process reads the same file). Deleting a row removes the text
and the vector together. Superseded and archived rows stay as history and are skipped
by retrieval.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    session_id TEXT,
    created_at TEXT NOT NULL,
    memory_type TEXT NOT NULL,          -- episodic | semantic | procedural
    event_type TEXT,                    -- error_encountered, preference_stated, correction, summary ...
    topic TEXT,
    slot TEXT,                          -- profile slot for updatable facts, e.g. environment
    importance REAL NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',   -- active | archived | consolidated
    supersedes TEXT,
    superseded_by TEXT,
    valid_to TEXT,                      -- set when a later memory replaces this one
    source_ids TEXT DEFAULT '[]',       -- for consolidated summaries
    consolidated_into TEXT,
    access_count INTEGER DEFAULT 0,
    last_accessed TEXT,
    source_url TEXT,
    synthetic INTEGER DEFAULT 1,
    vector BLOB
);
CREATE INDEX IF NOT EXISTS idx_learner ON memories(learner_id);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, learner_id TEXT, action TEXT, memory_id TEXT, detail TEXT
);
"""

COLUMNS = ["memory_id", "learner_id", "session_id", "created_at", "memory_type", "event_type", "topic", "slot",
           "importance", "text", "status", "supersedes", "superseded_by", "valid_to", "source_ids",
           "consolidated_into", "access_count", "last_accessed", "source_url", "synthetic"]


@dataclass
class Memory:
    memory_id: str
    learner_id: str
    session_id: str
    created_at: str
    memory_type: str
    text: str
    importance: float = 5.0
    event_type: str = ""
    topic: str = ""
    slot: str = ""
    status: str = "active"
    supersedes: str = ""
    superseded_by: str = ""
    valid_to: str = ""
    source_ids: list = field(default_factory=list)
    consolidated_into: str = ""
    access_count: int = 0
    last_accessed: str = ""
    source_url: str = ""
    synthetic: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


class MemoryStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    # ---------- meta ----------
    def get_meta(self, key: str, default: str = "") -> str:
        r = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else default

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self.conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))
            self.conn.commit()

    # ---------- rows ----------
    @staticmethod
    def _row_to_memory(r: sqlite3.Row) -> Memory:
        d = {k: r[k] for k in COLUMNS}
        d["source_ids"] = json.loads(d["source_ids"] or "[]")
        d["synthetic"] = bool(d["synthetic"])
        for k in ("session_id", "event_type", "topic", "slot", "supersedes", "superseded_by", "valid_to",
                  "consolidated_into", "last_accessed", "source_url"):
            d[k] = d[k] or ""
        return Memory(**d)

    def add(self, m: Memory, vector: np.ndarray) -> None:
        d = m.to_dict()
        d["source_ids"] = json.dumps(d["source_ids"])
        d["synthetic"] = int(d["synthetic"])
        blob = np.asarray(vector, dtype=np.float16).tobytes()
        with self._lock:
            self.conn.execute(
                f"INSERT OR REPLACE INTO memories ({','.join(COLUMNS)}, vector) VALUES ({','.join('?' * (len(COLUMNS) + 1))})",
                [d[k] for k in COLUMNS] + [blob])
            self.conn.commit()

    def update(self, memory_id: str, **fields) -> None:
        if not fields:
            return
        if "source_ids" in fields:
            fields["source_ids"] = json.dumps(fields["source_ids"])
        sets = ", ".join(f"{k}=?" for k in fields)
        with self._lock:
            self.conn.execute(f"UPDATE memories SET {sets} WHERE memory_id=?", [*fields.values(), memory_id])
            self.conn.commit()

    def set_vector(self, memory_id: str, vector: np.ndarray) -> None:
        with self._lock:
            self.conn.execute("UPDATE memories SET vector=? WHERE memory_id=?",
                              (np.asarray(vector, dtype=np.float16).tobytes(), memory_id))
            self.conn.commit()

    def get(self, memory_id: str) -> Memory | None:
        r = self.conn.execute("SELECT * FROM memories WHERE memory_id=?", (memory_id,)).fetchone()
        return self._row_to_memory(r) if r else None

    def has_vector(self, memory_id: str) -> bool:
        r = self.conn.execute("SELECT vector IS NOT NULL FROM memories WHERE memory_id=?", (memory_id,)).fetchone()
        return bool(r and r[0])

    def list(self, learner_id: str | None = None) -> list[Memory]:
        if learner_id is None:
            rows = self.conn.execute("SELECT * FROM memories ORDER BY created_at").fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM memories WHERE learner_id=? ORDER BY created_at",
                                     (learner_id,)).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def vectors(self, ids: list[str]) -> dict[str, np.ndarray]:
        if not ids:
            return {}
        out = {}
        for i in range(0, len(ids), 500):
            part = ids[i:i + 500]
            q = f"SELECT memory_id, vector FROM memories WHERE memory_id IN ({','.join('?' * len(part))})"
            for mid, blob in self.conn.execute(q, part).fetchall():
                if blob is not None:
                    out[mid] = np.frombuffer(blob, dtype=np.float16).astype(np.float32)
        return out

    def learners(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT DISTINCT learner_id FROM memories ORDER BY learner_id")]

    def delete(self, memory_id: str) -> bool:
        """Hard delete: text, metadata and vector are removed in one statement."""
        with self._lock:
            cur = self.conn.execute("DELETE FROM memories WHERE memory_id=?", (memory_id,))
            self.conn.commit()
        return cur.rowcount > 0

    def delete_learner(self, learner_id: str) -> int:
        with self._lock:
            cur = self.conn.execute("DELETE FROM memories WHERE learner_id=?", (learner_id,))
            self.conn.commit()
        return cur.rowcount

    def clear(self) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM memories")
            self.conn.execute("DELETE FROM audit")
            self.conn.commit()

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    # ---------- audit log (what happened to memory, for the timeline page) ----------
    def log(self, at: str, learner_id: str, action: str, memory_id: str, detail: str = "") -> None:
        with self._lock:
            self.conn.execute("INSERT INTO audit (at, learner_id, action, memory_id, detail) VALUES (?,?,?,?,?)",
                              (at, learner_id, action, memory_id, detail))
            self.conn.commit()

    def audit(self, learner_id: str | None = None) -> list[dict]:
        if learner_id:
            rows = self.conn.execute("SELECT * FROM audit WHERE learner_id=? ORDER BY id", (learner_id,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM audit ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.conn.close()
