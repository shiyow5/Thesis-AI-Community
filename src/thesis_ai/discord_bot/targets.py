"""ThreadTarget の Discord 実装。

導入メッセージをチャンネルに投稿し、それを起点にスレッドを作成する。
（discord.py 依存のグルー層。ユニットテストではなく手動 E2E で検証する。）
"""

import discord

from thesis_ai.discord_bot.runner import ThreadTarget


class DiscordThreadTarget(ThreadTarget):
    """指定チャンネルに導入文を投稿し、スレッドを開く。"""

    def __init__(self, channel: discord.TextChannel) -> None:
        self._channel = channel

    async def open_thread(self, *, name: str, intro: str) -> str:
        message = await self._channel.send(intro)
        thread = await message.create_thread(name=name)
        return str(thread.id)
