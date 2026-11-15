"""The Sources block that ends every answer: which shared references the answer was given, each with
its id, title and a clickable link."""
# I build the Sources block in code, not with the model, so the links are always the verified ones
# from our data files and a model can never invent a source.
from __future__ import annotations

import re

NOT_COVERED = "The reference notes do not cover this question."
R4DS_NOTE = "R for Data Science (2e), link only (CC BY-NC-ND)"

# A model sometimes writes its own "Sources:" list at the end despite the instructions. I cut it off,
# so only the app's verified block is shown.
_MODEL_SOURCES = re.compile(r"\n+\s*(\*\*|#+\s*)?(sources|references)\s*(\*\*)?\s*:?\s*(\*\*)?\s*\n[\s\S]*$", re.I)


def strip_model_sources(text: str) -> str:
    return _MODEL_SOURCES.sub("", text).rstrip()


# A readable label for each kind of reference.
def _label(r: dict) -> str:
    if r.get("kind") == "note":
        return f"R reference note: {r.get('title', '')}"
    if r.get("kind") == "stackoverflow":
        return f"Stack Overflow thread: {r.get('title', '')}"
    return f"R documentation excerpt: {r.get('title', '')}"


# The ids written in square brackets in an answer, for example [N028].
def cited_ids(text: str) -> set[str]:
    return set(re.findall(r"\[([A-Za-z0-9_#.\-]+)\]", text or ""))


def sources_block(refs: list[dict], answer_text: str = "") -> str:
    """Markdown block listing the references given to this answer.

    If the answer cites some of them by id, those are listed first and marked as cited. With no
    references at all, the block says plainly that the reference notes do not cover the question.
    """
    lines = ["", "---", "**Sources**"]
    if not refs:
        lines.append(f"- None. {NOT_COVERED}")
        return "\n".join(lines)
    cited = cited_ids(answer_text)
    # Cited references first, in the original order inside each group.
    ordered = sorted(refs, key=lambda r: r.get("chunk_id") not in cited)
    for r in ordered:
        rid = r.get("chunk_id", "")
        mark = " (cited)" if rid in cited else ""
        lines.append(f"- [{rid}] {_label(r)}: [{r.get('source_url', '')}]({r.get('source_url', '')}){mark}")
    # Further reading links (R4DS 2e) are links only; no text from the book is stored or shown.
    extra = sorted({r["further_reading"] for r in refs if r.get("further_reading")})
    for url in extra:
        lines.append(f"- Further reading, {R4DS_NOTE}: [{url}]({url})")
    return "\n".join(lines)


def with_sources(answer_text: str, refs: list[dict]) -> str:
    """The answer with any model-written source list removed and the app's Sources block appended."""
    body = strip_model_sources(answer_text)
    return body + "\n" + sources_block(refs, body)
