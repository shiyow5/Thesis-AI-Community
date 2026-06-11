"""DiscussionEngine のテスト（FakeRouter 注入で LLM 非依存）。"""

from thesis_ai.discussion.engine import (
    DiscussionEngine,
    compose_system,
    format_history,
)
from thesis_ai.discussion.session import DiscussionSession, Turn
from thesis_ai.llm.base import Message
from thesis_ai.personas import DEFAULT_PERSONAS, PROFESSOR


class FakeRouter:
    """generate 呼び出しを記録し、定型応答を返すルーター代用。"""

    def __init__(self) -> None:
        self.calls: list[list[Message]] = []
        self._counter = 0

    async def generate(self, messages: list[Message], *, max_tokens: int) -> str:
        self.calls.append(messages)
        self._counter += 1
        return f"  発言{self._counter}  "  # 前後空白は strip される想定


def _session() -> DiscussionSession:
    return DiscussionSession(
        session_id="t1",
        paper_title="Sample Paper",
        paper_text="paper body text",
        persona_keys=("professor", "layperson"),
    )


def _engine(router: FakeRouter) -> DiscussionEngine:
    return DiscussionEngine(router)  # type: ignore[arg-type]  # FakeRouter は構造的に互換


def test_compose_system_includes_persona_and_paper() -> None:
    system = compose_system(PROFESSOR, _session(), max_paper_chars=1000)

    assert PROFESSOR.system_prompt in system
    assert "Sample Paper" in system
    assert "paper body text" in system


def test_compose_system_truncates_long_paper() -> None:
    session = DiscussionSession(
        session_id="t1",
        paper_title="T",
        paper_text="x" * 500,
        persona_keys=("professor",),
    )

    system = compose_system(PROFESSOR, session, max_paper_chars=100)

    assert "以下省略" in system


def test_format_history_uses_display_names() -> None:
    personas = {p.key: p for p in DEFAULT_PERSONAS}
    turns = (
        Turn(persona_key="professor", content="A"),
        Turn(persona_key="layperson", content="B"),
    )

    text = format_history(turns, personas)

    assert text == "教授: A\n一般の人: B"


async def test_generate_turn_strips_and_tags_persona() -> None:
    router = FakeRouter()
    engine = _engine(router)

    turn = await engine.generate_turn(_session(), "professor")

    assert turn.persona_key == "professor"
    assert turn.content == "発言1"  # strip 済み


async def test_first_turn_prompt_has_no_history() -> None:
    router = FakeRouter()
    engine = _engine(router)

    await engine.generate_turn(_session(), "professor")

    user_msg = router.calls[0][-1].content
    assert "最初の発言" in user_msg


class ScriptedRouter:
    """select_next 用と generate 用で出し分けるルーター代用。"""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls: list[list[Message]] = []

    async def generate(self, messages: list[Message], *, max_tokens: int) -> str:
        self.calls.append(messages)
        return self._replies.pop(0)


async def test_select_next_speaker_returns_key() -> None:
    engine = DiscussionEngine(ScriptedRouter(["layperson"]))  # type: ignore[arg-type]
    assert await engine.select_next_speaker(_session()) == "layperson"


async def test_select_next_speaker_done_returns_none() -> None:
    engine = DiscussionEngine(ScriptedRouter(["DONE"]))  # type: ignore[arg-type]
    assert await engine.select_next_speaker(_session()) is None


async def test_next_turn_selects_then_generates() -> None:
    # 1 回目=司会の選択(expert), 2 回目=発言本文
    router = ScriptedRouter(["expert", "専門家の発言"])
    engine = DiscussionEngine(router)  # type: ignore[arg-type]

    session = DiscussionSession(
        session_id="t1",
        paper_title="P",
        paper_text="body",
        persona_keys=("professor", "expert", "grad_student", "layperson"),
    )
    turn = await engine.next_turn(session)

    assert turn is not None
    assert turn.persona_key == "expert"
    assert turn.content == "専門家の発言"


async def test_next_turn_returns_none_when_done() -> None:
    engine = DiscussionEngine(ScriptedRouter(["DONE"]))  # type: ignore[arg-type]
    assert await engine.next_turn(_session()) is None


async def test_generate_turn_parses_reply_marker() -> None:
    router = ScriptedRouter(["@professor なるほど、その点に補足します。"])
    engine = DiscussionEngine(router)  # type: ignore[arg-type]

    session = DiscussionSession(
        session_id="t1",
        paper_title="P",
        paper_text="body",
        persona_keys=("professor", "expert"),
        turns=(Turn(persona_key="professor", content="導入"),),
    )
    turn = await engine.generate_turn(session, "expert")

    assert turn.reply_to == 0  # professor の発言（index 0）への返信
    assert turn.content == "なるほど、その点に補足します。"  # マーカー除去済み


async def test_generate_turn_ignores_self_reply_marker() -> None:
    router = ScriptedRouter(["@expert 自分への返信は無視される"])
    engine = DiscussionEngine(router)  # type: ignore[arg-type]

    session = DiscussionSession(
        session_id="t1",
        paper_title="P",
        paper_text="body",
        persona_keys=("professor", "expert"),
        turns=(Turn(persona_key="expert", content="前の発言"),),
    )
    turn = await engine.generate_turn(session, "expert")

    assert turn.reply_to is None
