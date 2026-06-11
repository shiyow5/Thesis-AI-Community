"""DiscussionSession の不変更新関数のテスト。"""

import dataclasses

import pytest

from thesis_ai.discussion.session import (
    STATUS_DONE,
    DiscussionSession,
    Turn,
    add_turn,
    set_status,
)


def _session() -> DiscussionSession:
    return DiscussionSession(
        session_id="t1",
        paper_title="Title",
        paper_text="body",
        persona_keys=("professor", "layperson"),
    )


def test_add_turn_returns_new_session_without_mutation() -> None:
    original = _session()

    updated = add_turn(original, Turn(persona_key="professor", content="hello"))

    assert original.turns == ()
    assert updated.turns == (Turn(persona_key="professor", content="hello"),)
    assert updated is not original


def test_set_status_returns_new_session() -> None:
    original = _session()

    updated = set_status(original, STATUS_DONE)

    assert original.status == "active"
    assert updated.status == STATUS_DONE


def test_session_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _session().status = "x"  # type: ignore[misc]
