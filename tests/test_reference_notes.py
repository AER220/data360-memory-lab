"""Tests for the v4 R reference notes, the Sources block and a brand new user end to end."""
# These tests check that the R reference notes are complete and verified, that every answer ends with
# a Sources block, that off-topic questions are declared "not covered", and that a classmate can
# create a new user and chat straight away. No network and no API key are needed.
import re
import sys
import types
from pathlib import Path

import pytest

from data360 import answer, datasets, knowledge
from data360.prompting import build_prompt
from data360.sources import NOT_COVERED, sources_block, with_sources

ROOT = Path(__file__).resolve().parents[1]
NOTES = datasets.r_notes()
BY_ID = {n["note_id"]: n for n in NOTES}
# Official documentation sites only (CRAN, R help pages, tidyverse, package sites, Posit).
OFFICIAL = re.compile(r"^https://(cran\.r-project\.org|stat\.ethz\.ch/R-manual|www\.rdocumentation\.org/packages|"
                      r"[a-z0-9]+\.tidyverse\.org|shiny\.posit\.co|posit\.cloud|docs\.posit\.co|keras3\.posit\.co|"
                      r"topepo\.github\.io/caret|juliasilge\.github\.io/tidytext|quanteda\.io|michael\.hahsler\.net/arules|"
                      r"jeroen\.r-universe\.dev/jsonlite)/")
DASHES = re.compile("[\u2013\u2014]")


# ---------- the notes themselves ----------

def test_at_least_fifty_notes_with_required_fields():
    assert len(NOTES) >= 50
    assert len(BY_ID) == len(NOTES), "note ids must be unique"
    for n in NOTES:
        for f in ("note_id", "title", "topic", "syllabus_week", "text", "source_url", "check_terms"):
            assert n.get(f) not in (None, "", []), (n["note_id"], f)
        assert 60 <= len(n["text"]) <= 600, n["note_id"]
        assert not DASHES.search(n["text"] + n["title"]), n["note_id"]


# Every link was fetched by scripts/verify_reference_notes.py: HTTP 200 and the topic words on the page.
def test_every_source_is_official_and_verified():
    for n in NOTES:
        assert OFFICIAL.match(n["source_url"]), n["source_url"]
        assert n.get("verified") is True and n.get("http_status") == 200, n["note_id"]
        assert n.get("verified_utc", "").startswith("20"), n["note_id"]


# R for Data Science 2e is CC BY-NC-ND: it may only appear as a further-reading link, never as a source.
def test_r4ds_is_link_only():
    for n in NOTES:
        assert "r4ds" not in n["source_url"]
        if n.get("further_reading"):
            assert n["further_reading"].startswith("https://r4ds.hadley.nz/")


# Every lecture in the IST 387/687 schedule (1 to 12) has notes, and each lab focus has its own note.
def test_every_syllabus_lecture_is_covered():
    weeks = {n["syllabus_week"] for n in NOTES}
    assert set(range(1, 13)) <= weeks
    for w in range(1, 13):
        assert sum(n["syllabus_week"] == w for n in NOTES) >= 3, w
    blob = " ".join(n["title"] + " " + n["text"] for n in NOTES).lower()
    for topic in ["posit cloud", "rstudio", "data frame", "mean(", "function(", "sample(", "set.seed", "t.test",
                  "fromjson", "ggplot", "map_data", "lm(", "ksvm", "rpart", "apriori", "shinyapp", "keras3",
                  "wordcloud", "get_sentiments", "%>%", "group_by", "na.rm"]:
        assert topic in blob, topic


# ---------- retrieval and coverage ----------

@pytest.mark.parametrize("question,expected", [
    ("How do I filter rows in R?", "N028"),
    ("Why do I keep getting could not find function %>%?", "N035"),
    ("How do I read a JSON file?", "N064"),
    ("How do I fit a linear regression?", "N085"),
    ("What does lift mean in association rules?", "N102"),
    ("How do I build a Shiny app with a slider?", "N103"),
    ("How do I make a word cloud?", "N112"),
    ("How do I split data into training and test sets?", "N091"),
    ("How do I draw a map of US states?", "N081"),
    ("How do I do sentiment analysis?", "N114"),
])
def test_course_questions_find_the_right_note(question, expected):
    ids = [r["chunk_id"] for r in knowledge.search(question) if r["kind"] == "note"]
    assert expected in ids, (question, ids)


@pytest.mark.parametrize("question", ["What is the capital of France?", "How do I cook rice?", "hello",
                                      "Explain photosynthesis", "Write me a poem about the sea"])
def test_off_topic_questions_are_not_covered(question):
    refs = knowledge.search(question)
    assert refs == [] and not knowledge.covered(refs)


# ---------- the Sources block ----------

def test_sources_block_lists_ids_titles_and_verified_links():
    refs = knowledge.search("How do I make a word cloud?")
    block = sources_block(refs, "Use wordcloud() [N112].")
    assert block.splitlines()[2] == "**Sources**"
    assert "[N112] R reference note: Word clouds: [" + BY_ID["N112"]["source_url"] + "]" in block
    assert "(cited)" in block


def test_sources_block_says_plainly_when_not_covered():
    assert NOT_COVERED in sources_block([], "anything")


