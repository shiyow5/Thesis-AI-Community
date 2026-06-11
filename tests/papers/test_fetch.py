"""fetch モジュール（本文取得・多段フォールバック）のテスト。"""

import httpx
import pymupdf
import respx

from thesis_ai.papers.fetch import fetch_paper_text

ARXIV_ID = "1706.03762"


def _make_pdf(text: str = "PDF body text") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data: bytes = doc.tobytes()
    doc.close()
    return data


@respx.mock
async def test_prefers_arxiv_txt_pdf() -> None:
    respx.get(f"https://arxiv-txt.org/pdf/{ARXIV_ID}").mock(
        return_value=httpx.Response(200, text="full text from arxiv-txt")
    )

    async with httpx.AsyncClient() as client:
        text = await fetch_paper_text(client, ARXIV_ID)

    assert text == "full text from arxiv-txt"


@respx.mock
async def test_falls_back_to_abs_when_pdf_missing() -> None:
    respx.get(f"https://arxiv-txt.org/pdf/{ARXIV_ID}").mock(return_value=httpx.Response(404))
    respx.get(f"https://arxiv-txt.org/abs/{ARXIV_ID}").mock(
        return_value=httpx.Response(200, text="abstract level text")
    )

    async with httpx.AsyncClient() as client:
        text = await fetch_paper_text(client, ARXIV_ID)

    assert text == "abstract level text"


@respx.mock
async def test_falls_back_to_pdf_extraction() -> None:
    respx.get(f"https://arxiv-txt.org/pdf/{ARXIV_ID}").mock(return_value=httpx.Response(404))
    respx.get(f"https://arxiv-txt.org/abs/{ARXIV_ID}").mock(return_value=httpx.Response(404))
    respx.get(f"https://arxiv.org/pdf/{ARXIV_ID}").mock(
        return_value=httpx.Response(200, content=_make_pdf("extracted body"))
    )

    async with httpx.AsyncClient() as client:
        text = await fetch_paper_text(client, ARXIV_ID)

    assert text is not None
    assert "extracted body" in text


@respx.mock
async def test_returns_none_when_all_sources_fail() -> None:
    respx.get(f"https://arxiv-txt.org/pdf/{ARXIV_ID}").mock(return_value=httpx.Response(404))
    respx.get(f"https://arxiv-txt.org/abs/{ARXIV_ID}").mock(return_value=httpx.Response(404))
    respx.get(f"https://arxiv.org/pdf/{ARXIV_ID}").mock(return_value=httpx.Response(404))

    async with httpx.AsyncClient() as client:
        assert await fetch_paper_text(client, ARXIV_ID) is None


@respx.mock
async def test_empty_text_is_treated_as_failure() -> None:
    respx.get(f"https://arxiv-txt.org/pdf/{ARXIV_ID}").mock(
        return_value=httpx.Response(200, text="   ")
    )
    respx.get(f"https://arxiv-txt.org/abs/{ARXIV_ID}").mock(
        return_value=httpx.Response(200, text="real content")
    )

    async with httpx.AsyncClient() as client:
        text = await fetch_paper_text(client, ARXIV_ID)

    assert text == "real content"
