from data360 import datasets
from data360.synthetic import generate


def test_real_data_cached():
    docs = datasets.reference_docs()
    so = datasets.stackoverflow_questions()
    assert len(docs) >= 100 and all(d["source_url"].startswith("https://") for d in docs)
    assert len(so) >= 40 and all(q["link"].startswith("https://stackoverflow.com/") for q in so)
    assert all(q["author"] and q["license"].startswith("CC BY-SA") for q in so)
    pen = datasets.penguins()
    assert len(pen) == 344 and set(pen.species.unique()) == {"Adelie", "Chinstrap", "Gentoo"}


def test_canonical_set_matches_proposal():
    ev = datasets.canonical_events()
    assert len(ev) == 28
    assert len({e["learner_id"] for e in ev}) == 3
    assert len({e["session_id"] for e in ev}) == 12
    assert sum(1 for e in ev if e["supersedes"]) == 3
    assert sum(1 for e in ev if e["event_type"] == "distractor") == 4
    assert len(datasets.canonical_probes()) == 14


def test_generator_is_seeded_and_ordered():
    a = generate(6, seed=7)
    b = generate(6, seed=7)
    c = generate(6, seed=8)
    assert a == b and a != c
    events, probes = a
    assert all(e["synthetic"] for e in events)
    by_l = {}
    for e in events:
        by_l.setdefault(e["learner_id"], []).append(e["timestamp"])
    from data360.timeutil import parse
    for ts in by_l.values():
        assert [parse(t) for t in ts] == sorted(parse(t) for t in ts), "events per learner in time order"
    ids = {e["event_id"] for e in events}
    for p in probes:
        assert set(p["expected_event_ids"]) <= ids and set(p["must_not_return"]) <= ids
    for e in events:
        if e["supersedes"]:
            assert e["supersedes"] in ids


def test_generated_files_exist():
    assert len(datasets.generated_events()) > 100
    assert len(datasets.generated_probes()) > 30
