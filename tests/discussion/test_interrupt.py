"""割り込み応答（select_responder / answer_interrupt / parser）のテスト。"""

from thesis_ai.discussion.engine import DiscussionEngine
from thesis_ai.discussion.interrupt import build_selector_messages, parse_persona_key
from thesis_ai.discussion.session import DiscussionSession, Turn
from thesis_ai.llm.base import Message
from thesis_ai.personas import DEFAULT_PERSONAS


class ScriptedRouter:
    """generate の戻り値を順に返すルーター代用。"""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls: list[list[Message]] = []

    async def generate(self, messages: list[Message], *, max_tokens: int) -> str:
        self.calls.append(messages)
        return self._replies.pop(0)


def _session() -> DiscussionSession:
    return DiscussionSession(
        session_id="t1",
        paper_title="Paper",
        paper_text="body",
        persona_keys=("professor", "expert", "grad_student", "layperson"),
        turns=(Turn(persona_key="professor", content="導入の説明"),),
    )


def test_parse_persona_key_matches() -> None:
    keys = ["professor", "expert", "grad_student", "layperson"]
    assert parse_persona_key("expert", keys) == "expert"
    assert parse_persona_key("  Professor \n", keys) == "professor"


def test_parse_persona_key_falls_back_to_first() -> None:
    keys = ["professor", "expert"]
    assert parse_persona_key("わかりません", keys) == "professor"


def test_build_selector_messages_lists_all_personas() -> None:
    messages = build_selector_messages(DEFAULT_PERSONAS, "これは何の役に立つの？")

    system = messages[0].content
    for persona in DEFAULT_PERSONAS:
        assert persona.key in system
    assert "これは何の役に立つの？" in messages[1].content


async def test_select_responder_returns_parsed_key() -> None:
    engine = DiscussionEngine(ScriptedRouter(["layperson"]))  # type: ignore[arg-type]

    key = await engine.select_responder(_session(), "簡単に言うと？")

    assert key == "layperson"


async def test_select_responder_falls_back_on_junk() -> None:
    engine = DiscussionEngine(ScriptedRouter(["???"]))  # type: ignore[arg-type]

    key = await engine.select_responder(_session(), "?")

    assert key == "professor"  # persona_keys 先頭


async def test_answer_interrupt_uses_selected_persona_and_context() -> None:
    # 1 回目=選定(expert), 2 回目=回答本文
    router = ScriptedRouter(["expert", "  専門家の回答  "])
    engine = DiscussionEngine(router)  # type: ignore[arg-type]

    turn = await engine.answer_interrupt(_session(), "再現性は？")

    assert turn.persona_key == "expert"
    assert turn.content == "専門家の回答"
    # 回答プロンプトに質問と既存の議論履歴が含まれる
    answer_prompt = router.calls[1][-1].content
    assert "再現性は？" in answer_prompt
    assert "導入の説明" in answer_prompt
