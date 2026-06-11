"""モードA: 1日1回トレンド論文を取得して議論を実行する。

`run_daily_discussion` は依存を引数で受け取り、外部非依存でテストできる。実運用では
これを discord.ext.tasks のループから定時呼び出しする（`DailyDiscussionTask`）。
"""

import datetime
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from discord.ext import tasks

from thesis_ai.discord_bot.runner import PosterTarget, ThreadTarget, run_discussion
from thesis_ai.discussion.engine import DiscussionEngine
from thesis_ai.discussion.session import DiscussionSession
from thesis_ai.discussion.store import SessionStore
from thesis_ai.papers.fetch import fetch_paper_text
from thesis_ai.papers.trending import fetch_trending_papers, pick_top_paper

logger = logging.getLogger(__name__)


async def run_daily_discussion(
    http_client: httpx.AsyncClient,
    *,
    thread_target: ThreadTarget,
    poster: PosterTarget,
    engine: DiscussionEngine,
    store: SessionStore,
    date: str | None = None,
) -> DiscussionSession | None:
    """トレンド上位の論文を1本選び、本文を取得して議論を実行する。

    取得できる論文が無い場合は None を返す。
    """
    papers = await fetch_trending_papers(http_client, date=date)
    paper = pick_top_paper(papers)
    if paper is None:
        logger.warning("トレンド論文を取得できませんでした")
        return None

    paper_text = ""
    if paper.arxiv_id:
        paper_text = await fetch_paper_text(http_client, paper.arxiv_id) or ""
    if not paper_text:
        paper_text = paper.ai_summary or paper.abstract or paper.title

    logger.info("本日の論文: %s (%s)", paper.title, paper.arxiv_id)
    return await run_discussion(
        paper,
        paper_text,
        thread_target=thread_target,
        poster=poster,
        engine=engine,
        store=store,
    )


def create_daily_task(
    run_at: datetime.time,
    job: Callable[[], Awaitable[None]],
) -> tasks.Loop[Any]:
    """指定時刻に `job()` を実行する discord.ext.tasks ループを生成する。"""

    @tasks.loop(time=run_at)
    async def _loop() -> None:
        try:
            await job()
        except Exception:
            logger.exception("日次議論ジョブが失敗しました")

    return _loop
