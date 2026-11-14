"""Seeded synthetic learner generator (multi-session histories + probe questions).

Every learner, session and event is FICTIONAL. Error texts are modelled on real, public
Stack Overflow questions (data/real/stackoverflow_r_errors.jsonl) and each error event
links to a matching real thread in ``source_url`` when one is cached.

    python -m data360.synthetic --learners 12 --seed 360

Writes data/synthetic/generated_events.jsonl and generated_probes.jsonl.
Same seed, same output (Python's random.Random only, no global state).
"""
# Here I generate fictional learners and test questions. No real student data is used anywhere.
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone

from .paths import SYNTH

# All dates are synthetic, placed in the autumn 2026 term in Syracuse time.
TZ = timezone(timedelta(hours=-4))  # Syracuse, autumn (EDT); dates are synthetic
TERM_START = datetime(2026, 8, 31, tzinfo=TZ)

# Building blocks for fictional learners: setups, backgrounds, explanation styles and accessibility
# needs.
ENVIRONMENTS = ["RStudio Desktop on a Windows laptop", "RStudio Desktop on a MacBook", "Posit Cloud",
                "VS Code with the R extension", "Jupyter with the R kernel"]
BACKGROUNDS = [
    ("I am completely new to coding.", "beginner"),
    ("I know Python and pandas, so comparisons to pandas help me.", "python"),
    ("I use Excel every day at work but have never programmed.", "excel"),
    ("I took one statistics course that used SPSS.", "spss"),
]
STYLES = [
    "Please keep explanations short with one worked example.",
    "Please give step-by-step explanations with comments in the code.",
    "Please show me the base R version and the tidyverse version side by side.",
    "Please explain the idea in plain words before showing any code.",
]
ACCESSIBILITY = [
    "I use a screen reader. Describe every plot in words and never rely on colour alone.",
    "I am colour blind, so please use colour-blind-safe palettes and label lines directly.",
    "Large blocks of text are hard for me to read; please use short bullet points.",
]
# Off-topic small talk. The write filter should skip all of these, and the evaluation checks that it
# does.
DISTRACTORS = ["Mentioned it is raining and asked whether the library is open late.",
               "Asked for a good coffee place near campus.", "Asked how to reset a campus Wi-Fi password.",
               "Shared a favourite soup recipe.", "Talked about the weekend football game.",
               "Asked when the bookstore closes."]