# A model that writes its own source list gets it replaced by the app's verified block.
def test_model_written_sources_are_replaced():
    refs = knowledge.search("How do I make a word cloud?")
    text = with_sources("Use wordcloud() [N112].\n\nSources:\n- https://made-up.example.com", refs)
    assert "made-up.example.com" not in text and text.count("**Sources**") == 1


# The offline template: a general question answered from the notes, an off-topic one declared not
# covered, and both end with the Sources block.
def test_offline_reply_ends_with_sources():
    q = "How do I make a word cloud?"
    refs = knowledge.search(q)
    r = answer.reply(q, build_prompt(q, None, refs, memory_on=False), None, refs, False, provider_name="offline")
    assert "[N112]" in r.text
    tail = r.full_text.split("**Sources**")[-1]
    assert BY_ID["N112"]["source_url"] in tail
    q2 = "What is the capital of France?"
    r2 = answer.reply(q2, build_prompt(q2, None, [], memory_on=False), None, [], False, provider_name="offline")
    assert NOT_COVERED in r2.text and r2.full_text.rstrip().endswith(NOT_COVERED)


# Online mode (mocked): the prompt tells the model to cite only the provided notes and to say plainly
# when they do not cover the question, and the answer still ends with the app's Sources block.
def test_online_prompt_rules_and_sources(monkeypatch):
    sent = []
    oa = types.ModuleType("openai")

    class Completions:
        def create(self, **kw):
            sent.append(kw)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(content="Use wordcloud() [N112]."))])

    oa.OpenAI = lambda **kw: types.SimpleNamespace(chat=types.SimpleNamespace(completions=Completions()))
    monkeypatch.setitem(sys.modules, "openai", oa)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-notes-123456")
    q = "How do I make a word cloud?"
    refs = knowledge.search(q)
    r = answer.reply(q, build_prompt(q, None, refs, memory_on=False), None, refs, False, provider_name="openai")
    system = sent[0]["messages"][0]["content"]
    user = sent[0]["messages"][1]["content"]
    assert "answer only from the REFERENCE items provided" in system and NOT_COVERED in system
    assert "[N112] (note) Word clouds" in user and "http" not in user.split("<<REFERENCE")[1]
    assert r.provider == "openai" and r.full_text.startswith("Use wordcloud() [N112].")
    assert BY_ID["N112"]["source_url"] in r.full_text.split("**Sources**")[-1]
    # No references: the prompt says so, and the Sources block says not covered.
    p2 = build_prompt("What is the capital of France?", None, [], memory_on=False)
    assert "REFERENCE: none" in p2.user


# ---------- a brand new user, end to end ----------

def test_fresh_user_end_to_end(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    from data360.store import MemoryStore

    monkeypatch.setenv("DATA360_DB", str(tmp_path / "fresh.db"))
    monkeypatch.chdir(ROOT)
    at = AppTest.from_file(str(ROOT / "pages/2_Chat_and_Memory.py"), default_timeout=120)
    at.run()
    assert not at.exception
    # The demo learners are loaded, as on the class app, then a classmate creates their own user.
    next(b for b in at.button if b.label == "Load course set (3 learners)").click().run()
    next(s for s in at.selectbox if s.label == "Learner").set_value("+ new learner").run()
    next(t for t in at.text_input if t.label.startswith("New learner")).set_value("amy 2026!").run()
    assert any("New user `amy_2026`" in c.value for c in at.caption)
    # A general R question is answered from the shared notes, with the Sources block.
    at.chat_input[0].set_value("How do I make a word cloud?").run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "[N112]" in text and "**Sources**" in text and BY_ID["N112"]["source_url"] in text
    # Their private memory starts empty: a personal question gets an honest "no record".
    at.chat_input[0].set_value("Which R environment do I use now?").run()
    assert answer.NO_RECORD in " ".join(m.value for m in at.markdown)
    # They save a preference, and it is stored under their name only.
    at.chat_input[0].set_value("I prefer short answers").run()
    for _ in range(3):
        btns = [b for b in at.button if b.label == "Approve"]
        if not btns:
            break
        btns[0].click().run()
    assert not at.exception
    assert next(s for s in at.selectbox if s.label == "Learner").value == "amy_2026"
    store = MemoryStore(tmp_path / "fresh.db")
    assert [m.text for m in store.list("amy_2026") if m.slot == "style"] == ["I prefer short answers"]
    assert all(m.learner_id != "amy_2026" for m in store.list("syn_L01"))
    store.close()
    # A second browser session: amy is not listed for others, but typing the name brings her memory back.
    at2 = AppTest.from_file(str(ROOT / "pages/2_Chat_and_Memory.py"), default_timeout=120)
    at2.run()
    learner = next(s for s in at2.selectbox if s.label == "Learner")
    assert "amy_2026" not in learner.options and "syn_L01" in learner.options
    learner.set_value("+ new learner").run()
    next(t for t in at2.text_input if t.label.startswith("New learner")).set_value("amy_2026").run()
    assert any("Welcome back, `amy_2026`" in c.value for c in at2.caption)
    at2.chat_input[0].set_value("How do I like explanations?").run()
    assert "I prefer short answers" in " ".join(m.value for m in at2.markdown)
