"""trending モジュールのテスト。"""

from typing import Any

import httpx
import respx

from thesis_ai.papers.models import Paper
from thesis_ai.papers.trending import (
    HF_DAILY_PAPERS_URL,
    _parse_hf_entry,
    fetch_trending_papers,
    pick_top_paper,
)


def _entry(**paper: Any) -> dict[str, Any]:
    return {"paper": paper, "title": paper.get("title")}


def test_parse_hf_entry_full() -> None:
    entry = _entry(
        id="2606.03108",
        title="Cool Paper",
        authors=[{"name": "Alice"}, {"name": "Bob"}, {"hidden": True}],
        summary="abstract text",
        ai_summary="ai summary",
        ai_keywords=["kw1", "kw2"],
        upvotes=42,
    )

    paper = _parse_hf_entry(entry)

    assert paper is not None
    assert paper.title == "Cool Paper"
    assert paper.authors == ("Alice", "Bob")
    assert paper.abstract == "abstract text"
    assert paper.arxiv_id == "2606.03108"
    assert paper.url == "https://arxiv.org/abs/2606.03108"
    assert paper.ai_summary == "ai summary"
    assert paper.ai_keywords == ("kw1", "kw2")
    assert paper.upvotes == 42


def test_parse_hf_entry_missing_title_returns_none() -> None:
    assert _parse_hf_entry({"paper": {"id": "x"}}) is None


def test_parse_hf_entry_tolerates_missing_keys() -> None:
    paper = _parse_hf_entry({"paper": {"title": "Only Title"}})

    assert paper is not None
    assert paper.title == "Only Title"
    assert paper.authors == ()
    assert paper.upvotes is None
    assert paper.url == ""


@respx.mock
async def test_fetch_trending_papers_parses_response() -> None:
    payload = [
        _entry(id="1111.00001", title="P1", upvotes=3),
        _entry(id="2222.00002", title="P2", upvotes=9),
        {"paper": {}},  # title 欠如 → スキップ
    ]
    respx.get(HF_DAILY_PAPERS_URL).mock(return_value=httpx.Response(200, json=payload))

    async with httpx.AsyncClient() as client:
        papers = await fetch_trending_papers(client, limit=10)

    assert [p.title for p in papers] == ["P1", "P2"]


@respx.mock
async def test_fetch_trending_papers_non_list_returns_empty() -> None:
    respx.get(HF_DAILY_PAPERS_URL).mock(return_value=httpx.Response(200, json={"error": "x"}))

    async with httpx.AsyncClient() as client:
        assert await fetch_trending_papers(client) == []


def test_pick_top_paper_returns_highest_upvotes() -> None:
    low = Paper(title="low", authors=(), abstract="", url="", upvotes=2)
    high = Paper(title="high", authors=(), abstract="", url="", upvotes=10)
    none = Paper(title="none", authors=(), abstract="", url="", upvotes=None)

    assert pick_top_paper([low, high, none]) is high


def test_pick_top_paper_empty_returns_none() -> None:
    assert pick_top_paper([]) is None