# topic, Stack Overflow query it is modelled on, first-time text, repeat text, strategy that helped, mastery evidence
# Common beginner R errors, each modelled on a real public Stack Overflow question.
ERRORS = [
    ("dplyr", "could not find function",
     'Got Error: could not find function "%>%" because library(dplyr) was not loaded.',
     'Again got could not find function "%>%" in a new project; packages are not loaded automatically.',
     "Checking which packages are loaded with search() before debugging the pipe fixed the error quickly.",
     "Wrote a five-step dplyr pipeline with filter, group_by and summarise without hints."),
    ("objects", "object not found",
     "Got Error: object 'sales' not found because the line that created sales was never run.",
     "Again got object not found after restarting R; the script had not been re-run from the top.",
     "Running the script from the top with Ctrl+Shift+Enter showed which object was missing.",
     "Explained why objects disappear after restarting the R session."),
    ("packages", "there is no package called",
     "Got Error in library(ggplot2): there is no package called 'ggplot2'.",
     "Again saw there is no package called 'tidyr' in a fresh environment.",
     "Separating install.packages() (once) from library() (every session) made the difference clear.",
     "Installed and loaded a new package on their own and explained the difference."),
    ("types", "non-numeric argument to binary operator",
     "Got Error: non-numeric argument to binary operator because price was stored as character.",
     "Again got non-numeric argument to binary operator after reading a CSV with a dollar sign in a column.",
     "Showing str(df) first made the character column obvious.",
     "Converted a character column to numeric with as.numeric() and checked for NAs."),
    ("ggplot2", "aesthetics must be either length 1",
     "Got Error: Aesthetics must be either length 1 or the same as the data when adding a vector to ggplot.",
     "Again got Aesthetics must be either length 1 after mapping a summary vector in geom_line().",
     "Putting every variable in the same data frame before plotting solved the length mismatch.",
     "Built a scatter plot of flipper length against body mass with a correct aes() mapping."),
    ("syntax", "unexpected symbol",
     "Got Error: unexpected symbol because a comma was missing between two arguments.",
     "Again got unexpected symbol from an unclosed quote in a file path.",
     "Reading the line just before the reported position found the missing comma.",
     "Found and fixed a syntax error without help by reading the error position."),
    ("data frames", "arguments imply differing number of rows",
     "Got Error in data.frame(): arguments imply differing number of rows: 3, 4.",
     "Again got arguments imply differing number of rows when combining vectors of different lengths.",
     "Printing length() of each vector before data.frame() showed the mismatch.",
     "Built a data frame from three vectors of equal length correctly."),
    ("missing", "NAs introduced by coercion",
     "Got Warning: NAs introduced by coercion when converting a column with text like 'n/a' to numeric.",
     "mean() returned NA again because the column had missing values; needed na.rm = TRUE.",
     "Counting NAs with sum(is.na(x)) before and after conversion helped.",
     "Used na.rm = TRUE correctly and explained why mean() returns NA."),
    ("import", "cannot open file",
     "Got Error: cannot open file 'data.csv': No such file or directory; the working directory was wrong.",
     "Again got cannot open file because the CSV was uploaded to a different folder.",
     "Using getwd() and list.files() located the file before calling read_csv().",
     "Imported a CSV with read_csv() using a project-relative path."),
    ("JSON", "lexical error invalid char in json text",
     "Got lexical error: invalid char in json text because a file path was passed as text to fromJSON().",
     "fromJSON() returned a nested list again; needed flatten = TRUE to get a data frame.",
     "Showing str() of the nested list before fixing it helped the learner understand the structure.",
     "Turned a nested JSON response into a flat data frame with jsonlite."),
    ("indexing", "subscript out of bounds",
     "Got Error: subscript out of bounds when asking for column 10 of a data frame with 8 columns.",
     "Used df[0, ] expecting the first row like pandas; R indexing starts at 1.",
     "Checking dim(df) before indexing prevented the out-of-bounds error.",
     "Selected rows and columns with [ , ] indexing correctly on the penguins data."),
]
QUESTIONS = [
    ("lm", "Asked how to read the slope coefficient in lm() output on the penguins data."),
    ("lm", "Confused the slope coefficient with the correlation when reading lm() output."),
    ("factors", "Asked why summary() shows counts instead of a mean; the column was a factor."),
    ("ggplot2", "Asked how to add a title and axis labels to a ggplot."),
    ("tidyr", "Asked when to use pivot_longer() instead of pivot_wider()."),
    ("dplyr", "Asked the difference between summarise() and mutate()."),
    ("trees", "Asked how rpart chooses where to split a decision tree."),
    ("descriptive stats", "Asked how to compute the median body mass for each penguin species."),
]
# Questions with no answer in memory. A good system says it does not know.
ABSTAIN_QUESTIONS = ["What is my favourite colour for plots?", "What did I say about my SVM homework?",
                     "What is the name of my pet?", "Which football team do I support?"]


# These texts join the TF-IDF background corpus, so generated events use known vocabulary.
def template_texts() -> list[str]:
    """All template strings, used to fit the TF-IDF vocabulary."""
    out = list(ENVIRONMENTS) + [b for b, _ in BACKGROUNDS] + STYLES + ACCESSIBILITY + DISTRACTORS + ABSTAIN_QUESTIONS
    for e in ERRORS:
        out += list(e[2:])
    out += [q for _, q in QUESTIONS]
    return out


# For each error, the link to the highest-scored matching real Stack Overflow thread.
def _so_links() -> dict[str, str]:
    from .datasets import stackoverflow_questions

    links: dict[str, str] = {}
    for q in sorted(stackoverflow_questions(), key=lambda r: -r["score"]):
        links.setdefault(q["error_query"], q["link"])
    return links


