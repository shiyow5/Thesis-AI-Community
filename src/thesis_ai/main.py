"""アプリのエントリポイント。設定をロードして Discord bot を起動する。"""

import asyncio
import logging

from thesis_ai.config import load_settings
from thesis_ai.discord_bot.bot import ThesisBot

logger = logging.getLogger(__name__)


async def run() -> None:
    """設定をロードして bot を起動する（停止までブロックする）。"""
    settings = load_settings()
    missing = settings.missing_webhooks()
    if missing:
        logger.warning("未設定の Webhook があります: %s", ", ".join(missing))

    bot = ThesisBot()
    await bot.start(settings.discord_bot_token)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
