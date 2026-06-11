"""議論セッションの不変状態と更新関数。

状態は frozen dataclass とし、変更は新しいコピーを返す関数で行う（in-place 変更禁止）。
"""

from dataclasses import dataclass, field, replace

STATUS_ACTIVE = "active"
STATUS_IDLE = "idle"
STATUS_DONE = "done"


@dataclass(frozen=True)
class Turn:
    """1 つの発言。

    Attributes:
        persona_key: 発言したペルソナ。
        content: 発言本文。
        reply_to: 特定の過去発言への返信ならその発言のインデックス。全体/新論点なら None。
    """

    persona_key: str
    content: str
    reply_to: int | None = None


@dataclass(frozen=True)
class DiscussionSession:
    """1 論文に対する議論セッション。

    Attributes:
        session_id: Discord スレッド ID（永続化のキー）。
        paper_title: 論文タイトル。
        paper_text: 取得済みの論文本文（要約生成にのみ使用）。
        persona_keys: 参加ペルソナのキー（発言順）。
        turns: これまでの発言列。
        status: ``active`` / ``idle`` / ``done``。
        summary: 生成済みの論文要約。議論・割り込みの文脈にはこれを使い、全文の再送を避ける。
    """

    session_id: str
    paper_title: str
    paper_text: str
    persona_keys: tuple[str, ...]
    turns: tuple[Turn, ...] = field(default_factory=tuple)
    status: str = STATUS_ACTIVE
    summary: str | None = None


def add_turn(session: DiscussionSession, turn: Turn) -> DiscussionSession:
    """発言を 1 つ追加した新しいセッションを返す。"""
    return replace(session, turns=(*session.turns, turn))


def set_status(session: DiscussionSession, status: str) -> DiscussionSession:
    """ステータスを更新した新しいセッションを返す。"""
    return replace(session, status=status)


def set_summary(session: DiscussionSession, summary: str) -> DiscussionSession:
    """要約を設定した新しいセッションを返す。"""
    return replace(session, summary=summary)
