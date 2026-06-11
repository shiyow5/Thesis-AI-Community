"""run_discussion / build_intro のテスト（Discord 非依存・FakeRouter 利用）。"""

from pathlib import Path

from thesis_ai.discord_bot.runner import build_intro, run_discussion
from thesis_ai.discussion.engine import DiscussionEngine
from thesis_ai.discussion.session import STATUS_IDLE
from thesis_ai.discussion.store import SessionStore
from thesis_ai.llm.base import Message
from thesis_ai.papers.models import Paper
from thesis_ai.personas import Persona


class FakeRouter:
    def __init__(self) -> None:
        self.n = 0

    async def generate(self, messages: list[Message], *, max_tokens: int) -> str:
        self.n += 1
        return f"発言{self.n}"


class FakeThreadTarget:
    def __init__(self) -> None:
        self.opened: dict[str, str] = {}

    async def open_thread(self, *, name: str, intro: str) -> str:
        self.opened = {"name": name, "intro": intro}
        return "thread-123"


class FakePoster:
    def __init__(self) -> None:
        self.posts: list[tuple[str, str, str | None]] = []

    async def post(self, persona: Persona, content: str, *, thread_id: str | None = None) -> None:
        self.posts.append((persona.key, content, thread_id))


def _paper() -> Paper:
    return Paper(
        title="Attention Is All You Need",
        authors=("A", "B"),
        abstract="abstract",
        url="https://arxiv.org/abs/1706.03762",
        arxiv_id="1706.03762",
        ai_summary="AI 要約",
    )


def test_build_intro_contains_key_fields() -> None:
    intro = build_intro(_paper())

    assert "Attention Is All You Need" in intro
    assert "AI 要約" in intro
    assert "https://arxiv.org/abs/1706.03762" in intro


def test_build_intro_truncates_author_list() -> None:
    paper = Paper(
        title="T",
        authors=tuple(f"A{i}" for i in range(8)),
        abstract="",
        url="",
    )

    assert "ほか" in build_intro(paper)


async def test_run_discussion_full_flow(tmp_path: Path) -> None:
    engine = DiscussionEngine(FakeRouter())  # type: ignore[arg-type]
    store = SessionStore(tmp_path / "db.sqlite3")
    thread_target = FakeThreadTarget()
    poster = FakePoster()

    session = await run_discussion(
        _paper(),
        "paper full text",
        thread_target=thread_target,
        poster=poster,
        engine=engine,
        store=store,
    )

    # スレッドが開かれ、4 ペルソナが投稿された
    assert thread_target.opened["name"] == "Attention Is All You Need"
    assert len(poster.posts) == 4
    assert all(thread_id == "thread-123" for _, _, thread_id in poster.posts)

    # 最終状態は idle で永続化されている
    assert session.status == STATUS_IDLE
    loaded = store.load("thread-123")
    assert loaded is not None
    assert len(loaded.turns) == 4
    assert loaded.status == STATUS_IDLE


async def test_run_discussion_multiple_rounds(tmp_path: Path) -> None:
    engine = DiscussionEngine(FakeRouter())  # type: ignore[arg-type]
    store = SessionStore(tmp_path / "db.sqlite3")

    session = await run_discussion(
        _paper(),
        "text",
        thread_target=FakeThreadTarget(),
        poster=FakePoster(),
        engine=engine,
        store=store,
        rounds=2,
    )

    assert len(session.turns) == 8  # 4 ペルソナ × 2 ラウンド
