"""run_discussion / build_intro / render_turn のテスト（Discord 非依存）。"""

from pathlib import Path

from thesis_ai.discord_bot.runner import build_intro, render_turn, run_discussion
from thesis_ai.discussion.engine import DiscussionEngine
from thesis_ai.discussion.session import STATUS_IDLE, Turn
from thesis_ai.discussion.store import SessionStore
from thesis_ai.llm.base import Message
from thesis_ai.papers.models import Paper
from thesis_ai.personas import PROFESSOR, Persona


def _is_selection(messages: list[Message]) -> bool:
    return "次に発言すべき" in messages[-1].content


class StubRouter:
    """司会選択には speakers を順に（尽きたら DONE）、発言生成には連番を返す。"""

    def __init__(self, speakers: list[str]) -> None:
        self._speakers = list(speakers)
        self.n = 0

    async def generate(self, messages: list[Message], *, max_tokens: int) -> str:
        if _is_selection(messages):
            return self._speakers.pop(0) if self._speakers else "DONE"
        self.n += 1
        return f"発言{self.n}"


class AlwaysSpeakRouter:
    """司会選択には常に professor（DONE しない）、発言生成には連番を返す。"""

    def __init__(self) -> None:
        self.n = 0

    async def generate(self, messages: list[Message], *, max_tokens: int) -> str:
        if _is_selection(messages):
            return "professor"
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
        self.notices: list[tuple[str, str | None]] = []

    async def post(self, persona: Persona, content: str, *, thread_id: str | None = None) -> None:
        self.posts.append((persona.key, content, thread_id))

    async def post_notice(
        self, content: str, *, thread_id: str | None = None, username: str = "📄 論文要約"
    ) -> None:
        self.notices.append((content, thread_id))


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
    speakers = ["professor", "expert", "grad_student", "layperson"]
    engine = DiscussionEngine(StubRouter(speakers))  # type: ignore[arg-type]
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

    # スレッドが開かれ、要約が1件投稿されてから、司会が選んだ 4 名が発言
    assert thread_target.opened["name"] == "Attention Is All You Need"
    assert len(poster.notices) == 1  # 論文要約
    assert poster.notices[0][1] == "thread-123"
    assert [pk for pk, _, _ in poster.posts] == speakers
    assert all(thread_id == "thread-123" for _, _, thread_id in poster.posts)

    assert session.status == STATUS_IDLE
    loaded = store.load("thread-123")
    assert loaded is not None
    assert len(loaded.turns) == 4
    assert loaded.status == STATUS_IDLE


async def test_run_discussion_stops_when_done(tmp_path: Path) -> None:
    # 単一ペルソナ構成: 全員（=professor）が発言した後に DONE で終了する。
    engine = DiscussionEngine(StubRouter(["professor"]), personas=(PROFESSOR,))  # type: ignore[arg-type]
    store = SessionStore(tmp_path / "db.sqlite3")
    poster = FakePoster()

    session = await run_discussion(
        _paper(),
        "text",
        thread_target=FakeThreadTarget(),
        poster=poster,
        engine=engine,
        store=store,
    )

    # 1 発言の後に司会が DONE → 全員発言済みなので終了
    assert len(session.turns) == 1
    assert len(poster.posts) == 1


async def test_run_discussion_respects_max_turns(tmp_path: Path) -> None:
    # 司会が決して DONE しない場合でも max_turns で打ち切られる
    engine = DiscussionEngine(AlwaysSpeakRouter())  # type: ignore[arg-type]
    store = SessionStore(tmp_path / "db.sqlite3")

    session = await run_discussion(
        _paper(),
        "text",
        thread_target=FakeThreadTarget(),
        poster=FakePoster(),
        engine=engine,
        store=store,
        max_turns=3,
    )

    assert len(session.turns) == 3


def test_render_turn_plain_when_no_reply() -> None:
    turn = Turn(persona_key="professor", content="全体への発言")
    assert render_turn(turn, ()) == "全体への発言"


def test_render_turn_quotes_reply_target() -> None:
    prior = (Turn(persona_key="professor", content="自己注意は重要だ"),)
    turn = Turn(persona_key="expert", content="同意します", reply_to=0)

    rendered = render_turn(turn, prior)

    assert rendered.startswith("> **教授**: 自己注意は重要だ")
    assert "同意します" in rendered
