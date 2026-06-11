"""Discord Gateway 受信 bot。

メッセージ / コマンドの受信を担当する（ペルソナ発言の投稿は Webhook 側）。
URL 検知（モードB）や割り込み応答（Phase 7）は後続フェーズでハンドラを拡張する。
"""

import logging

import discord

logger = logging.getLogger(__name__)


def make_intents() -> discord.Intents:
    """必要最小限の Gateway Intents を構成する。

    メッセージ本文の取得には MESSAGE CONTENT INTENT（Developer Portal で要有効化）が必要。
    """
    intents = discord.Intents.default()
    intents.message_content = True
    return intents


class ThesisBot(discord.Client):
    """論文議論コミュニティの受信 bot。"""

    def __init__(self, *, intents: discord.Intents | None = None) -> None:
        super().__init__(intents=intents or make_intents())

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (id=%s)", self.user, getattr(self.user, "id", "?"))

    async def on_message(self, message: discord.Message) -> None:
        # 自分・他 bot・Webhook 由来の投稿には反応しない（ループ防止）
        if message.author.bot or message.webhook_id is not None:
            return
        # モードB（URL 検知）と割り込み応答は Phase 6 / 7 で実装する。
