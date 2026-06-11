"""アプリのエントリポイント兼合成ルート。

設定をロードして LLM ルーター・議論エンジン・Webhook 投稿・bot を組み立て、起動する。
"""

import asyncio
import datetime
import logging

import httpx

from thesis_ai.config import Settings, load_settings
from thesis_ai.discord_bot.bot import BotContext, ThesisBot
from thesis_ai.discord_bot.commands import register_commands
from thesis_ai.discord_bot.webhooks import PersonaWebhookPoster
from thesis_ai.discussion.engine import DiscussionEngine
from thesis_ai.discussion.store import SessionStore
from thesis_ai.llm.gemini import GeminiClient
from thesis_ai.llm.router import LLMRouter, RoutedModel, SlidingRateLimiter

logger = logging.getLogger(__name__)

# 無料枠の保守的な既定値（実値は AI Studio で確認のうえ調整）
_GEMMA_RPM, _GEMMA_RPD = 10, 1400
_FLASH_RPM, _FLASH_RPD = 10, 240

_DB_PATH = "data/sessions.sqlite3"
_DAILY_TIME = datetime.time(hour=9, minute=0)


def build_router(settings: Settings) -> LLMRouter:
    """Gemma 4（主力）→ Gemini Flash（品質補完）のフォールバックチェーンを構成する。"""
    gemma = GeminiClient(api_key=settings.gemini_api_key, model=settings.gemma_model)
    flash = GeminiClient(api_key=settings.gemini_api_key, model=settings.flash_model)
    chain = [
        RoutedModel(
            name="gemma-4",
            client=gemma,
            limiter=SlidingRateLimiter(max_per_minute=_GEMMA_RPM, max_per_day=_GEMMA_RPD),
        ),
        RoutedModel(
            name="gemini-flash",
            client=flash,
            limiter=SlidingRateLimiter(max_per_minute=_FLASH_RPM, max_per_day=_FLASH_RPD),
        ),
    ]
    return LLMRouter(chain)


def build_bot(settings: Settings, http_client: httpx.AsyncClient) -> ThesisBot:
    """設定と HTTP クライアントから bot を組み立てる。"""
    engine = DiscussionEngine(build_router(settings))
    store = SessionStore(_DB_PATH)
    poster = PersonaWebhookPoster(http_client, settings.webhook_map())
    context = BotContext(
        http_client=http_client,
        engine=engine,
        store=store,
        poster=poster,
        channel_id=settings.discord_channel_id,
        daily_time=_DAILY_TIME,
    )
    bot = ThesisBot(context)
    register_commands(bot)
    return bot


async def run() -> None:
    """設定をロードして bot を起動する（停止までブロックする）。"""
    settings = load_settings()
    missing = settings.missing_webhooks()
    if missing:
        logger.warning("未設定の Webhook があります: %s", ", ".join(missing))

    async with httpx.AsyncClient(timeout=60.0) as http_client:
        bot = build_bot(settings, http_client)
        await bot.start(settings.discord_bot_token)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
