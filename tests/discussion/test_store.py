"""SessionStore（SQLite 永続化）のテスト。"""

from pathlib import Path

from thesis_ai.discussion.session import DiscussionSession, Turn, add_turn
from thesis_ai.discussion.store import SessionStore


def _session() -> DiscussionSession:
    base = DiscussionSession(
        session_id="thread-1",
        paper_title="Attention Is All You Need",
        paper_text="full text",
        persona_keys=("professor", "expert"),
        summary="要約テキスト",
    )
    base = add_turn(base, Turn(persona_key="professor", content="発言1", reply_to=None))
    return add_turn(base, Turn(persona_key="expert", content="発言2", reply_to=0))


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite3")
    session = _session()

    store.save(session)
    loaded = store.load("thread-1")

    assert loaded == session


def test_load_missing_returns_none(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite3")

    assert store.load("nope") is None


def test_save_replaces_turns(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite3")
    store.save(_session())

    shortened = add_turn(
        DiscussionSession(
            session_id="thread-1",
            paper_title="Attention Is All You Need",
            paper_text="full text",
            persona_keys=("professor", "expert"),
        ),
        Turn(persona_key="professor", content="only one"),
    )
    store.save(shortened)
    loaded = store.load("thread-1")

    assert loaded is not None
    assert len(loaded.turns) == 1
    assert loaded.turns[0].content == "only one"


def test_delete_removes_session(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite3")
    store.save(_session())

    store.delete("thread-1")

    assert store.load("thread-1") is None


def test_persists_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite3"
    SessionStore(db).save(_session())

    reopened = SessionStore(db).load("thread-1")

    assert reopened == _session()
