"""自由発話型の議論オーケストレータ。

固定順・固定回数を廃し、司会判断（select_next_speaker）で次の発言者を動的に選ぶ。
論点が出尽くせば DONE を返して終了する。各発言は特定の参加者への返信（reply_to）か、
全体への発言かを自分で示す。
"""

import logging

from thesis_ai.discussion.interrupt import (
    build_next_speaker_messages,
    build_selector_messages,
    is_done_signal,
    parse_next_speaker,
    parse_persona_key,
    parse_reply_marker,
)
from thesis_ai.discussion.session import DiscussionSession, Turn
from thesis_ai.llm.base import Message
from thesis_ai.llm.router import LLMRouter
from thesis_ai.personas import DEFAULT_PERSONAS, Persona

logger = logging.getLogger(__name__)

# 要約生成に渡す論文本文の上限。Gemma 無料枠の入力 16,000 tokens/分 に収まる範囲に抑える
_DEFAULT_MAX_PAPER_CHARS = 48_000
_DEFAULT_MAX_TURNS = 20
# 発言本文の出力上限。Gemma 4 は思考(thinking)モデルで可視出力の前に思考トークンを消費する。
# 1024 程度だと思考＋本文が収まらず本文が MAX_TOKENS で途中切断されるため余裕を持たせる。
_DEFAULT_MAX_TOKENS = 2048
_DEFAULT_INTERRUPT_MAX_TOKENS = 2048
_SUMMARY_MAX_TOKENS = 2048
# 司会選定・回答者選定の出力上限。主力 Gemma 4 は思考(thinking)モデルで、可視出力の前に
# 思考トークンを消費する。16 程度だと思考だけで使い切り可視テキストが空になり
# フォールバックを誘発するため、思考＋短い回答が収まる余裕を持たせる。
_SELECT_MAX_TOKENS = 512

_SUMMARY_SYSTEM = "あなたは論文を分かりやすく日本語で要約する専門家です。"
_SUMMARY_INSTRUCTION = (
    "この論文について、背景、目的、手法、実験方法、実験結果、考察の順に説明してください。\n\n"
    "ただしそれぞれの説明は簡潔に、具体的で、提案手法について特に詳しく、"
    "長くても1000文字で収めてください。\n\n"
    "フォーマットは以下の通りです。\n\n"
    "【背景】\n\n日本語の説明1\n日本語の説明2\n\n"
    "【目的】\n\n…\n\n【手法】\n\n…\n\n【実験方法】\n\n…\n\n【実験結果】\n\n…\n\n【考察】\n\n…"
)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[... 以下省略 ...]"


