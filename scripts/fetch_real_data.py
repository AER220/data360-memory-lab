"""Fetch the REAL public data used by Data360-Memory and cache it under data/real/.

Run once with internet access:  python scripts/fetch_real_data.py
The app and tests only read the cached files, so they work offline.

Sources (all public, see DATA_SOURCES.md for licences):
  1. Tidyverse and base R reference pages (HTML -> plain text chunks)
  2. Real Stack Overflow questions tagged [r] about common beginner errors
     (Stack Exchange API, CC BY-SA, attribution kept per row)
  3. The palmerpenguins dataset (CC0), the analysis data used in IST 387/687 style examples
"""
# Here I download the real public data once and cache it, so the deployed app works offline.
from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Everything fetched is cached in data/real, so the app and tests never need the internet.
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "real"
# A clear User-Agent is polite to the documentation sites and the Stack Exchange API.
UA = {"User-Agent": "Data360-Memory-Lab/1.0 (course project; contact: student)"}

# Real R documentation pages covering the topics beginners ask about most.
DOC_PAGES = [
    # (doc_id, package, topic, url)
    ("dplyr_filter", "dplyr", "dplyr", "https://dplyr.tidyverse.org/reference/filter.html"),
    ("dplyr_mutate", "dplyr", "dplyr", "https://dplyr.tidyverse.org/reference/mutate.html"),
    ("dplyr_select", "dplyr", "dplyr", "https://dplyr.tidyverse.org/reference/select.html"),
    ("dplyr_arrange", "dplyr", "dplyr", "https://dplyr.tidyverse.org/reference/arrange.html"),
    ("dplyr_summarise", "dplyr", "dplyr", "https://dplyr.tidyverse.org/reference/summarise.html"),
    ("dplyr_group_by", "dplyr", "dplyr", "https://dplyr.tidyverse.org/reference/group_by.html"),
    ("dplyr_join", "dplyr", "dplyr", "https://dplyr.tidyverse.org/reference/mutate-joins.html"),
    ("magrittr_pipe", "magrittr", "pipe", "https://magrittr.tidyverse.org/reference/pipe.html"),
    ("ggplot2_ggplot", "ggplot2", "ggplot2", "https://ggplot2.tidyverse.org/reference/ggplot.html"),
    ("ggplot2_aes", "ggplot2", "ggplot2", "https://ggplot2.tidyverse.org/reference/aes.html"),
    ("ggplot2_geom_point", "ggplot2", "ggplot2", "https://ggplot2.tidyverse.org/reference/geom_point.html"),
    ("ggplot2_geom_histogram", "ggplot2", "ggplot2", "https://ggplot2.tidyverse.org/reference/geom_histogram.html"),
    ("ggplot2_facet_wrap", "ggplot2", "ggplot2", "https://ggplot2.tidyverse.org/reference/facet_wrap.html"),
    ("tidyr_pivot_longer", "tidyr", "tidyr", "https://tidyr.tidyverse.org/reference/pivot_longer.html"),
    ("tidyr_drop_na", "tidyr", "missing", "https://tidyr.tidyverse.org/reference/drop_na.html"),
    ("readr_read_csv", "readr", "import", "https://readr.tidyverse.org/reference/read_delim.html"),
    ("stats_lm", "stats", "lm", "https://stat.ethz.ch/R-manual/R-devel/library/stats/html/lm.html"),
    ("base_library", "base", "packages", "https://stat.ethz.ch/R-manual/R-devel/library/base/html/library.html"),
    ("base_factor", "base", "factors", "https://stat.ethz.ch/R-manual/R-devel/library/base/html/factor.html"),
    ("base_na", "base", "missing", "https://stat.ethz.ch/R-manual/R-devel/library/base/html/NA.html"),
    ("jsonlite_quickstart", "jsonlite", "JSON", "https://cran.r-project.org/web/packages/jsonlite/vignettes/json-aaquickstart.html"),
    ("palmerpenguins_home", "palmerpenguins", "datasets", "https://allisonhorst.github.io/palmerpenguins/"),
]

# Error messages to search on Stack Overflow, each with the topic it belongs to.
SO_QUERIES = [
    ("could not find function", "packages"),
    ("object not found", "objects"),
    ("there is no package called", "packages"),
    ("non-numeric argument to binary operator", "types"),
    ("aesthetics must be either length 1", "ggplot2"),
    ("unexpected symbol", "syntax"),
    ("arguments imply differing number of rows", "data frames"),
    ("NAs introduced by coercion", "types"),
    ("cannot open file", "import"),
    ("subscript out of bounds", "indexing"),
    ("must be size or 1", "dplyr"),
    ("lexical error invalid char in json text", "JSON"),
]

PENGUINS_URL = "https://raw.githubusercontent.com/allisonhorst/palmerpenguins/main/inst/extdata/penguins.csv"


# Unescape HTML, replace dashes, and squeeze whitespace so chunks are clean plain text.
def clean_text(s: str) -> str:
    s = html.unescape(s)
    s = s.replace("\u2014", ", ").replace("\u2013", "-")  # no em or en dashes in our text
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


