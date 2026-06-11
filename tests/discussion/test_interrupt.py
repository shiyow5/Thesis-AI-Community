"""割り込み応答（select_responder / answer_interrupt / parser）のテスト。"""

from thesis_ai.discussion.engine import DiscussionEngine
from thesis_ai.discussion.interrupt import (
    build_next_speaker_messages,
    build_selector_messages,
    parse_next_speaker,
    parse_persona_key,
    parse_reply_marker,
)
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


def test_parse_next_speaker_returns_key() -> None:
    keys = ["professor", "expert", "grad_student", "layperson"]
    assert parse_next_speaker("expert", keys) == "expert"
    assert parse_next_speaker("  Layperson です\n", keys) == "layperson"


def test_parse_next_speaker_done_or_unknown_returns_none() -> None:
    keys = ["professor", "expert"]
    assert parse_next_speaker("DONE", keys) is None
    assert parse_next_speaker("もう十分です", keys) is None


def test_build_next_speaker_messages_lists_personas() -> None:
    messages = build_next_speaker_messages(DEFAULT_PERSONAS, "教授: 導入")

    system = messages[0].content
    for persona in DEFAULT_PERSONAS:
        assert persona.key in system
    assert "次に発言すべき" in messages[1].content


_ALIASES = {"professor": "professor", "教授": "professor", "expert": "expert", "専門家": "expert"}


def test_parse_reply_marker_extracts_key() -> None:
    target, body = parse_reply_marker("@professor それは違います", _ALIASES)
    assert target == "professor"
    assert body == "それは違います"


def test_parse_reply_marker_accepts_display_name() -> None:
    target, body = parse_reply_marker("@教授\nそれは違います", _ALIASES)
    assert target == "professor"
    assert body == "それは違います"


def test_parse_reply_marker_tolerates_honorific() -> None:
    aliases = {"他分野の研究生": "grad_student", "教授": "professor"}
    target, body = parse_reply_marker("@他分野の研究生さん、鋭い質問ですね。", aliases)
    assert target == "grad_student"
    assert body == "鋭い質問ですね。"


def test_parse_reply_marker_none_when_no_marker() -> None:
    target, body = parse_reply_marker("全体への発言です", _ALIASES)
    assert target is None
    assert body == "全体への発言です"


def test_parse_reply_marker_unknown_ignored() -> None:
    target, body = parse_reply_marker("@unknown これは？", _ALIASES)
    assert target is None
    assert body == "@unknown これは？"


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
    # 回答プロンプトに質問・既存履歴・文字数指示が含まれる
    answer_prompt = router.calls[1][-1].content
    assert "再現性は？" in answer_prompt
    assert "導入の説明" in answer_prompt
    assert "字程度" in answer_prompt  # 切れ防止の長さ指示
