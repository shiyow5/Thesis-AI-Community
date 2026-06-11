"""Discord Gateway 受信 bot とその実行コンテキスト。

通常投稿に含まれる arXiv URL/ID を検知してオンデマンド議論を起動する（モードB 経路1）。
また、設定があれば日次のトレンド論文議論（モードA）を on_ready で開始する。
割り込み応答（Phase 7）も on_message を起点に拡張する。
"""

import asyncio
import datetime
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord
import httpx

from thesis_ai.discord_bot.ondemand import detect_paper_query, run_on_demand_discussion
from thesis_ai.discord_bot.runner import ThreadTarget
from thesis_ai.discord_bot.scheduler import create_daily_task, run_daily_discussion
from thesis_ai.discord_bot.targets import DiscordThreadTarget
from thesis_ai.discord_bot.webhooks import PersonaWebhookPoster
from thesis_ai.discussion.engine import DiscussionEngine
from thesis_ai.discussion.session import add_turn
from thesis_ai.discussion.store import SessionStore
from thesis_ai.personas import get_persona

logger = logging.getLogger(__name__)


@dataclass
class BotContext:
    """bot が議論を実行するための依存一式。"""

    http_client: httpx.AsyncClient
    engine: DiscussionEngine
    store: SessionStore
    poster: PersonaWebhookPoster
    channel_id: int | None = None
    daily_time: datetime.time | None = None


def make_intents() -> discord.Intents:
    """必要最小限の Gateway Intents を構成する。

    メッセージ本文の取得には MESSAGE CONTENT INTENT（Developer Portal で要有効化）が必要。
    """
    intents = discord.Intents.default()
    intents.message_content = True
    return intents


class ThesisBot(discord.Client):
    """論文議論コミュニティの受信 bot。"""

    def __init__(self, context: BotContext, *, intents: discord.Intents | None = None) -> None:
        super().__init__(intents=intents or make_intents())
        self.context = context
        self.tree = discord.app_commands.CommandTree(self)
        self._daily_started = False
        self._interrupt_locks: dict[str, asyncio.Lock] = {}

    async def setup_hook(self) -> None:
        await self.tree.sync()

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (id=%s)", self.user, getattr(self.user, "id", "?"))
        self._maybe_start_daily()

    def _maybe_start_daily(self) -> None:
        if self._daily_started:
            return
        ctx = self.context
        if ctx.channel_id is None or ctx.daily_time is None:
            return
        channel = self.get_channel(ctx.channel_id)
        if not isinstance(channel, discord.TextChannel):
            logger.warning("日次議論用チャンネルが見つかりません: %s", ctx.channel_id)
            return
        task = create_daily_task(ctx.daily_time, self._make_daily_job(channel))
        task.start()
        self._daily_started = True
        logger.info("日次議論を %s に予約しました", ctx.daily_time)

    def _make_daily_job(self, channel: discord.TextChannel) -> Callable[[], Awaitable[None]]:
        async def _job() -> None:
            target = DiscordThreadTarget(channel)
            await run_daily_discussion(
                self.context.http_client,
                thread_target=target,
                poster=self.context.poster,
                engine=self.context.engine,
                store=self.context.store,
            )

        return _job

    async def on_message(self, message: discord.Message) -> None:
        # 自分・他 bot・Webhook 由来の投稿には反応しない（ループ防止）
        if message.author.bot or message.webhook_id is not None:
            return

        # 議論スレッド内のユーザー発言 → 割り込み応答（モードの途中でも答える）
        if isinstance(message.channel, discord.Thread):
            session = self.context.store.load(str(message.channel.id))
            if session is not None and message.content.strip():
                self.loop.create_task(
                    self._handle_interrupt(str(message.channel.id), message.content.strip())
                )
            return

        # 通常チャンネルへの arXiv URL/ID 投稿 → オンデマンド議論を開始
        if not isinstance(message.channel, discord.TextChannel):
            return
        query = detect_paper_query(message.content)
        if query is None:
            return
        target = DiscordThreadTarget(message.channel)
        self.loop.create_task(self._start_discussion(target, query))

    async def _handle_interrupt(self, thread_id: str, text: str) -> None:
        # 同一スレッドへの割り込みは直列化し、応答が交錯しないようにする
        lock = self._interrupt_locks.setdefault(thread_id, asyncio.Lock())
        async with lock:
            session = self.context.store.load(thread_id)
            if session is None:
                return
            try:
                turn = await self.context.engine.answer_interrupt(session, text)
            except Exception:
                logger.exception("割り込み応答の生成に失敗しました (thread=%s)", thread_id)
                return
            session = add_turn(session, turn)
            self.context.store.save(session)
            persona = get_persona(turn.persona_key)
            if persona is not None:
                snippet = " ".join(text.split())[:80]
                content = f"> **質問**: {snippet}…\n\n{turn.content}"
                await self.context.poster.post(persona, content, thread_id=thread_id)

    async def _start_discussion(self, target: ThreadTarget, query: str) -> None:
        try:
            await run_on_demand_discussion(
                self.context.http_client,
                query,
                thread_target=target,
                poster=self.context.poster,
                engine=self.context.engine,
                store=self.context.store,
            )
        except Exception:
            logger.exception("オンデマンド議論に失敗しました: %s", query)
