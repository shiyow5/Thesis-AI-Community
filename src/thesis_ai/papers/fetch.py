"""arXiv 論文の本文テキストを取得する。

多段フォールバック:
1. arxiv-txt.org ``/pdf/{id}``（全文・LLM 最適化済みプレーンテキスト）
2. arxiv-txt.org ``/abs/{id}``（要約レベル）
3. arXiv の PDF を直接取得し PyMuPDF で抽出

いずれも失敗した場合は None を返す（呼び出し側でハンドリングする）。
"""

import asyncio

import httpx
import pymupdf

from thesis_ai.papers.http import default_headers

ARXIV_TXT_BASE = "https://arxiv-txt.org"
ARXIV_PDF_BASE = "https://arxiv.org/pdf"


async def _try_arxiv_txt(client: httpx.AsyncClient, arxiv_id: str, path: str) -> str | None:
    """arxiv-txt.org の指定パスからテキストを取得する。失敗時は None。"""
    url = f"{ARXIV_TXT_BASE}/{path}/{arxiv_id}"
    try:
        resp = await client.get(url, headers=default_headers(), follow_redirects=True)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    text = resp.text.strip()
    return text or None


def _extract_pdf_text(data: bytes) -> str:
    """PDF バイト列からテキストを抽出する（同期・CPU バウンド）。"""
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


async def _try_pdf(client: httpx.AsyncClient, arxiv_id: str) -> str | None:
    """arXiv の PDF を取得し PyMuPDF で抽出する。失敗時は None。"""
    url = f"{ARXIV_PDF_BASE}/{arxiv_id}"
    try:
        resp = await client.get(url, headers=default_headers(), follow_redirects=True)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200 or not resp.content:
        return None
    text = (await asyncio.to_thread(_extract_pdf_text, resp.content)).strip()
    return text or None


async def fetch_paper_text(
    client: httpx.AsyncClient,
    arxiv_id: str,
    *,
    full: bool = True,
) -> str | None:
    """論文本文を多段フォールバックで取得する。

    Args:
        client: 利用する httpx クライアント。
        arxiv_id: arXiv ID（バージョン無し）。
        full: True なら全文を優先、False なら要約レベルを取得。
    """
    paths = ["pdf", "abs"] if full else ["abs"]
    for path in paths:
        text = await _try_arxiv_txt(client, arxiv_id, path)
        if text:
            return text
    return await _try_pdf(client, arxiv_id)
