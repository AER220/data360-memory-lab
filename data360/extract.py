"""Turn a learner's chat message into candidate memories (rule based, no API key).

Candidates are only proposals: the learner approves, edits or rejects them in the app.
"""
# Turns a chat message into a candidate memory. This is the 'propose' step of the memory loop; the
# human approval step lives on the Chat page.
from __future__ import annotations

import re

# Word lists for the rules below. I used rules instead of an LLM so memory proposals are predictable,
# free and testable.
ENV_WORDS = r"(rstudio|posit cloud|posit|vs ?code|jupyter|positron|windows|mac|macbook|chromebook|linux)"
SMALL_TALK = r"\b(weather|raining|coffee|lunch|football|soup|recipe|wi-?fi|bookstore|weekend|hello|hi there|thanks?)\b"
# Words about how an answer is presented. Together with "I prefer/want/need" they mark a style
# preference, and I accept typos such as "prefere" because learners type fast.
PRESENTATION = r"\b(short|shorter|brief|concise|detailed|long|longer|simple|step[- ]by[- ]step|comments?|bullets?|examples?|answers?|responses?|replies|explanations?)\b"
R_WORDS = r"(\br\b|dplyr|ggplot|tidyr|readr|%>%|\|>|lm\(|data ?frame|tibble|function|vector|factor|csv|json|plot|mean|na\.rm|package|library|pipe|error|warning|regression|penguins)"


# I propose at most one memory per message. Nothing is saved here: the learner must approve the card
# in the app first.
def propose(message: str) -> list[dict]:
    """Return 0 or 1 candidate memory dicts (memory_type, event_type, topic, slot, importance, text)."""
    msg = message.strip()
    low = msg.lower()
    if not msg:
        return []
    # A question such as "how do I prefer my answers?" asks ABOUT a preference; it must never be
    # saved as one, even though it contains the word "prefer".
    is_question = msg.endswith("?") or bool(re.match(r"(how|what|which|why|when|where|who|do|does|did|can|could|should|is|are)\b", low))
    # Words like 'actually' or 'switched' mark a correction, which later replaces the old fact instead
    # of sitting next to it.
    is_correction = bool(re.search(r"\b(correction|actually|not anymore|no longer|switched|moved to|changed to|instead now)\b", low))

    # Accessibility needs come first and get the highest importance, because forgetting them harms the
    # learner most.
    if re.search(r"(screen reader|colou?r ?blind|dyslexi|low vision|hard of hearing|large text)", low):
        return [dict(memory_type="semantic", event_type="correction" if is_correction else "preference_stated",
                     topic="accessibility", slot="accessibility", importance=9, text=msg)]
    # Setup statements (RStudio, Posit Cloud, laptop) go into the 'environment' slot, so a newer one
    # supersedes the older one.
    if re.search(r"\b(i (now )?use|i'?m using|i am using|i switched|i moved|i work in|my laptop|i code in)\b", low) and re.search(ENV_WORDS, low):
        return [dict(memory_type="semantic", event_type="correction" if is_correction else "preference_stated",
                     topic="environment", slot="environment", importance=8 if is_correction else 6, text=msg)]
    # Stated preferences about explanations or answer length go into the 'style' slot as semantic
    # memories, so they join the learner's profile and are applied to every later answer.
    if not is_question and (re.search(r"\b(i prefer|i like|please (always|keep|give|stop|don'?t|use|explain|show)|explain .* (step|short|simple)|i learn better)\b", low)
                            or (re.search(r"\bi (really |would |'d )?(prefer\w*|want|need|like)\b", low) and re.search(PRESENTATION, low))
                            or re.search(r"\bkeep (it|them|answers?|responses?|explanations?|replies) (short|brief|simple|concise)", low)):
        return [dict(memory_type="semantic", event_type="correction" if is_correction else "preference_stated",
                     topic="style", slot="style", importance=8 if is_correction else 7, text=msg)]
    # A strategy that worked becomes a procedural memory: a tutoring move worth repeating.
    if re.search(r"\b(that (helped|worked)|it worked|this fixed|fixed it|now it works)\b", low):
        return [dict(memory_type="procedural", event_type="strategy_outcome", topic=_topic(low), slot="",
                     importance=7, text=msg)]
    # An error becomes an episodic memory, so repeated errors across sessions can be spotted and
    # consolidated.
    if re.search(r"(error|warning|could not find|not found|unexpected|doesn'?t work|won'?t run|returns? na)", low):
        return [dict(memory_type="episodic", event_type="error_encountered", topic=_topic(low), slot="",
                     importance=6, text=msg)]
    # Small talk is never proposed. Storing it would waste the memory budget and could leak private
    # details.
    if re.search(SMALL_TALK, low) and not re.search(R_WORDS, low):
        return []  # small talk: the write filter would skip it anyway
    # A substantial R question is kept as a low-importance episode.
    if re.search(R_WORDS, low) and len(low.split()) >= 4:
        return [dict(memory_type="episodic", event_type="question_asked", topic=_topic(low), slot="",
                     importance=4, text=f"Asked: {msg}")]
    return []


# A rough topic label lets consolidation group related episodes, for example all pipe (%>%) errors.
def _topic(low: str) -> str:
    for pat, topic in [(r"%>%|\|>|dplyr|filter|mutate|summari[sz]e|group_by", "dplyr"), (r"ggplot|aes|geom", "ggplot2"),
                       (r"json", "JSON"), (r"\blm\b|lm\(|regression|coefficient", "lm"), (r"\bna\b|missing|na\.rm", "missing"),
                       (r"csv|read_|working directory|file", "import"), (r"factor", "factors"),
                       (r"package|library|install", "packages"), (r"not found|object", "objects")]:
        if re.search(pat, low):
            return topic
    return "general"
