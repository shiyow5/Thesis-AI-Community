"""detect_paper_query / run_on_demand_discussion のテスト。"""

from pathlib import Path

import httpx
import respx

from thesis_ai.discord_bot.ondemand import detect_paper_query, run_on_demand_discussion
from thesis_ai.discussion.engine import DiscussionEngine
from thesis_ai.discussion.store import SessionStore
from thesis_ai.llm.base import Message
from thesis_ai.papers.resolve import ARXIV_API_URL
from thesis_ai.personas import Persona


class FakeRouter:
    """司会選択には4名を順に返し（その後 DONE）、発言生成には定型を返す。"""

    def __init__(self) -> None:
        self._speakers = ["professor", "expert", "grad_student", "layperson"]

    async def generate(self, messages: list[Message], *, max_tokens: int) -> str:
        if "次に発言すべき" in messages[-1].content:
            return self._speakers.pop(0) if self._speakers else "DONE"
        return "発言"


class FakeThreadTarget:
    async def open_thread(self, *, name: str, intro: str) -> str:
        return "thread-1"


class FakePoster:
    def __init__(self) -> None:
        self.count = 0
        self.notices = 0

    async def post(self, persona: Persona, content: str, *, thread_id: str | None = None) -> None:
        self.count += 1

    async def post_notice(
        self, content: str, *, thread_id: str | None = None, username: str = "📄 論文要約"
    ) -> None:
        self.notices += 1


_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v1</id>
    <title>Attention Is All You Need</title>
    <summary>We propose the Transformer.</summary>
    <author><name>Vaswani</name></author>
  </entry>
</feed>"""


def test_detect_paper_query_from_url() -> None:
    assert detect_paper_query("見て https://arxiv.org/abs/1706.03762 これ") == "1706.03762"


def test_detect_paper_query_from_bare_id() -> None:
    assert detect_paper_query("2401.00001 を議論して") == "2401.00001"


def test_detect_paper_query_none_for_chitchat() -> None:
    assert detect_paper_query("おはよう、今日は良い天気だね") is None


@respx.mock
async def test_run_on_demand_resolves_and_runs(tmp_path: Path) -> None:
    respx.get(ARXIV_API_URL).mock(return_value=httpx.Response(200, text=_ATOM))
    respx.get("https://arxiv-txt.org/pdf/1706.03762").mock(
        return_value=httpx.Response(200, text="full text")
    )
    engine = DiscussionEngine(FakeRouter())  # type: ignore[arg-type]
    store = SessionStore(tmp_path / "db.sqlite3")
    poster = FakePoster()

    session = await run_on_demand_discussion(
        httpx.AsyncClient(),
        "https://arxiv.org/abs/1706.03762",
        thread_target=FakeThreadTarget(),
        poster=poster,
        engine=engine,
        store=store,
    )

    assert session is not None
    assert session.paper_title == "Attention Is All You Need"
    assert session.paper_text == "full text"
    assert poster.count == 4


@respx.mock
async def test_run_on_demand_returns_none_when_unresolved(tmp_path: Path) -> None:
    empty = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    respx.get(ARXIV_API_URL).mock(return_value=httpx.Response(200, text=empty))
    engine = DiscussionEngine(FakeRouter())  # type: ignore[arg-type]
    store = SessionStore(tmp_path / "db.sqlite3")
    poster = FakePoster()

    result = await run_on_demand_discussion(
        httpx.AsyncClient(),
        "未知のタイトル xyz",
        thread_target=FakeThreadTarget(),
        poster=poster,
        engine=engine,
        store=store,
    )

    assert result is None
    assert poster.count == 0
