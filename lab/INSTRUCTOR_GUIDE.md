# Instructor guide: Data360-Memory lab

For the presenting team, TAs and the course instructor. Students do not need this file.

## Goal and fit with the presentation brief

The brief asks for a concept explanation, applications, one concrete implementation (vector store, read/write cycle, memories injected into the prompt), five interactive questions, and a 40 minute lab with a 5 minute walkthrough. This project covers each part:

| Brief item | Where it lives |
|---|---|
| Concept, memory types | Overview page; `lab/LAB.md` table |
| Applications | Overview page; Chat and Memory page (R tutoring across sessions) |
| Implementation and read/write cycle | `data360/memory.py`, Chat and Memory page inspector, exact prompt |
| Five questions with delayed answers | `lab/EXAM_QUESTIONS.md` (also on the Lab page with Reveal buttons) |
| 40 minute lab + walkthrough | `lab/LAB.md`, `lab/starter/`, `lab/checks/`, `lab/solutions/` |

## Before class (preflight, 15 minutes, once per machine)

1. `python -m venv .venv`, activate it, `pip install -r requirements.txt`.
2. `python lab/check.py --solutions` must print `16/16 checks pass`.
3. `python lab/check.py` must print `0/16` with every line `TODO`. That confirms the starter is clean.
4. `streamlit run app.py`, click **Load course set (3 learners)**, open each page once.
5. No internet is needed in class: the real data is cached in `data/real/`, and the default embeddings (TF-IDF) are fitted locally in about a second. Only stretch C downloads a model.

If you edit the solutions, regenerate the starter with `python scripts/make_starter.py`.

## Timing and expected outputs

| Time | Students do | They should see |
|---|---|---|
| 0:00 to 0:05 | Watch walkthrough | `e009` in the reply; `e003` as history; prompt labels memory as data |
| 0:05 to 0:10 | Exercise 1 | 24 kept, 4 skipped |
| 0:10 to 0:17 | Exercise 2 | `e003.superseded_by == "e009"`; reopened store has 24 records |
| 0:17 to 0:22 | Exercise 3 | `e003` current on 1 Oct; `e009` current on 12 Nov |
| 0:22 to 0:30 | Exercise 4 | pipe question returns `e007`, `e010`; no `e201` for `syn_L02` |
| 0:30 to 0:35 | Exercise 5 | ids and warning in the prompt, warning before data |
| 0:35 to 0:38 | Exercise 6 | 14/14 core checks PASS |
| 0:38 to 0:40 | Evaluation page | naive memory leaks stale and cross-learner records, policy shows 0 |

Reference results with the default TF-IDF embeddings (course set, 14 probes):

| Condition | recall@context | stale-fact probes | cross-learner probes | correct abstentions |
|---|---|---|---|---|
| no memory | 0.00 | 0 | 0 | 3/3 (trivial) |
| naive memory | 0.71 | 3 | 12 | 0/3 |
| Data360 policy | 0.71 | 0 | 0 | 3/3 |

The point to land: **retrieval alone recalled the same facts; the policy removed every stale and cross-learner leak.** Run the Evaluation page before class to confirm the numbers on your machine.

## Common errors and the hint to give

| Symptom | Cause | Hint |
|---|---|---|
| ex1 count is 28 | kept the distractors | "Which memory_type means nothing to remember?" |
| ex2 deletes `e003` | treated correction as delete | "History matters. Mark, do not remove." |
| ex2 unseen test fails | did not check the learner id of the old record | "Who is allowed to change a learner's facts?" |
| ex3 offset test fails | string comparison of timestamps | "Use `parse()`." |
| ex4 leaks `e201` | filtered after ranking | "Filter first, then search." |
| ex4 returns `e003` today | forgot `is_current` | "Which records are current right now?" |
| ex5 order test fails | warning placed after memory | "The model reads top to bottom." |
| ex6 restart test fails | forgot `store.save()` or the vector | "Is it gone from disk, and from both dicts?" |

## Grading suggestion (if the lab is collected)

* 60%: core checks (14 checks, `python lab/check.py`), all or nothing per exercise.
* 20%: one-sentence limitation written at 0:38, specific and correct.
* 20%: answers to two of the five exam questions.
* Stretch A or B: up to 10% extra.

## Talking points and honest limits

* TF-IDF embeddings are lexical. They work on this vocabulary because R error messages are distinctive, but paraphrases are weaker. Stretch C swaps in `all-MiniLM-L6-v2`, the model named in the proposal.
* The profile (current preferences) is always injected, which fixes the known gap where "How do I like explanations?" fell below the relevance cut-off.
* Similarity cannot abstain on its own. The reply layer abstains when nothing relevant was retrieved for a personal question; with an LLM, test this again.
* Forgetting trades recall for focus: the `+ forgetting` row loses recall on purpose.
* Real deployment would involve education records under FERPA and needs consent and university approval. This lab uses fictional learners only.

## Resetting between sections

Click **Reset all memories** in the sidebar, or delete `data/store/memory.db`. Student lab stores live in temporary folders created by the checks, so nothing needs cleaning.
