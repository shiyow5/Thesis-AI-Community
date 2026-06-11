"""モードB: ユーザー指定の論文（URL / ID / タイトル）について議論を実行する。

`detect_paper_query` はチャンネルへの通常投稿から論文指定を検出し（自動検知）、
`run_on_demand_discussion` は解決した論文で議論ランナーを起動する。
"""

import logging

import httpx

from thesis_ai.discord_bot.runner import (
    PosterTarget,
    ThreadTarget,
    fetch_text_for,
    run_discussion,
)
from thesis_ai.discussion.engine import DiscussionEngine
from thesis_ai.discussion.session import DiscussionSession
from thesis_ai.discussion.store import SessionStore
from thesis_ai.papers.resolve import extract_arxiv_id, resolve_paper

logger = logging.getLogger(__name__)


def detect_paper_query(text: str) -> str | None:
    """通常メッセージから論文指定（arXiv URL / ID）を検出する。

    自動検知では誤反応を避けるため、明示的な arXiv URL / ID のみを対象とする。
    タイトル指定でのトリガーはスラッシュコマンド（明示操作）に限定する。
    """
    arxiv_id = extract_arxiv_id(text)
    if arxiv_id:
        return arxiv_id
    return None


async def run_on_demand_discussion(
    http_client: httpx.AsyncClient,
    query: str,
    *,
    thread_target: ThreadTarget,
    poster: PosterTarget,
    engine: DiscussionEngine,
    store: SessionStore,
) -> DiscussionSession | None:
    """URL / ID / タイトルから論文を解決し、議論を実行する。

    論文を解決できない場合は None を返す。
    """
    paper = await resolve_paper(http_client, query)
    if paper is None:
        logger.info("論文を解決できませんでした: %s", query)
        return None

    paper_text = await fetch_text_for(http_client, paper)
    logger.info("オンデマンド議論: %s (%s)", paper.title, paper.arxiv_id)
    return await run_discussion(
        paper,
        paper_text,
        thread_target=thread_target,
        poster=poster,
        engine=engine,
        store=store,
    )
