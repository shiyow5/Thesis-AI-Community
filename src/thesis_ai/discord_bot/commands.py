"""スラッシュコマンド `/discuss`（モードB 経路2）。

3 秒以内に ephemeral な ACK を返し（Interaction の期限を満たす）、議論本体は Webhook で
スレッドに投稿する（15 分の follow-up 制限を回避）。タイトル指定もここで受け付ける。
"""

import logging

import discord
from discord import app_commands

from thesis_ai.discord_bot.bot import ThesisBot
from thesis_ai.discord_bot.ondemand import run_on_demand_discussion
from thesis_ai.discord_bot.runner import ThreadTarget
from thesis_ai.discord_bot.targets import DiscordThreadTarget

logger = logging.getLogger(__name__)


def register_commands(bot: ThesisBot) -> None:
    """bot のコマンドツリーに `/discuss` を登録する。"""

    @bot.tree.command(
        name="discuss",
        description="指定した論文(URL/ID/タイトル)について4人のAIが議論します",
    )
    @app_commands.describe(paper="arXiv の URL / ID、または論文タイトル")
    async def discuss(interaction: discord.Interaction, paper: str) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "テキストチャンネルで実行してください。", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"「{paper}」の議論を開始します。スレッドをご覧ください。", ephemeral=True
        )
        target = DiscordThreadTarget(interaction.channel)
        bot.loop.create_task(_run(bot, target, paper))


async def _run(bot: ThesisBot, target: ThreadTarget, query: str) -> None:
    try:
        result = await run_on_demand_discussion(
            bot.context.http_client,
            query,
            thread_target=target,
            poster=bot.context.poster,
            engine=bot.context.engine,
            store=bot.context.store,
        )
        if result is None:
            logger.info("論文を解決できませんでした: %s", query)
    except Exception:
        logger.exception("/discuss の実行に失敗しました: %s", query)
