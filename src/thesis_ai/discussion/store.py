"""議論セッションの SQLite 永続化。

プロセス再起動後にセッション（論文情報・発言履歴・状態）を復元できるようにする。
接続は操作ごとに開閉し、スレッド跨ぎの利用でも安全にする。
"""

import json
import sqlite3
from pathlib import Path

from thesis_ai.discussion.session import DiscussionSession, Turn

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    paper_title  TEXT NOT NULL,
    paper_text   TEXT NOT NULL,
    persona_keys TEXT NOT NULL,
    status       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    session_id  TEXT NOT NULL,
    idx         INTEGER NOT NULL,
    persona_key TEXT NOT NULL,
    content     TEXT NOT NULL,
    reply_to    INTEGER,
    PRIMARY KEY (session_id, idx),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
"""


class SessionStore:
    """セッションの保存・読み込み・削除を行う。"""

    def __init__(self, db_path: str | Path) -> None:
        self._path = str(db_path)
        parent = Path(self._path).parent
        if parent and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            # 既存 DB（reply_to 列が無い）への簡易マイグレーション
            cols = {row[1] for row in conn.execute("PRAGMA table_info(turns)")}
            if "reply_to" not in cols:
                conn.execute("ALTER TABLE turns ADD COLUMN reply_to INTEGER")

    def save(self, session: DiscussionSession) -> None:
        """セッションを保存（upsert）する。発言は全置換する。"""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, paper_title, paper_text, persona_keys, status) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "paper_title=excluded.paper_title, paper_text=excluded.paper_text, "
                "persona_keys=excluded.persona_keys, status=excluded.status",
                (
                    session.session_id,
                    session.paper_title,
                    session.paper_text,
                    json.dumps(list(session.persona_keys)),
                    session.status,
                ),
            )
            conn.execute("DELETE FROM turns WHERE session_id = ?", (session.session_id,))
            conn.executemany(
                "INSERT INTO turns (session_id, idx, persona_key, content, reply_to) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (session.session_id, idx, turn.persona_key, turn.content, turn.reply_to)
                    for idx, turn in enumerate(session.turns)
                ],
            )

    def load(self, session_id: str) -> DiscussionSession | None:
        """セッションを読み込む。存在しなければ None。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT paper_title, paper_text, persona_keys, status "
                "FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            turn_rows = conn.execute(
                "SELECT persona_key, content, reply_to FROM turns "
                "WHERE session_id = ? ORDER BY idx",
                (session_id,),
            ).fetchall()

        paper_title, paper_text, persona_keys_json, status = row
        turns = tuple(
            Turn(persona_key=pk, content=content, reply_to=reply_to)
            for pk, content, reply_to in turn_rows
        )
        return DiscussionSession(
            session_id=session_id,
            paper_title=paper_title,
            paper_text=paper_text,
            persona_keys=tuple(json.loads(persona_keys_json)),
            turns=turns,
            status=status,
        )

    def delete(self, session_id: str) -> None:
        """セッションと発言を削除する。"""
        with self._connect() as conn:
            conn.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
