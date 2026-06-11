"""論文の取得・本文抽出・解決を担うレイヤ。"""

from thesis_ai.papers.fetch import fetch_paper_text
from thesis_ai.papers.models import Paper
from thesis_ai.papers.resolve import extract_arxiv_id, resolve_paper
from thesis_ai.papers.trending import fetch_trending_papers, pick_top_paper

__all__ = [
    "Paper",
    "extract_arxiv_id",
    "fetch_paper_text",
    "fetch_trending_papers",
    "pick_top_paper",
    "resolve_paper",
]
