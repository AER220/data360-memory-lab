"""The Data360 long-term memory loop.

Operations demonstrated (each one is a method below):
  WRITE        write()          write filter, metadata, vector
  RETRIEVE     retrieve()       learner + validity filter BEFORE similarity, then relevance, recency, importance
  UPDATE       write()/correct() a correction supersedes the old fact from that moment on (point in time)
  CONSOLIDATE  consolidate()    repeated episodes on one topic become one semantic summary
  FORGET       forget()         importance x exponential decay; weak episodic memories are archived
  DELETE       delete()         hard delete of text and vector, learner controlled
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, replace

import numpy as np

from .embeddings import get_embedder
from .store import Memory, MemoryStore
from .timeutil import days_between, iso, now, parse

PROFILE_EVENT_TYPES = {"preference_stated", "correction"}
SLOT_TOPICS = {"environment", "style", "accessibility", "background", "pace", "os"}


@dataclass
class Policy:
    k: int = 3                      # memory budget in the prompt
    min_rel: float = 0.12           # relevance gate (cosine); below it a memory is not "relevant"
    w_rel: float = 1.0              # weights of the combined score (Park et al. 2023 style)
    w_rec: float = 0.25
    w_imp: float = 0.25
    recency_half_life_days: float = 30.0
    filter_before_search: bool = True   # learner namespace applied before similarity
    use_validity: bool = True           # skip superseded / archived / consolidated rows
    write_filter: bool = True           # skip small talk and off-topic distractors
    inject_profile: bool = True         # always add current preferences (fixes the q04 gap)
    profile_max: int = 4
    decay_half_life_days: float = 21.0  # used by strength() and forget()

    @classmethod
    def naive(cls) -> "Policy":
        return cls(filter_before_search=False, use_validity=False, write_filter=False,
                   inject_profile=False, min_rel=0.0, w_rec=0.0, w_imp=0.0)


@dataclass
class Retrieved:
    memory: Memory
    relevance: float
    recency: float
    importance: float
    score: float

    def row(self) -> dict:
        return {"id": self.memory.memory_id, "type": self.memory.memory_type, "session": self.memory.session_id,
                "relevance": round(self.relevance, 3), "recency": round(self.recency, 3),
                "importance": round(self.importance, 2), "score": round(self.score, 3), "text": self.memory.text}


@dataclass
class Context:
    learner_id: str
    query: str
    profile: list[Memory] = field(default_factory=list)
    memories: list[Retrieved] = field(default_factory=list)

    @property
    def ids(self) -> list[str]:
        seen, out = set(), []
        for m in self.profile + [r.memory for r in self.memories]:
            if m.memory_id not in seen:
                seen.add(m.memory_id)
                out.append(m.memory_id)
        return out

    def ids_with_sources(self) -> list[str]:
        out = list(self.ids)
        for m in self.profile + [r.memory for r in self.memories]:
            out += [s for s in m.source_ids if s not in out]
        return out


def should_store(event: dict) -> bool:
    """WRITE FILTER: keep useful learning events, skip small talk and distractors."""
    if event.get("memory_type", "none") in ("none", "", None):
        return False
    if event.get("event_type") == "distractor":
        return False
    return float(event.get("importance", 5)) >= 3


def infer_slot(event: dict) -> str:
    if event.get("slot"):
        return event["slot"]
    if event.get("memory_type") == "semantic" and event.get("event_type") in PROFILE_EVENT_TYPES:
        topic = (event.get("topic") or "").lower()
        if topic in SLOT_TOPICS:
            return topic
    return ""


def _short(text: str, n: int = 110) -> str:
    text = re.sub(r"^(Correction:|Got Error:|Again got)\s*", "", text.strip(), flags=re.I)
    first = re.split(r"(?<=[.;])\s", text)[0]
    return first if len(first) <= n else first[: n - 3].rstrip() + "..."


class MemoryManager:
    def __init__(self, store: MemoryStore, embedder=None, policy: Policy | None = None):
        self.store = store
        self.embedder = embedder or get_embedder()
        self.policy = policy or Policy()
        self._reembed_if_needed()

    # ------------------------------------------------------------------ helpers
    def _reembed_if_needed(self) -> None:
        sig = self.store.get_meta("embedder_signature")
        if sig == self.embedder.signature:
            return
        mems = self.store.list()
        if mems:
            vecs = self.embedder.encode([m.text for m in mems])
            for m, v in zip(mems, vecs):
                self.store.set_vector(m.memory_id, v)
        self.store.set_meta("embedder_signature", self.embedder.signature)

    def is_valid(self, m: Memory, as_of=None) -> bool:
        t = parse(as_of) if as_of else None
        if t is not None and parse(m.created_at) > t:
            return False  # did not exist yet at that moment
        if not self.policy.use_validity:
            return True
        if m.status != "active":
            return False
        if m.valid_to and (t is None or parse(m.valid_to) <= t):
            return False
        return True

    def current(self, learner_id: str, as_of=None) -> list[Memory]:
        return [m for m in self.store.list(learner_id) if self.is_valid(m, as_of)]

    # ------------------------------------------------------------------ WRITE + UPDATE
    def write(self, event: dict, now_ts=None) -> tuple[str, str]:
        """Write one approved event. Returns (status, memory_id). Applies corrections in time order."""
        if self.policy.write_filter and not should_store(event):
            self.store.log(iso(parse(event.get("timestamp") or now_ts)), event.get("learner_id", "?"), "skip",
                           event.get("event_id", ""), event.get("text", "")[:80])
            return "skipped", ""
        created = iso(parse(event.get("timestamp") or now_ts))
        mid = event.get("event_id") or f"m_{uuid.uuid4().hex[:8]}"
        m = Memory(
            memory_id=mid, learner_id=event["learner_id"], session_id=event.get("session_id", ""),
            created_at=created, memory_type=event.get("memory_type") or "episodic", text=event["text"],
            importance=float(event.get("importance", 5)), event_type=event.get("event_type", ""),
            topic=event.get("topic", ""), slot=infer_slot(event), supersedes=event.get("supersedes", "") or "",
            source_url=event.get("source_url", "") or "", synthetic=bool(event.get("synthetic", True)),
        )
        self.store.add(m, self.embedder.encode([m.text])[0])
        self.store.log(created, m.learner_id, "write", mid, m.text[:80])
        # UPDATE: explicit supersedes link, or same profile slot replaced by a newer statement
        targets = []
        if m.supersedes:
            targets.append(m.supersedes)
        elif m.slot:
            targets += [o.memory_id for o in self.current(m.learner_id, created)
                        if o.slot == m.slot and o.memory_id != mid]
        for t in targets:
            old = self.store.get(t)
            if old and old.learner_id == m.learner_id and not old.valid_to:
                self.store.update(t, valid_to=created, superseded_by=mid)
                if not m.supersedes:
                    self.store.update(mid, supersedes=t)
                self.store.log(created, m.learner_id, "supersede", t, f"replaced by {mid}")
        return "saved", mid

    def load_events(self, events: list[dict], upto_session: str | None = None, upto_time=None) -> dict:
        """Replay events in time order (sessions arrive one after another)."""
        saved = skipped = 0
        evs = sorted(events, key=lambda e: parse(e["timestamp"]))
        last_ts = None
        if upto_session:
            sess = [e for e in evs if e["session_id"] == upto_session]
            last_ts = parse(sess[-1]["timestamp"]) if sess else None
        for e in evs:
            t = parse(e["timestamp"])
            if last_ts is not None and t > last_ts:
                break
            if upto_time is not None and t > parse(upto_time):
                break
            status, _ = self.write(e)
            saved += status == "saved"
            skipped += status == "skipped"
        return {"saved": saved, "skipped": skipped}

    def correct(self, memory_id: str, new_text: str, now_ts=None) -> str:
        """Learner edit: the new text becomes current, the old row stays as history."""
        old = self.store.get(memory_id)
        if old is None:
            raise KeyError(memory_id)
        t = iso(parse(now_ts) if now_ts else now())
        event = {"event_id": f"m_{uuid.uuid4().hex[:8]}", "learner_id": old.learner_id, "session_id": old.session_id,
                 "timestamp": t, "memory_type": old.memory_type, "event_type": "correction", "topic": old.topic,
                 "importance": max(old.importance, 6), "supersedes": memory_id, "text": new_text, "synthetic": old.synthetic}
        _, mid = self.write(event)
        return mid

    # ------------------------------------------------------------------ RETRIEVE
    def recency(self, m: Memory, as_of) -> float:
        ref = m.last_accessed or m.created_at
        age = max(0.0, days_between(ref, as_of))
        return float(0.5 ** (age / self.policy.recency_half_life_days))

    def retrieve(self, learner_id: str, query: str, as_of=None, k: int | None = None, touch: bool = False) -> list[Retrieved]:
        p = self.policy
        k = k or p.k
        as_of_dt = parse(as_of) if as_of else now()
        if p.filter_before_search:
            cands = [m for m in self.store.list(learner_id) if self.is_valid(m, as_of_dt)]
        else:  # naive: search everybody, everything, then rank by similarity alone
            cands = [m for m in self.store.list() if parse(m.created_at) <= as_of_dt]
        if not cands:
            return []
        vecs = self.store.vectors([m.memory_id for m in cands])
        q = self.embedder.encode([query])[0]
        out = []
        for m in cands:
            v = vecs.get(m.memory_id)
            if v is None:
                continue
            rel = float(np.dot(q, v))
            if rel < p.min_rel:
                continue
            rec = self.recency(m, as_of_dt)
            imp = m.importance / 10.0
            out.append(Retrieved(m, rel, rec, imp, p.w_rel * rel + p.w_rec * rec + p.w_imp * imp))
        out.sort(key=lambda r: r.score, reverse=True)
        out = out[:k]
        if touch:
            for r in out:
                self.store.update(r.memory.memory_id, access_count=r.memory.access_count + 1,
                                  last_accessed=iso(as_of_dt))
        return out

    def profile(self, learner_id: str, as_of=None) -> list[Memory]:
        if not self.policy.inject_profile:
            return []
        prof = [m for m in self.current(learner_id, as_of)
                if m.memory_type == "semantic" and m.event_type in PROFILE_EVENT_TYPES]
        prof.sort(key=lambda m: (m.importance, m.created_at), reverse=True)
        return prof[: self.policy.profile_max]

    def context(self, learner_id: str, query: str, as_of=None, touch: bool = False) -> Context:
        prof = self.profile(learner_id, as_of)
        mems = self.retrieve(learner_id, query, as_of=as_of, touch=touch)
        prof_ids = {m.memory_id for m in prof}
        return Context(learner_id, query, prof, [r for r in mems if r.memory.memory_id not in prof_ids])

    # ------------------------------------------------------------------ FORGET
    def strength(self, m: Memory, as_of=None) -> float:
        """Memory strength: importance x exponential decay; each retrieval slows the decay (spacing effect)."""
        ref = m.last_accessed or m.created_at
        age = max(0.0, days_between(ref, as_of or now()))
        half = self.policy.decay_half_life_days * (1 + 0.5 * m.access_count)
        return float(m.importance / 10.0 * 0.5 ** (age / half))

    def forget(self, learner_id: str, as_of=None, threshold: float = 0.1, types=("episodic",)) -> list[str]:
        """Archive (not delete) weak memories. Profile facts and procedures are kept unless listed in types."""
        as_of = as_of or now()
        archived = []
        for m in self.current(learner_id, as_of):
            if m.memory_type in types and self.strength(m, as_of) < threshold:
                self.store.update(m.memory_id, status="archived")
                self.store.log(iso(parse(as_of)), learner_id, "archive", m.memory_id, f"strength<{threshold}")
                archived.append(m.memory_id)
        return archived

    def restore(self, memory_id: str) -> None:
        m = self.store.get(memory_id)
        if m:
            self.store.update(memory_id, status="active", consolidated_into="")
            self.store.log(iso(now()), m.learner_id, "restore", memory_id, "")

    # ------------------------------------------------------------------ CONSOLIDATE
    def consolidate(self, learner_id: str, as_of=None, min_group: int = 2, summarizer=None) -> list[str]:
        """Group current episodic memories by topic; groups of >= min_group become one semantic summary.

        summarizer: optional callable(list[str]) -> str (for example an LLM). Default is extractive.
        """
        as_of = parse(as_of) if as_of else now()
        groups: dict[str, list[Memory]] = {}
        for m in self.current(learner_id, as_of):
            if m.memory_type == "episodic" and m.event_type != "summary":
                groups.setdefault(m.topic or "general", []).append(m)
        new_ids = []
        for topic, mems in sorted(groups.items()):
            if len(mems) < min_group:
                continue
            mems.sort(key=lambda m: m.created_at)
            sessions = ", ".join(sorted({m.session_id for m in mems}))
            if summarizer:
                text = summarizer([m.text for m in mems])
            else:
                text = (f"Recurring {topic} pattern across sessions {sessions} ({len(mems)} episodes): "
                        + "; ".join(_short(m.text) for m in mems))
            sid = f"sum_{learner_id}_{re.sub(r'[^a-z0-9]+', '_', topic.lower())}_{uuid.uuid4().hex[:4]}"
            ev = {"event_id": sid, "learner_id": learner_id, "session_id": mems[-1].session_id,
                  "timestamp": iso(as_of), "memory_type": "semantic", "event_type": "summary", "topic": topic,
                  "importance": min(10.0, max(m.importance for m in mems) + 1), "text": text,
                  "synthetic": all(m.synthetic for m in mems)}
            self.write(ev)
            self.store.update(sid, source_ids=[m.memory_id for m in mems])
            for m in mems:
                self.store.update(m.memory_id, status="consolidated", consolidated_into=sid)
            self.store.log(iso(as_of), learner_id, "consolidate", sid, ", ".join(m.memory_id for m in mems))
            new_ids.append(sid)
        return new_ids

    # ------------------------------------------------------------------ DELETE
    def delete(self, memory_id: str) -> bool:
        m = self.store.get(memory_id)
        ok = self.store.delete(memory_id)
        if ok and m:
            self.store.log(iso(now()), m.learner_id, "delete", memory_id, "text and vector removed")
        return ok

    def with_policy(self, **changes) -> "MemoryManager":
        mm = MemoryManager.__new__(MemoryManager)
        mm.store, mm.embedder, mm.policy = self.store, self.embedder, replace(self.policy, **changes)
        return mm
