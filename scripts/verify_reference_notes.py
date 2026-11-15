"""Check every R reference note's source link: HTTP 200 and the page really covers the note's topic.

For each note in data/real/r_reference_notes.jsonl I download the source page, strip the HTML, and
check that every word in the note's check_terms appears on the page (and that a #section anchor,
if the link has one, exists on the page). The result is written back into the note
(http_status, page_title, verified_utc, verified), so the app can show when each link was checked.

Usage (needs internet):  python scripts/verify_reference_notes.py
Exit code 1 if any note fails, so it can run in CI.
"""
# I verify links instead of trusting them, because a broken or wrong link would make the
# Sources block in every answer misleading.
from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

NOTES = Path(__file__).resolve().parents[1] / "data" / "real" / "r_reference_notes.jsonl"
HEADERS = {"User-Agent": "Mozilla/5.0 (Data360-Memory course project; link checker)"}


# Plain text of a page: scripts and styles removed, tags dropped, entities decoded.
def page_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw)))


# Checks one note and returns the updated record plus a list of problems (empty when it passes).
def check(note: dict, cache: dict) -> tuple[dict, list[str]]:
    url = note["source_url"]
    base, _, anchor = url.partition("#")
    # Several notes share a page, so I download each page only once.
    if base not in cache:
        try:
            r = requests.get(base, headers=HEADERS, timeout=30)
            cache[base] = (r.status_code, r.text)
        except requests.RequestException as exc:
            cache[base] = (0, str(exc))
    status, raw = cache[base]
    problems = [] if status == 200 else [f"HTTP {status}"]
    text = page_text(raw).lower()
    m = re.search(r"(?is)<title>(.*?)</title>", raw)
    title = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip() if m else ""
    # Our documents avoid long dashes, so I store page titles with " | " in their place.
    title = re.sub(r"\s*[\u2013\u2014]\s*", " | ", title)
    missing = [t for t in note.get("check_terms", []) if t.lower() not in text]
    if missing:
        problems.append(f"terms not on page: {missing}")
    if anchor and f'id="{anchor}"' not in raw and f"name=\"{anchor}\"" not in raw:
        problems.append(f"anchor #{anchor} not found")
    # Further reading (R4DS 2e) is a link only; I just check that it opens.
    fr = note.get("further_reading")
    if fr:
        if fr not in cache:
            try:
                cache[fr] = (requests.get(fr, headers=HEADERS, timeout=30).status_code, "")
            except requests.RequestException as exc:
                cache[fr] = (0, str(exc))
        if cache[fr][0] != 200:
            problems.append(f"further_reading HTTP {cache[fr][0]}")
    note = dict(note, http_status=status, page_title=title,
                verified_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                verified=not problems)
    return note, problems


def main() -> int:
    notes = [json.loads(line) for line in NOTES.read_text(encoding="utf-8").splitlines() if line.strip()]
    cache: dict = {}
    out, failed = [], 0
    for n in notes:
        n2, problems = check(n, cache)
        out.append(n2)
        flag = "OK  " if not problems else "FAIL"
        failed += bool(problems)
        print(f"{flag} {n['note_id']} {n2['http_status']} {n['source_url']} {'; '.join(problems)}")
    NOTES.write_text("".join(json.dumps(n, ensure_ascii=False) + "\n" for n in out), encoding="utf-8")
    print(f"{len(out) - failed}/{len(out)} notes verified, {len(cache)} pages fetched")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