# Generates learners and probe questions. Everything comes from one seeded random generator, so the
# same seed always gives the same data.
def generate(n_learners: int = 12, seed: int = 360, min_sessions: int = 4, max_sessions: int = 6,
             p_repeat: float = 0.4, p_env_change: float = 0.5, p_style_change: float = 0.4,
             p_accessibility: float = 0.2, p_distractor: float = 0.4) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    links = _so_links()
    events: list[dict] = []
    probes: list[dict] = []
    access_ids: dict[str, str] = {}

    for li in range(1, n_learners + 1):
        lid = f"syn_G{li:03d}"
        n_sess = rng.randint(min_sessions, max_sessions)
        weeks = sorted(rng.sample(range(2, 14), n_sess))
        counter = 0
        env = rng.choice(ENVIRONMENTS)
        background, bg_key = rng.choice(BACKGROUNDS)
        style = rng.choice(STYLES)
        change_env_at = rng.randint(2, n_sess) if rng.random() < p_env_change else None
        change_style_at = rng.randint(2, n_sess) if rng.random() < p_style_change else None
        has_access = rng.random() < p_accessibility
        seen_errors: list[int] = []
        sess_day = {i + 1: rng.randint(0, 4) for i in range(n_sess)}
        err_query: dict[str, str] = {}
        rec: dict[str, list] = {"env": [], "style": [], "errors": {}, "first_error": None}

        # Adds one event with a realistic timestamp inside the learner's session.
        def add(sess_no: int, minute: int, **kw) -> dict:
            nonlocal counter
            counter += 1
            week = weeks[sess_no - 1]
            ts = TERM_START + timedelta(weeks=week - 1, days=sess_day[sess_no], hours=18) + timedelta(minutes=minute)
            ev = {"event_id": f"g{li:03d}_{counter:02d}", "learner_id": lid, "session_id": f"sg{li:03d}_{sess_no}",
                  "timestamp": ts.isoformat(), "course_week": week, "supersedes": "", "slot": "",
                  "source_url": "", "synthetic": True}
            ev.update(kw)
            events.append(ev)
            return ev

        for s in range(1, n_sess + 1):
            minute = 0
            # Session 1: the learner states background, environment, style and maybe an accessibility
            # need.
            if s == 1:
                add(1, 0, topic="background", event_type="preference_stated", memory_type="semantic", importance=7,
                    slot="background", text=background)
                e = add(1, 3, topic="environment", event_type="preference_stated", memory_type="semantic",
                        importance=6, slot="environment", text=f"I use {env}.")
                rec["env"].append(e)
                e = add(1, 5, topic="style", event_type="preference_stated", memory_type="semantic", importance=7,
                        slot="style", text=style)
                rec["style"].append(e)
                if has_access:
                    e = add(1, 7, topic="accessibility", event_type="preference_stated", memory_type="semantic",
                            importance=9, slot="accessibility", text=rng.choice(ACCESSIBILITY))
                    access_ids[lid] = e["event_id"]
                minute = 10
            # Sometimes the learner switches environment later. The correction links to the old fact
            # with supersedes.
            if change_env_at == s:
                new_env = rng.choice([x for x in ENVIRONMENTS if x != env])
                old = rec["env"][-1]
                e = add(s, minute, topic="environment", event_type="correction", memory_type="semantic", importance=8,
                        slot="environment", supersedes=old["event_id"],
                        text=f"Correction: I switched from {env} to {new_env}.")
                rec["env"].append(e)
                env = new_env
                minute += 4
            # Same idea for a change of explanation style.
            if change_style_at == s:
                new_style = rng.choice([x for x in STYLES if x != style])
                old = rec["style"][-1]
                e = add(s, minute, topic="style", event_type="correction", memory_type="semantic", importance=8,
                        slot="style", supersedes=old["event_id"], text=f"Correction: {new_style}")
                rec["style"].append(e)
                style = new_style
                minute += 4
            # One or two errors per session; some repeat earlier ones, which is what consolidation
            # should catch.
            for _ in range(rng.randint(1, 2)):
                repeat = seen_errors and rng.random() < p_repeat
                idx = rng.choice(seen_errors) if repeat else rng.choice([i for i in range(len(ERRORS)) if i not in seen_errors])
                topic, soq, first, again, strategy, mastery = ERRORS[idx]
                e = add(s, minute, topic=topic, event_type="error_encountered", memory_type="episodic",
                        importance=7 if repeat else 6, text=again if repeat else first, source_url=links.get(soq, ""))
                rec["errors"].setdefault(idx, []).append(e)
                err_query[e["event_id"]] = soq
                if rec["first_error"] is None:
                    rec["first_error"] = e
                if not repeat:
                    seen_errors.append(idx)
                minute += 6
                if rng.random() < 0.5:
                    add(s, minute, topic=topic, event_type="strategy_outcome", memory_type="procedural", importance=7,
                        text=strategy)
                    minute += 3
                if repeat and rng.random() < 0.5:
                    add(s, minute, topic=topic, event_type="mastery_evidence", memory_type="semantic", importance=6,
                        text=f"Tentative mastery evidence (not a grade): {mastery}")
                    minute += 3
            if rng.random() < 0.6:
                topic, q = rng.choice(QUESTIONS)
                add(s, minute, topic=topic, event_type="question_asked", memory_type="episodic", importance=5, text=q)
                minute += 5
            # Sometimes add small talk, which should never be stored.
            if rng.random() < p_distractor:
                add(s, minute, topic="none", event_type="distractor", memory_type="none", importance=1,
                    text=rng.choice(DISTRACTORS))

        # ---------------- probes for this learner ----------------
        pid = 0

        # Each probe records the question, the memory ids that should be found and the ids that must
        # not appear.
        def probe(ability, question, expected, answer, must_not=(), as_of=""):
            nonlocal pid
            pid += 1
            probes.append({"question_id": f"{lid}_q{pid}", "learner_id": lid, "ability": ability,
                           "question": question, "expected_event_ids": list(expected), "expected_answer": answer,
                           "must_not_return": list(must_not), "as_of": as_of})

        env_ids = [e["event_id"] for e in rec["env"]]
        # Knowledge update: only the latest environment fact should be returned.
        probe("knowledge-update", "Which R environment do I use now?", [env_ids[-1]], rec["env"][-1]["text"],
              must_not=env_ids[:-1])
        style_ids = [e["event_id"] for e in rec["style"]]
        probe("knowledge-update", "How do I like explanations?", [style_ids[-1]], rec["style"][-1]["text"],
              must_not=style_ids[:-1])
        # Temporal reasoning: asking about the start of the course should return the old fact.
        if len(rec["env"]) > 1:  # point in time: before the correction, the old fact was current
            before = (datetime.fromisoformat(rec["env"][1]["timestamp"]) - timedelta(minutes=1)).isoformat()
            probe("temporal-reasoning", "Which R environment did I use at the start of the course?",
                  [env_ids[0]], rec["env"][0]["text"], must_not=env_ids[1:], as_of=before)
        repeats = [v for v in rec["errors"].values() if len(v) > 1]
        if repeats:
            evs = repeats[0]
            key = err_query[evs[0]["event_id"]]
            probe("multi-session", f"Why do I keep getting '{key}' in R?",
                  [evs[0]["event_id"], evs[-1]["event_id"]],
                  f"The same {evs[0]['topic']} problem happened in {len(evs)} sessions.")
        fe = rec["first_error"]
        if fe:
            probe("information-extraction", f"What happened with my {fe['topic']} problem: {fe['text'][:60]}",
                  [fe["event_id"]], fe["text"])
        # Abstention: nothing is recorded, so the right answer is 'I do not know'.
        probe("abstention", rng.choice(ABSTAIN_QUESTIONS), [], "Nothing recorded; the agent should say it does not know.")
        if not has_access:
            probe("privacy-isolation", "What accessibility needs did I mention?", [],
                  "None for this learner; other learners' accessibility memories must never be returned.",
                  must_not=[])  # filled after all learners exist

    # Privacy probes are completed last, once I know which other learners have accessibility memories.
    for p in probes:
        if p["ability"] == "privacy-isolation":
            p["must_not_return"] = [v for k, v in access_ids.items() if k != p["learner_id"]]
    return events, probes


# Saves the generated data as JSON Lines in data/synthetic.
def write(events: list[dict], probes: list[dict]) -> None:
    SYNTH.mkdir(parents=True, exist_ok=True)
    with open(SYNTH / "generated_events.jsonl", "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    with open(SYNTH / "generated_probes.jsonl", "w") as f:
        for p in probes:
            f.write(json.dumps(p) + "\n")


# Command-line entry: python -m data360.synthetic --learners 12 --seed 360
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--learners", type=int, default=12)
    ap.add_argument("--seed", type=int, default=360)
    a = ap.parse_args()
    ev, pr = generate(a.learners, a.seed)
    write(ev, pr)
    print(f"wrote {len(ev)} events and {len(pr)} probes for {a.learners} learners (seed {a.seed})")


if __name__ == "__main__":
    main()
