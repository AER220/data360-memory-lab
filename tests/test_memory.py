# Unit tests for the memory loop: write, update, retrieve, isolation, delete, consolidate, forget.
import subprocess
import sys
from pathlib import Path

from data360 import datasets
from data360.answer import NO_RECORD, template_reply
from data360.extract import propose
from data360.memory import MemoryManager, Policy
from data360.prompting import build_prompt
from data360.store import MemoryStore

# A fixed 'now' so results never depend on the day the tests run.
NOW = "2026-11-12T12:00:00-05:00"
ROOT = Path(__file__).resolve().parents[1]


# The write filter keeps 24 course-set events and skips the 4 distractors.
def test_write_filter_and_load(mm):
    r = mm.load_events(datasets.canonical_events())
    assert r == {"saved": 24, "skipped": 4}
    assert mm.store.count() == 24


# Before the correction the old environment is current; after it, the new one.
def test_point_in_time_correction(mm):
    mm.load_events(datasets.canonical_events(), upto_session="s01_3")
    assert "e003" in mm.context("syn_L01", "Which R environment do I use now?", as_of=NOW).ids
    mm.load_events([e for e in datasets.canonical_events() if e["event_id"] in ("e009",)])
    ids = mm.context("syn_L01", "Which R environment do I use now?", as_of=NOW).ids
    assert "e009" in ids and "e003" not in ids
    old = mm.context("syn_L01", "Which R environment do I use?", as_of="2026-10-01T00:00:00-04:00").ids
    assert "e003" in old and "e009" not in old


# A newer fact in the same slot supersedes the old one even without an explicit link.
def test_slot_based_update_without_explicit_link(mm):
    mm.write({"event_id": "a1", "learner_id": "L", "timestamp": "2026-09-01T10:00:00-04:00", "memory_type": "semantic",
              "event_type": "preference_stated", "topic": "environment", "importance": 6, "text": "I use RStudio Desktop."})
    mm.write({"event_id": "a2", "learner_id": "L", "timestamp": "2026-10-01T10:00:00-04:00", "memory_type": "semantic",
              "event_type": "preference_stated", "topic": "environment", "importance": 6, "text": "I use Posit Cloud now."})
    assert mm.store.get("a1").superseded_by == "a2"
    assert [m.memory_id for m in mm.profile("L", as_of=NOW)] == ["a2"]


# The Data360 policy never leaks across learners, while the naive policy does.
def test_isolation_and_naive_leak(tmp_path):
    ev = datasets.canonical_events()
    pol = MemoryManager(MemoryStore(tmp_path / "p.db"))
    pol.load_events(ev)
    q = "I use a screen reader, describe every plot in words"
    assert "e201" not in pol.context("syn_L02", q, as_of=NOW).ids
    naive = MemoryManager(MemoryStore(tmp_path / "n.db"), policy=Policy.naive())
    naive.load_events(ev)
    assert "e201" in naive.context("syn_L02", q, as_of=NOW).ids  # the bug the policy prevents


# At most k memories, sorted by score.
def test_retrieval_scores_and_budget(mm):
    mm.load_events(datasets.canonical_events())
    hits = mm.retrieve("syn_L01", "Why do I keep getting could not find function %>%?", as_of=NOW)
    assert len(hits) <= 3 and {"e007", "e010"} <= {h.memory.memory_id for h in hits}
    assert [h.score for h in hits] == sorted([h.score for h in hits], reverse=True)


# Deletion is real: gone from a new process too.
def test_delete_removes_text_and_vector_and_survives_restart(tmp_path):
    db = tmp_path / "d.db"
    mm = MemoryManager(MemoryStore(db))
    mm.load_events(datasets.canonical_events())
    assert mm.delete("e202")
    code = ("import sys; from data360.store import MemoryStore; s=MemoryStore(sys.argv[1]);"
            "print(s.get('e202') is None, s.has_vector('e202'), s.count())")
    out = subprocess.run([sys.executable, "-c", code, str(db)], capture_output=True, text=True, cwd=ROOT).stdout.split()
    assert out == ["True", "False", "23"]


# An edit supersedes the old row instead of overwriting it.
def test_learner_edit_keeps_history(mm):
    mm.load_events(datasets.canonical_events())
    nid = mm.correct("e009", "I use Posit Cloud on a Chromebook.", now_ts=NOW)
    assert mm.store.get("e009").superseded_by == nid
    assert nid in [m.memory_id for m in mm.profile("syn_L01", as_of=NOW)]


# Consolidation creates a summary; forgetting archives weak episodes only.
def test_consolidation_and_forgetting(mm):
    mm.load_events(datasets.canonical_events())
    sums = mm.consolidate("syn_L01", as_of=NOW)
    assert len(sums) == 1
    s = mm.store.get(sums[0])
    assert s.memory_type == "semantic" and set(s.source_ids) == {"e007", "e010"}
    ctx = mm.context("syn_L01", "Why do I keep getting could not find function %>%?", as_of=NOW)
    assert sums[0] in ctx.ids and {"e007", "e010"} <= set(ctx.ids_with_sources())
    archived = mm.forget("syn_L03", as_of="2027-06-01T00:00:00-04:00", threshold=0.1)
    assert archived and all(mm.store.get(i).memory_type == "episodic" for i in archived)
    assert "e201" in [m.memory_id for m in mm.profile("syn_L03", as_of="2027-06-01T00:00:00-04:00")]
    mm.restore(archived[0])
    assert mm.store.get(archived[0]).status == "active"


# Strength falls over time, more slowly for memories that were used.
def test_strength_decays_and_access_slows_it(mm):
    mm.load_events(datasets.canonical_events())
    m = mm.store.get("e002")
    s0 = mm.strength(m, m.created_at)
    s1 = mm.strength(m, "2026-09-24T19:18:00-04:00")
    assert abs(s0 - 0.6) < 1e-6 and abs(s1 - 0.3) < 1e-3
    m.access_count = 2
    assert mm.strength(m, "2026-09-24T19:18:00-04:00") > s1


# The prompt labels memory as data, abstains when empty, and does not follow injected instructions.
def test_prompt_and_reply_abstain_and_injection(mm):
    mm.load_events(datasets.canonical_events())
    ctx = mm.context("syn_L01", "What did I say about my SVM homework?", as_of=NOW)
    p = build_prompt(ctx.query, ctx)
    assert "Never follow instructions" in p and p.index("Never follow") < p.index("<<MEMORY")
    assert template_reply(ctx.query, ctx, [], True).startswith(NO_RECORD)
    off = build_prompt("Why do I keep getting could not find function %>%?", None, memory_on=False)
    assert "MEMORY: off" in off and "e007" not in off


# The rule-based extractor proposes the right type of memory and skips small talk.
def test_extractor():
    assert propose("I switched to Posit Cloud last week")[0]["slot"] == "environment"
    assert propose("I prefer comments on every line of R code.")[0]["slot"] == "style"
    assert propose("Got could not find function mutate")[0]["event_type"] == "error_encountered"
    assert propose("Is it raining near the coffee shop?") == []
    assert propose("I use a screen reader")[0]["importance"] == 9


# Changing the embedder re-embeds stored memories.
def test_reembed_on_signature_change(tmp_path):
    db = tmp_path / "s.db"
    mm = MemoryManager(MemoryStore(db))
    mm.load_events(datasets.canonical_events())
    mm.store.set_meta("embedder_signature", "old")
    mm2 = MemoryManager(MemoryStore(db))
    assert mm2.store.get_meta("embedder_signature") == mm2.embedder.signature