# Split a page into chunks of about 120 words, small enough to quote in a prompt.
def chunk(text: str, max_words: int = 120) -> list[str]:
    paras = [p.strip() for p in text.split("\n") if len(p.split()) >= 4]
    chunks, cur = [], []
    for p in paras:
        words = p.split()
        if len(cur) + len(words) > max_words and cur:
            chunks.append(" ".join(cur))
            cur = []
        cur.extend(words[: max_words * 2])
    if cur:
        chunks.append(" ".join(cur))
    return chunks


# Download each documentation page, strip navigation and scripts, and keep headings, paragraphs and
# code.
def fetch_docs() -> list[dict]:
    rows = []
    for doc_id, pkg, topic, url in DOC_PAGES:
        try:
            r = requests.get(url, headers=UA, timeout=30)
            r.raise_for_status()
        # One missing page should not stop the whole fetch.
        except Exception as exc:  # keep going, record the miss
            print(f"  MISS {url}: {exc}", file=sys.stderr)
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        main = soup.find("main") or soup.find("div", class_="contents") or soup.body or soup
        title = clean_text(soup.title.get_text()) if soup.title else doc_id
        blocks = []
        for el in main.find_all(["h1", "h2", "h3", "p", "li", "pre", "dt", "dd"]):
            if el.find_parent(["li", "dd", "pre"]) and el.name != "pre":
                continue  # avoid duplicating nested text
            t = " ".join(el.get_text(" ").split())
            if t:
                blocks.append(t)
        text = clean_text("\n".join(blocks))
        for i, c in enumerate(chunk(text)):
            rows.append({
                "chunk_id": f"{doc_id}#{i:02d}", "doc_id": doc_id, "package": pkg, "topic": topic,
                "title": title, "text": c, "source_url": url, "source_type": "documentation",
            })
        print(f"  doc {doc_id}: {len(text)} chars")
        # A short pause between requests so I do not hammer the servers.
        time.sleep(0.3)
    return rows


# Search the public Stack Exchange API for the most-voted [r] questions per error message. No key is
# needed for this small number of requests.
def fetch_stackoverflow(per_query: int = 6) -> list[dict]:
    rows, seen = [], set()
    for q, topic in SO_QUERIES:
        params = {
            "order": "desc", "sort": "votes", "title": q, "tagged": "r", "site": "stackoverflow",
            "pagesize": per_query, "filter": "withbody", "answers": 1,
        }
        r = requests.get("https://api.stackexchange.com/2.3/search/advanced", params=params, headers=UA, timeout=30)
        r.raise_for_status()
        data = r.json()
        for item in data.get("items", []):
            if item["question_id"] in seen:
                continue
            seen.add(item["question_id"])
            body = clean_text(BeautifulSoup(item.get("body", ""), "html.parser").get_text("\n"))
            rows.append({
                "question_id": item["question_id"],
                "title": clean_text(item["title"]),
                "body_excerpt": " ".join(body.split()[:120]),
                "tags": ";".join(item.get("tags", [])),
                "score": item.get("score", 0),
                "answer_count": item.get("answer_count", 0),
                "is_answered": item.get("is_answered", False),
                "created_utc": dt.datetime.fromtimestamp(item["creation_date"], dt.timezone.utc).isoformat(),
                # Author and link are kept on every row, as the CC BY-SA licence requires attribution.
                "author": clean_text(item.get("owner", {}).get("display_name", "unknown")),
                "link": item["link"],
                "error_query": q, "topic": topic,
                "license": "CC BY-SA (2.5, 3.0 or 4.0 depending on post date), Stack Overflow user content",
            })
        print(f"  SO '{q}': {len(data.get('items', []))} (quota left {data.get('quota_remaining')})")
        time.sleep(0.5)
    return rows


# Fetch everything, write the cache files and a manifest recording when and from where the data came.
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fetched = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    print("Fetching documentation pages ...")
    docs = fetch_docs()
    print("Fetching Stack Overflow questions ...")
    so = fetch_stackoverflow()
    print("Fetching palmerpenguins ...")
    pen = requests.get(PENGUINS_URL, headers=UA, timeout=30)
    pen.raise_for_status()
    (OUT / "penguins.csv").write_text(pen.text)
    with open(OUT / "reference_docs.jsonl", "w") as f:
        for r in docs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT / "stackoverflow_r_errors.jsonl", "w") as f:
        for r in so:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    manifest = {
        "fetched_utc": fetched,
        "reference_docs": {"chunks": len(docs), "pages": len({d['doc_id'] for d in docs})},
        "stackoverflow_r_errors": {"questions": len(so)},
        "penguins_rows": pen.text.count("\n") - 1,
        "sources": [u for *_, u in DOC_PAGES] + ["https://api.stackexchange.com/2.3/search/advanced", PENGUINS_URL],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2)[:800])


if __name__ == "__main__":
    main()
