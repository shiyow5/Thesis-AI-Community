"""議論の実行オーケストレーション（モードA / モードB 共通）。

論文を受け取り、スレッドを開き、ペルソナの発言を順次生成・投稿し、セッションを永続化する。
Discord 依存（スレッド作成）は ``ThreadTarget`` プロトコルで抽象化し、テスト可能にする。
"""

from typing import Protocol

from thesis_ai.discussion.engine import DiscussionEngine
from thesis_ai.discussion.session import (
    STATUS_IDLE,
    DiscussionSession,
    set_status,
)
from thesis_ai.discussion.store import SessionStore
from thesis_ai.papers.models import Paper
from thesis_ai.personas import Persona, get_persona

_THREAD_NAME_LIMIT = 100


class ThreadTarget(Protocol):
    """論文用スレッドを開いて ID を返すターゲット（実体は Discord チャンネル）。"""

    async def open_thread(self, *, name: str, intro: str) -> str: ...


class PosterTarget(Protocol):
    """ペルソナ発言の投稿先（実体は PersonaWebhookPoster）。"""

    async def post(
        self, persona: Persona, content: str, *, thread_id: str | None = ...
    ) -> None: ...


def build_intro(paper: Paper) -> str:
    """スレッド冒頭に投稿する論文紹介文を作る。"""
    authors = "、".join(paper.authors[:5])
    if len(paper.authors) > 5:
        authors += " ほか"
    summary = paper.ai_summary or paper.abstract
    lines = [f"**📄 {paper.title}**"]
    if authors:
        lines.append(f"_{authors}_")
    if summary:
        lines.append(f"\n{summary}")
    if paper.url:
        lines.append(f"\n🔗 {paper.url}")
    lines.append("\n4人のAIが議論します。気になったら気軽に割り込んで質問してください。")
    return "\n".join(lines)


async def run_discussion(
    paper: Paper,
    paper_text: str,
    *,
    thread_target: ThreadTarget,
    poster: PosterTarget,
    engine: DiscussionEngine,
    store: SessionStore,
    rounds: int = 1,
) -> DiscussionSession:
    """論文に対する議論を最初から最後まで実行する。

    スレッドを開き、各ペルソナの発言を生成しながら逐次投稿・永続化する。
    """
    thread_id = await thread_target.open_thread(
        name=paper.title[:_THREAD_NAME_LIMIT],
        intro=build_intro(paper),
    )

    session = DiscussionSession(
        session_id=thread_id,
        paper_title=paper.title,
        paper_text=paper_text,
        persona_keys=engine.persona_keys,
    )
    store.save(session)

    for _ in range(rounds):
        async for turn, updated in engine.stream_round(session):
            persona = get_persona(turn.persona_key)
            if persona is not None:
                await poster.post(persona, turn.content, thread_id=thread_id)
            session = updated
            store.save(session)

    session = set_status(session, STATUS_IDLE)
    store.save(session)
    return session
