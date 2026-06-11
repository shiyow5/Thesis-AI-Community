"""resolve モジュール（ID 抽出・メタ解決）のテスト。"""

import httpx
import respx

from thesis_ai.papers.resolve import (
    ARXIV_API_URL,
    extract_arxiv_id,
    fetch_arxiv_metadata,
    resolve_paper,
)

_ATOM_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/{id}v1</id>
    <title>{title}</title>
    <summary>{summary}</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
  </entry>
</feed>"""

_EMPTY_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>"""


def _atom(id_: str = "1706.03762", title: str = "Attention Is All You Need") -> str:
    return _ATOM_TEMPLATE.format(id=id_, title=title, summary="We propose the Transformer.")


def test_extract_arxiv_id_from_abs_url() -> None:
    assert extract_arxiv_id("https://arxiv.org/abs/1706.03762") == "1706.03762"


def test_extract_arxiv_id_from_pdf_url_with_version() -> None:
    assert extract_arxiv_id("https://arxiv.org/pdf/2606.03108v3") == "2606.03108"


def test_extract_arxiv_id_from_bare_id() -> None:
    assert extract_arxiv_id("please discuss 2401.00001 today") == "2401.00001"


def test_extract_arxiv_id_none_for_plain_title() -> None:
    assert extract_arxiv_id("Attention Is All You Need") is None


@respx.mock
async def test_fetch_arxiv_metadata_parses_atom() -> None:
    respx.get(ARXIV_API_URL).mock(return_value=httpx.Response(200, text=_atom()))

    async with httpx.AsyncClient() as client:
        paper = await fetch_arxiv_metadata(client, "1706.03762")

    assert paper is not None
    assert paper.title == "Attention Is All You Need"
    assert paper.authors == ("Ashish Vaswani", "Noam Shazeer")
    assert paper.arxiv_id == "1706.03762"
    assert paper.url == "https://arxiv.org/abs/1706.03762"


@respx.mock
async def test_fetch_arxiv_metadata_empty_feed_returns_none() -> None:
    respx.get(ARXIV_API_URL).mock(return_value=httpx.Response(200, text=_EMPTY_FEED))

    async with httpx.AsyncClient() as client:
        assert await fetch_arxiv_metadata(client, "0000.00000") is None


@respx.mock
async def test_resolve_paper_by_id() -> None:
    route = respx.get(ARXIV_API_URL).mock(return_value=httpx.Response(200, text=_atom()))

    async with httpx.AsyncClient() as client:
        paper = await resolve_paper(client, "https://arxiv.org/abs/1706.03762")

    assert paper is not None
    assert paper.arxiv_id == "1706.03762"
    assert route.calls.last.request.url.params["id_list"] == "1706.03762"


@respx.mock
async def test_resolve_paper_by_title_uses_search() -> None:
    route = respx.get(ARXIV_API_URL).mock(
        return_value=httpx.Response(200, text=_atom(title="Some Title"))
    )

    async with httpx.AsyncClient() as client:
        paper = await resolve_paper(client, "Some Title")

    assert paper is not None
    assert "search_query" in route.calls.last.request.url.params


async def test_resolve_paper_empty_query_returns_none() -> None:
    async with httpx.AsyncClient() as client:
        assert await resolve_paper(client, "   ") is None
