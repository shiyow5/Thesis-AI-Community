"""Hugging Face Daily Papers からトレンド論文を取得する。

非公式 API（``https://huggingface.co/api/daily_papers``）を利用する。スキーマ変更に
備え、欠損キーに耐性を持たせる。各エントリは ``paper`` キーの下にメタデータを持つ。
"""

from typing import Any

import httpx

from thesis_ai.papers.http import default_headers
from thesis_ai.papers.models import Paper

HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"


def _parse_hf_entry(entry: dict[str, Any]) -> Paper | None:
    """HF Daily Papers の 1 エントリを ``Paper`` に変換する。タイトル欠如時は None。"""
    paper = entry.get("paper") or {}
    title = paper.get("title") or entry.get("title")
    if not title:
        return None

    arxiv_id = paper.get("id")
    authors = tuple(a.get("name", "") for a in paper.get("authors", []) if a.get("name"))
    abstract = paper.get("summary") or entry.get("summary") or ""
    ai_keywords = tuple(paper.get("ai_keywords") or ())
    url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else (paper.get("url") or "")

    return Paper(
        title=title,
        authors=authors,
        abstract=abstract,
        url=url,
        arxiv_id=arxiv_id,
        ai_summary=paper.get("ai_summary"),
        ai_keywords=ai_keywords,
        upvotes=paper.get("upvotes"),
    )


async def fetch_trending_papers(
    client: httpx.AsyncClient,
    *,
    limit: int = 50,
    date: str | None = None,
) -> list[Paper]:
    """当日（または指定日）のトレンド論文一覧を取得する。

    Args:
        client: 利用する httpx クライアント。
        limit: 取得件数。
        date: ``YYYY-MM-DD`` 形式の対象日。None なら最新。
    """
    params: dict[str, str | int] = {"limit": limit}
    if date:
        params["date"] = date

    resp = await client.get(HF_DAILY_PAPERS_URL, params=params, headers=default_headers())
    resp.raise_for_status()

    data = resp.json()
    if not isinstance(data, list):
        return []
    return [paper for entry in data if (paper := _parse_hf_entry(entry)) is not None]


def pick_top_paper(papers: list[Paper]) -> Paper | None:
    """upvote 数が最大の論文を返す。空なら None。"""
    if not papers:
        return None
    return max(papers, key=lambda p: p.upvotes or 0)
