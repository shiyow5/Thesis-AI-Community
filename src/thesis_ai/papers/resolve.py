"""ユーザー入力（URL / arXiv ID / タイトル）から論文メタデータを解決する。

arXiv の公式 API（Atom XML）を利用する。XML は信頼できる arXiv エンドポイント
由来のみをパースする。
"""

import re
import xml.etree.ElementTree as ET

import httpx

from thesis_ai.papers.http import default_headers
from thesis_ai.papers.models import Paper

ARXIV_API_URL = "https://export.arxiv.org/api/query"
_ATOM = "{http://www.w3.org/2005/Atom}"

_ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)
_ARXIV_BARE_RE = re.compile(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b")


def extract_arxiv_id(text: str) -> str | None:
    """URL またはテキストから arXiv ID（バージョン無し）を抽出する。無ければ None。"""
    match = _ARXIV_URL_RE.search(text)
    if match:
        return match.group(1)
    match = _ARXIV_BARE_RE.search(text)
    if match:
        return match.group(1)
    return None


def _parse_atom(xml_text: str) -> Paper | None:
    """arXiv API の Atom レスポンスから先頭 entry を ``Paper`` に変換する。"""
    root = ET.fromstring(xml_text)  # 信頼できる arXiv API レスポンスのみをパース
    entry = root.find(f"{_ATOM}entry")
    if entry is None:
        return None

    title = (entry.findtext(f"{_ATOM}title") or "").strip()
    if not title:
        return None
    summary = (entry.findtext(f"{_ATOM}summary") or "").strip()
    authors = tuple(
        name
        for author in entry.findall(f"{_ATOM}author")
        if (name := (author.findtext(f"{_ATOM}name") or "").strip())
    )
    id_url = (entry.findtext(f"{_ATOM}id") or "").strip()
    arxiv_id = extract_arxiv_id(id_url)
    url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else id_url

    return Paper(
        title=title,
        authors=authors,
        abstract=summary,
        url=url,
        arxiv_id=arxiv_id,
    )


async def fetch_arxiv_metadata(client: httpx.AsyncClient, arxiv_id: str) -> Paper | None:
    """arXiv ID からメタデータを取得する。"""
    resp = await client.get(
        ARXIV_API_URL,
        params={"id_list": arxiv_id, "max_results": 1},
        headers=default_headers(),
    )
    resp.raise_for_status()
    return _parse_atom(resp.text)


async def search_arxiv_by_title(client: httpx.AsyncClient, title: str) -> Paper | None:
    """タイトル文字列で arXiv を検索し、最も一致する 1 件を返す。"""
    resp = await client.get(
        ARXIV_API_URL,
        params={"search_query": f'ti:"{title}"', "max_results": 1},
        headers=default_headers(),
    )
    resp.raise_for_status()
    return _parse_atom(resp.text)


async def resolve_paper(client: httpx.AsyncClient, query: str) -> Paper | None:
    """URL / arXiv ID / タイトルのいずれかから論文を解決する。

    arXiv ID を抽出できれば ID 解決、できなければタイトル検索にフォールバックする。
    """
    arxiv_id = extract_arxiv_id(query)
    if arxiv_id:
        return await fetch_arxiv_metadata(client, arxiv_id)
    cleaned = query.strip()
    if not cleaned:
        return None
    return await search_arxiv_by_title(client, cleaned)
