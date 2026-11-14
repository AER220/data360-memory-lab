# Data sources

Data360-Memory uses **real public data** for reference knowledge and analysis, and **synthetic data** for learner memory. No real student records are used anywhere.

All real data was fetched on **14 November 2026 at 08:15 UTC (03:15 in Syracuse, EST)** by `scripts/fetch_real_data.py` and is cached in `data/real/`, so the app and tests run offline. Run the script again with internet access to refresh it. `data/real/manifest.json` records the fetch time, counts and URLs.

## 1. R documentation pages (reference knowledge for RAG)

File: `data/real/reference_docs.jsonl`, 216 text chunks from 22 pages. Each chunk keeps its `source_url`.

| Package | Pages | Licence of the documentation |
|---|---|---|
| dplyr | [filter](https://dplyr.tidyverse.org/reference/filter.html), [mutate](https://dplyr.tidyverse.org/reference/mutate.html), [select](https://dplyr.tidyverse.org/reference/select.html), [arrange](https://dplyr.tidyverse.org/reference/arrange.html), [summarise](https://dplyr.tidyverse.org/reference/summarise.html), [group_by](https://dplyr.tidyverse.org/reference/group_by.html), [joins](https://dplyr.tidyverse.org/reference/mutate-joins.html) | MIT |
| magrittr | [pipe %>%](https://magrittr.tidyverse.org/reference/pipe.html) | MIT |
| ggplot2 | [ggplot](https://ggplot2.tidyverse.org/reference/ggplot.html), [aes](https://ggplot2.tidyverse.org/reference/aes.html), [geom_point](https://ggplot2.tidyverse.org/reference/geom_point.html), [geom_histogram](https://ggplot2.tidyverse.org/reference/geom_histogram.html), [facet_wrap](https://ggplot2.tidyverse.org/reference/facet_wrap.html) | MIT |
| tidyr | [pivot_longer](https://tidyr.tidyverse.org/reference/pivot_longer.html), [drop_na](https://tidyr.tidyverse.org/reference/drop_na.html) | MIT |
| readr | [read_csv](https://readr.tidyverse.org/reference/read_delim.html) | MIT |
| stats, base (R manual pages) | [lm](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/lm.html), [library](https://stat.ethz.ch/R-manual/R-devel/library/base/html/library.html), [factor](https://stat.ethz.ch/R-manual/R-devel/library/base/html/factor.html), [NA](https://stat.ethz.ch/R-manual/R-devel/library/base/html/NA.html) | GPL-2 / GPL-3 (part of R) |
| jsonlite | [quick start vignette](https://cran.r-project.org/web/packages/jsonlite/vignettes/json-aaquickstart.html) | MIT |
| palmerpenguins | [package site](https://allisonhorst.github.io/palmerpenguins/) | CC0 |

Short excerpts are stored for teaching and retrieval only, each with its link. For use beyond the classroom, check each project's licence page.

## 2. Real Stack Overflow questions about R errors

File: `data/real/stackoverflow_r_errors.jsonl`, 66 questions tagged `[r]`, fetched with the public [Stack Exchange API](https://api.stackexchange.com/docs/advanced-search) (`/2.3/search/advanced`, title search, sorted by votes, no key) for these error messages:

`could not find function`, `object not found`, `there is no package called`, `non-numeric argument to binary operator`, `aesthetics must be either length 1`, `unexpected symbol`, `arguments imply differing number of rows`, `NAs introduced by coercion`, `cannot open file`, `subscript out of bounds`, `lexical error invalid char in json text` (one more search, `must be size or 1`, returned nothing).

Stored per question: title, a 120-word excerpt of the question body, tags, score, answer count, creation time (UTC), author display name and link. Stack Overflow user content is licensed **CC BY-SA** (2.5, 3.0 or 4.0 depending on the post date); attribution is the author name plus the link, kept in every row and shown in the app.

How it is used: (a) as reference knowledge (the tutor can point to a real thread), and (b) as the model for the synthetic learners' error events. Each generated error event links to a matching real thread in `source_url`.

## 3. palmerpenguins dataset (analysis data)

File: `data/real/penguins.csv`, 344 rows, from <https://raw.githubusercontent.com/allisonhorst/palmerpenguins/main/inst/extdata/penguins.csv>. Licence: **CC0**. Horst AM, Hill AP, Gorman KB (2020). palmerpenguins: Palmer Archipelago (Antarctica) penguin data. R package version 0.1.0. The same data is built into base R from version 4.5.0 as `penguins`.

## 4. Lab notes

File: `data/real/lab_reference_notes.jsonl`, 8 short notes written for the lab by the team, each pointing to a public source. Carried over from the earlier Data360 prototype.

## 5. Synthetic learner data (memory)

| File | What it is |
|---|---|
| `data/synthetic/canonical_events.jsonl` | The hand-written course set from the proposal: 3 learners, 12 sessions, 28 events, 3 corrections, 4 distractors |
| `data/synthetic/canonical_probes.jsonl` | 14 probe questions (information extraction, multi-session, knowledge update, temporal, abstention, privacy isolation) |
| `data/synthetic/generated_events.jsonl` | 278 events for 12 learners from `python -m data360.synthetic --learners 12 --seed 360` |
| `data/synthetic/generated_probes.jsonl` | 75 probes generated with the events, with expected and forbidden memory ids |

Every learner is fictional and every row has `"synthetic": true`. The generator is seeded (same seed, same output) and documented in `data360/synthetic.py`. Ids `syn_L01` to `syn_L03` are the course set; `syn_G001` onward are generated.

## Not used (and why)

* **R for Data Science (2e)**: CC BY-NC-ND, so we link to <https://r4ds.hadley.nz/> instead of copying text.
* **Course lecture notes and labs**: only with the professor's permission, kept local and never committed or shared.
* **LongMemEval** (<https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned>, MIT) and **LoCoMo** (<https://github.com/snap-research/locomo>, CC BY-NC 4.0): optional public long-term memory benchmarks for a later extension. Our probe categories follow LongMemEval's.
