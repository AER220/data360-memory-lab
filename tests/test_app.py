"""Headless Streamlit tests: every page imports and renders without an exception."""
# Headless Streamlit tests using AppTest, which runs the real page scripts without a browser.
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
# Every page file, plus the entry point.
PAGES = ["app.py"] + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "pages").glob("*.py"))


@pytest.fixture(autouse=True)
# Each test uses its own temporary database, so tests never touch the real store.
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA360_DB", str(tmp_path / "app.db"))
    monkeypatch.chdir(ROOT)


def _clean(at):
    assert len(at.exception) == 0, [e.value for e in at.exception]


@pytest.mark.parametrize("page", PAGES)
# Smoke test: every page runs headless without an exception.
def test_page_renders(page):
    at = AppTest.from_file(str(ROOT / page), default_timeout=120)
    at.run()
    _clean(at)


def _btn(at, label):
    return next(b for b in at.button if b.label == label)


# End to end chat: load data, ask, check the remembered fact, approve a new memory.
def test_chat_flow_with_memory():
    at = AppTest.from_file(str(ROOT / "pages/2_Chat_and_Memory.py"), default_timeout=120)
    at.run()
    _btn(at, "Load course set (3 learners)").click().run()
    _clean(at)
    at.selectbox[0].set_value("syn_L01").run()
    at.chat_input[0].set_value("Which R environment do I use now?").run()
    _clean(at)
    text = " ".join(m.value for m in at.markdown)
    assert "e009" in text and "Posit Cloud" in text
    at.chat_input[0].set_value("I prefer comments on every line of R code.").run()
    _clean(at)
    _btn(at, "Approve").click().run()
    _clean(at)


# The evaluation runs from the page and shows results.
def test_evaluation_page_runs():
    at = AppTest.from_file(str(ROOT / "pages/4_Evaluation.py"), default_timeout=300)
    at.run()
    _btn(at, "Run evaluation").click().run()
    _clean(at)
    assert len(at.dataframe) >= 1


# Consolidation works from the Timeline page.
def test_timeline_page_maintenance():
    at = AppTest.from_file(str(ROOT / "pages/3_Memory_Timeline.py"), default_timeout=120)
    at.run()
    _btn(at, "Load course set (3 learners)").click().run()
    _clean(at)
    _btn(at, "Consolidate now").click().run()
    _clean(at)