def compose_system(persona: Persona, session: DiscussionSession, *, max_paper_chars: int) -> str:
    """ペルソナ用の system プロンプトを組み立てる。

    要約があればそれを文脈に使い（全文の再送を避けてトークン消費を抑える）、無ければ
    本文を切り詰めて使う。
    """
    if session.summary:
        label, context = "# 論文の要約", session.summary
    else:
        label = "# 議論対象の論文"
        context = _truncate(session.paper_text or session.paper_title, max_paper_chars)
    return (
        f"{persona.system_prompt}\n\n"
        f"{label}\n"
        f"タイトル: {session.paper_title}\n\n"
        f"{context}\n\n"
        "# 発言ルール\n"
        "- 必ず日本語で、あなたの視点から簡潔に発言する（200〜400字程度）\n"
        "- 他の参加者の発言を踏まえ、質問・反論・補足・言い換えを行う\n"
        "- 未回答の質問が残っていれば、可能な範囲で必ず答える\n"
        "- 断定や教科書的な言い切りを避け、『〜と考えます』『〜のように思われます』"
        "『〜かもしれません』のように、自分の見解として柔らかく人間らしい口調で述べる\n"
        "- 文を途中で切らず、最後まで言い切ってから終える\n"
        "- 特定の参加者の発言に直接返信する場合は、本文の最初に @相手の名前（例: @教授）を"
        "1つだけ書く。新しい論点や全体への発言なら何も付けない\n"
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


def _latest_index(session: DiscussionSession, persona_key: str) -> int | None:
    for idx in range(len(session.turns) - 1, -1, -1):
        if session.turns[idx].persona_key == persona_key:
            return idx
    return None


class DiscussionEngine:
    """セッションに対して議論ターンを動的に生成する。"""

    def __init__(
        self,
        router: LLMRouter,
        *,
        personas: tuple[Persona, ...] = DEFAULT_PERSONAS,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        max_paper_chars: int = _DEFAULT_MAX_PAPER_CHARS,
        max_turns: int = _DEFAULT_MAX_TURNS,
        interrupt_max_tokens: int = _DEFAULT_INTERRUPT_MAX_TOKENS,
    ) -> None:
        self._router = router
        self._personas = {p.key: p for p in personas}
        self._max_tokens = max_tokens
        self._max_paper_chars = max_paper_chars
        self.max_turns = max_turns
        self._interrupt_max_tokens = interrupt_max_tokens

    @property
    def persona_keys(self) -> tuple[str, ...]:
        """登録ペルソナのキー（一覧）。"""
        return tuple(self._personas)

    def _active_personas(self, session: DiscussionSession) -> tuple[Persona, ...]:
        active = tuple(self._personas[k] for k in session.persona_keys if k in self._personas)
        return active or tuple(self._personas.values())

    def _build_messages(self, session: DiscussionSession, persona: Persona) -> list[Message]:
        system = compose_system(persona, session, max_paper_chars=self._max_paper_chars)
        messages = [Message(role="system", content=system)]
        history = format_history(session.turns, self._personas)
        if history:
            prompt = (
                "これまでの議論:\n"
                f"{history}\n\n"
                f"あなた（{persona.display_name}）として、議論を続けてください。"
            )
        else:
            prompt = (
                f"あなた（{persona.display_name}）として、"
                "この論文について最初の発言をしてください。"
            )
        messages.append(Message(role="user", content=prompt))
        return messages

    def _reply_aliases(self) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for persona in self._personas.values():
            aliases[persona.key] = persona.key
            aliases[persona.display_name] = persona.key
        return aliases

    async def generate_turn(self, session: DiscussionSession, persona_key: str) -> Turn:
        """指定ペルソナの発言を 1 つ生成する。返信マーカーがあれば reply_to を設定する。"""
        persona = self._personas[persona_key]
        raw = await self._router.generate(
            self._build_messages(session, persona),
            max_tokens=self._max_tokens,
        )
        marker_key, content = parse_reply_marker(raw, self._reply_aliases())
        reply_to = None
        if marker_key is not None and marker_key != persona_key:
            reply_to = _latest_index(session, marker_key)
        return Turn(persona_key=persona_key, content=content.strip(), reply_to=reply_to)

    async def summarize_paper(self, session: DiscussionSession) -> str:
        """議論に先立ち、論文の構造化要約（背景〜考察）を生成する。"""
        paper = _truncate(session.paper_text or session.paper_title, self._max_paper_chars)
        user = f"# 論文\nタイトル: {session.paper_title}\n\n{paper}\n\n{_SUMMARY_INSTRUCTION}"
        text = await self._router.generate(
            [
                Message(role="system", content=_SUMMARY_SYSTEM),
                Message(role="user", content=user),
            ],
            max_tokens=_SUMMARY_MAX_TOKENS,
        )
        return text.strip()

    async def select_next_speaker(self, session: DiscussionSession) -> str | None:
        """次に発言すべきペルソナのキーを選ぶ。終了すべきなら None。"""
        personas = self._active_personas(session)
        history = format_history(session.turns, self._personas)
        raw = await self._router.generate(
            build_next_speaker_messages(personas, history),
            max_tokens=_SELECT_MAX_TOKENS,
        )
        n = len(session.turns)
        keys = [p.key for p in personas]
        chosen = parse_next_speaker(raw, keys)
        spoken = {turn.persona_key for turn in session.turns}
        unspoken = [k for k in keys if k not in spoken]

        # 全ペルソナが最低 1 回発言するまでは終了させず、未発言者を優先する。
        if unspoken:
            if chosen is not None and chosen in unspoken:
                logger.info("司会選定: raw=%r -> %s (turn数=%d)", raw.strip(), chosen, n)
                return chosen
            fallback = self._round_robin(session, personas)
            logger.info(
                "司会選定(未発言者優先): raw=%r -> %s (turn数=%d)", raw.strip(), fallback, n
            )
            return fallback

        if chosen is not None:
            logger.info("司会選定: raw=%r -> %s (turn数=%d)", raw.strip(), chosen, n)
            return chosen
        if is_done_signal(raw):
            logger.info("司会選定: raw=%r -> 終了 (turn数=%d)", raw.strip(), n)
            return None
        # キーも DONE も取れない解析不能・空応答では議論を終わらせず継続する。
        fallback = self._round_robin(session, personas)
        logger.warning(
            "司会選定が解析不能 raw=%r -> ラウンドロビンで %s (turn数=%d)", raw.strip(), fallback, n
        )
        return fallback

    def _round_robin(self, session: DiscussionSession, personas: tuple[Persona, ...]) -> str:
        """最も長く発言していない（または未発言の）ペルソナのキーを返す。"""
        last_idx: dict[str, int] = {}
        for i, turn in enumerate(session.turns):
            last_idx[turn.persona_key] = i
        return min((p.key for p in personas), key=lambda k: last_idx.get(k, -1))

    async def next_turn(self, session: DiscussionSession) -> Turn | None:
        """司会判断で次の発言者を選び、その発言を生成する。終了なら None。"""
        persona_key = await self.select_next_speaker(session)
        if persona_key is None:
            return None
        return await self.generate_turn(session, persona_key)

    async def select_responder(self, session: DiscussionSession, user_message: str) -> str:
        """ユーザーの割り込み質問に最も適切に答えられるペルソナのキーを選ぶ。"""
        personas = self._active_personas(session)
        raw = await self._router.generate(
            build_selector_messages(personas, user_message),
            max_tokens=_SELECT_MAX_TOKENS,
        )
        return parse_persona_key(raw, [p.key for p in personas])

    async def answer_interrupt(self, session: DiscussionSession, user_message: str) -> Turn:
        """議論中のユーザーの割り込み質問に、最適なペルソナとして回答する。"""
        persona_key = await self.select_responder(session, user_message)
        persona = self._personas[persona_key]
        system = compose_system(persona, session, max_paper_chars=self._max_paper_chars)
        history = format_history(session.turns, self._personas)
        history_block = f"これまでの議論:\n{history}\n\n" if history else ""
        prompt = (
            f"{history_block}"
            f"参加者への質問: {user_message}\n\n"
            f"あなた（{persona.display_name}）として、この質問に日本語で答えてください。"
            "会話なのでできるだけ簡潔に。長くても300字程度に収め、途中で切らず最後まで答えきること。"
        )
        text = await self._router.generate(
            [Message(role="system", content=system), Message(role="user", content=prompt)],
            max_tokens=self._interrupt_max_tokens,
        )
        return Turn(persona_key=persona_key, content=text.strip())
