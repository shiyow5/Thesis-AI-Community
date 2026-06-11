"""bot モジュールのテスト（Gateway へは接続しない）。"""

from thesis_ai.discord_bot.bot import make_intents


def test_make_intents_enables_message_content() -> None:
    intents = make_intents()

    assert intents.message_content is True
