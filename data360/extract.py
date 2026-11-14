"""Turn a learner's chat message into candidate memories (rule based, no API key).

Candidates are only proposals: the learner approves, edits or rejects them in the app.
"""
from __future__ import annotations

import re

ENV_WORDS = r"(rstudio|posit cloud|posit|vs ?code|jupyter|positron|windows|mac|macbook|chromebook|linux)"
SMALL_TALK = r"\b(weather|raining|coffee|lunch|football|soup|recipe|wi-?fi|bookstore|weekend|hello|hi there|thanks?)\b"
R_WORDS = r"(\br\b|dplyr|ggplot|tidyr|readr|%>%|\|>|lm\(|data ?frame|tibble|function|vector|factor|csv|json|plot|mean|na\.rm|package|library|pipe|error|warning|regression|penguins)"


def propose(message: str) -> list[dict]:
    """Return 0 or 1 candidate memory dicts (memory_type, event_type, topic, slot, importance, text)."""
    msg = message.strip()
    low = msg.lower()
    if not msg:
        return []
    is_correction = bool(re.search(r"\b(correction|actually|not anymore|no longer|switched|moved to|changed to|instead now)\b", low))

    if re.search(r"(screen reader|colou?r ?blind|dyslexi|low vision|hard of hearing|large text)", low):
        return [dict(memory_type="semantic", event_type="correction" if is_correction else "preference_stated",
                     topic="accessibility", slot="accessibility", importance=9, text=msg)]
    if re.search(r"\b(i (now )?use|i'?m using|i am using|i switched|i moved|i work in|my laptop|i code in)\b", low) and re.search(ENV_WORDS, low):
        return [dict(memory_type="semantic", event_type="correction" if is_correction else "preference_stated",
                     topic="environment", slot="environment", importance=8 if is_correction else 6, text=msg)]
    if re.search(r"\b(i prefer|i like|please (always|keep|give|stop|don'?t|use|explain|show)|explain .* (step|short|simple)|i learn better)\b", low):
        return [dict(memory_type="semantic", event_type="correction" if is_correction else "preference_stated",
                     topic="style", slot="style", importance=8 if is_correction else 7, text=msg)]
    if re.search(r"\b(that (helped|worked)|it worked|this fixed|fixed it|now it works)\b", low):
        return [dict(memory_type="procedural", event_type="strategy_outcome", topic=_topic(low), slot="",
                     importance=7, text=msg)]
    if re.search(r"(error|warning|could not find|not found|unexpected|doesn'?t work|won'?t run|returns? na)", low):
        return [dict(memory_type="episodic", event_type="error_encountered", topic=_topic(low), slot="",
                     importance=6, text=msg)]
    if re.search(SMALL_TALK, low) and not re.search(R_WORDS, low):
        return []  # small talk: the write filter would skip it anyway
    if re.search(R_WORDS, low) and len(low.split()) >= 4:
        return [dict(memory_type="episodic", event_type="question_asked", topic=_topic(low), slot="",
                     importance=4, text=f"Asked: {msg}")]
    return []


def _topic(low: str) -> str:
    for pat, topic in [(r"%>%|\|>|dplyr|filter|mutate|summari[sz]e|group_by", "dplyr"), (r"ggplot|aes|geom", "ggplot2"),
                       (r"json", "JSON"), (r"\blm\b|lm\(|regression|coefficient", "lm"), (r"\bna\b|missing|na\.rm", "missing"),
                       (r"csv|read_|working directory|file", "import"), (r"factor", "factors"),
                       (r"package|library|install", "packages"), (r"not found|object", "objects")]:
        if re.search(pat, low):
            return topic
    return "general"
