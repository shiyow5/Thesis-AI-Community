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


async def test_stream_round_accumulates_turns() -> None:
    router = FakeRouter()
    engine = _engine(router)

    results = [(turn, session) async for turn, session in engine.stream_round(_session())]

    assert [t.persona_key for t, _ in results] == ["professor", "layperson"]
    # 最終セッションに 2 発言蓄積
    final_session = results[-1][1]
    assert len(final_session.turns) == 2
    # 2 人目のプロンプトには 1 人目の発言が履歴として含まれる
    second_user_msg = router.calls[1][-1].content
    assert "教授: 発言1" in second_user_msg
