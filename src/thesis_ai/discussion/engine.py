"""ターン制で議論を生成するオーケストレータ。

各ペルソナの発言を LLMRouter 経由で 1 つずつ生成する。同一ラウンド内では後続ペルソナが
先行発言を踏まえられるよう、セッションを逐次更新しながらストリーム生成する。
"""

from collections.abc import AsyncIterator

from thesis_ai.discussion.session import DiscussionSession, Turn, add_turn
from thesis_ai.llm.base import Message
from thesis_ai.llm.router import LLMRouter
from thesis_ai.personas import DEFAULT_PERSONAS, Persona

_DEFAULT_MAX_PAPER_CHARS = 200_000


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[... 以下省略 ...]"


def compose_system(persona: Persona, session: DiscussionSession, *, max_paper_chars: int) -> str:
    """ペルソナ用の system プロンプトを組み立てる。"""
    paper = _truncate(session.paper_text or session.paper_title, max_paper_chars)
    return (
        f"{persona.system_prompt}\n\n"
        "# 議論対象の論文\n"
        f"タイトル: {session.paper_title}\n\n"
        f"{paper}\n\n"
        "# 発言ルール\n"
        "- 必ず日本語で、あなたの視点から簡潔に発言する（200〜400字程度）\n"
        "- 他の参加者の発言があれば踏まえ、質問・反論・補足・言い換えを行う\n"
        "- 名前や見出しを付けず、発言内容のみを書く"
    )


def format_history(turns: tuple[Turn, ...], personas: dict[str, Persona]) -> str:
    """これまでの発言を読みやすいテキストに整形する。"""
    lines = []
    for turn in turns:
        persona = personas.get(turn.persona_key)
        name = persona.display_name if persona else turn.persona_key
        lines.append(f"{name}: {turn.content}")
    return "\n".join(lines)


class DiscussionEngine:
    """セッションに対して議論ターンを生成する。"""

    def __init__(
        self,
        router: LLMRouter,
        *,
        personas: tuple[Persona, ...] = DEFAULT_PERSONAS,
        max_tokens: int = 1024,
        max_paper_chars: int = _DEFAULT_MAX_PAPER_CHARS,
    ) -> None:
        self._router = router
        self._personas = {p.key: p for p in personas}
        self._max_tokens = max_tokens
        self._max_paper_chars = max_paper_chars

    def _build_messages(self, session: DiscussionSession, persona: Persona) -> list[Message]:
        system = compose_system(persona, session, max_paper_chars=self._max_paper_chars)
        messages = [Message(role="system", content=system)]
        history = format_history(session.turns, self._personas)
        if history:
            prompt = (
                "これまでの議論:\n"
                f"{history}\n\n"
                f"上記を踏まえ、あなた（{persona.display_name}）として議論を続けてください。"
            )
        else:
            prompt = (
                f"あなた（{persona.display_name}）として、"
                "この論文について最初の発言をしてください。"
            )
        messages.append(Message(role="user", content=prompt))
        return messages

    async def generate_turn(self, session: DiscussionSession, persona_key: str) -> Turn:
        """指定ペルソナの発言を 1 つ生成する。"""
        persona = self._personas[persona_key]
        text = await self._router.generate(
            self._build_messages(session, persona),
            max_tokens=self._max_tokens,
        )
        return Turn(persona_key=persona_key, content=text.strip())

    async def stream_round(
        self, session: DiscussionSession
    ) -> AsyncIterator[tuple[Turn, DiscussionSession]]:
        """全ペルソナが 1 巡発言する。各発言ごとに (発言, 更新後セッション) を yield する。"""
        current = session
        for persona_key in current.persona_keys:
            turn = await self.generate_turn(current, persona_key)
            current = add_turn(current, turn)
            yield turn, current
