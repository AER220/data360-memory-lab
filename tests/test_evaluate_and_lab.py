# Tests for the evaluation. The Lab 9 page has its own tests in test_lab9_page.py.
from data360 import knowledge
from data360.evaluate import evaluate, policy_checks


# The core claim: the Data360 policy beats no memory and naive memory, with zero leaks.
def test_memory_beats_baselines_canonical():
    s, _ = evaluate("canonical")
    s = s.set_index("condition")
    pol, naive, none = s.loc["Data360 policy"], s.loc["naive memory"], s.loc["no memory"]
    assert none["recall@context"] == 0 and pol["recall@context"] >= 0.6
    assert pol["probes with stale fact"] == 0 and pol["probes with other learner's memory"] == 0
    assert naive["probes with other learner's memory"] > 0
    assert pol["correct abstentions"] == "3/3"


# Same claim on the larger generated dataset.
def test_memory_beats_baselines_generated():
    s, _ = evaluate("generated", ["no memory", "naive memory", "Data360 policy"])
    s = s.set_index("condition")
    assert s.loc["Data360 policy", "recall@context"] > s.loc["naive memory", "recall@context"]
    assert s.loc["Data360 policy", "probes with stale fact"] == 0


# Every PASS/FAIL policy check passes.
def test_policy_checks_all_pass():
    res = policy_checks(fresh_process=True)
    assert len(res) >= 10
    assert all(r["result"] == "PASS" for r in res), [r for r in res if r["result"] != "PASS"]


# Reference search returns real documentation and Stack Overflow links.
def test_reference_search_returns_real_sources():
    hits = knowledge.search("could not find function %>% dplyr pipe")
    assert hits and all(h["source_url"].startswith("https://") for h in hits)
