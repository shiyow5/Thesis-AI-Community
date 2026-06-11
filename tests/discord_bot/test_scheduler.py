"""run_daily_discussion のテスト（HF/arxiv-txt は respx でモック）。"""

from pathlib import Path

import httpx
import respx

from thesis_ai.discord_bot.scheduler import run_daily_discussion
from thesis_ai.discussion.engine import DiscussionEngine
from thesis_ai.discussion.store import SessionStore
from thesis_ai.llm.base import Message
from thesis_ai.papers.trending import HF_DAILY_PAPERS_URL
from thesis_ai.personas import Persona


class FakeRouter:
    async def generate(self, messages: list[Message], *, max_tokens: int) -> str:
        return "発言"


class FakeThreadTarget:
    async def open_thread(self, *, name: str, intro: str) -> str:
        return "thread-1"


class FakePoster:
    def __init__(self) -> None:
        self.count = 0

    async def post(self, persona: Persona, content: str, *, thread_id: str | None = None) -> None:
        self.count += 1


def _hf_entry(arxiv_id: str, upvotes: int) -> dict[str, object]:
    return {"paper": {"id": arxiv_id, "title": f"Paper {arxiv_id}", "upvotes": upvotes}}


def _deps(tmp_path: Path) -> tuple[DiscussionEngine, SessionStore, FakePoster, FakeThreadTarget]:
    engine = DiscussionEngine(FakeRouter(), max_rounds=1)  # type: ignore[arg-type]
    store = SessionStore(tmp_path / "db.sqlite3")
    return engine, store, FakePoster(), FakeThreadTarget()


@respx.mock
async def test_run_daily_picks_top_and_runs(tmp_path: Path) -> None:
    respx.get(HF_DAILY_PAPERS_URL).mock(
        return_value=httpx.Response(
            200, json=[_hf_entry("1111.00001", 3), _hf_entry("2222.00002", 9)]
        )
    )
    # 上位論文 (2222.00002) の本文取得
    respx.get("https://arxiv-txt.org/pdf/2222.00002").mock(
        return_value=httpx.Response(200, text="full text")
    )
    engine, store, poster, thread_target = _deps(tmp_path)

    async with httpx.AsyncClient() as client:
        session = await run_daily_discussion(
            client, thread_target=thread_target, poster=poster, engine=engine, store=store
        )

    assert session is not None
    assert session.paper_title == "Paper 2222.00002"
    assert session.paper_text == "full text"
    assert poster.count == 4


@respx.mock
async def test_run_daily_falls_back_to_summary_when_text_unavailable(tmp_path: Path) -> None:
    respx.get(HF_DAILY_PAPERS_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"paper": {"id": "3333.00003", "title": "P", "upvotes": 1, "ai_summary": "要約"}}
            ],
        )
    )
    respx.get("https://arxiv-txt.org/pdf/3333.00003").mock(return_value=httpx.Response(404))
    respx.get("https://arxiv-txt.org/abs/3333.00003").mock(return_value=httpx.Response(404))
    respx.get("https://arxiv.org/pdf/3333.00003").mock(return_value=httpx.Response(404))
    engine, store, poster, thread_target = _deps(tmp_path)

    async with httpx.AsyncClient() as client:
        session = await run_daily_discussion(
            client, thread_target=thread_target, poster=poster, engine=engine, store=store
        )

    assert session is not None
    assert session.paper_text == "要約"


@respx.mock
async def test_run_daily_returns_none_when_no_papers(tmp_path: Path) -> None:
    respx.get(HF_DAILY_PAPERS_URL).mock(return_value=httpx.Response(200, json=[]))
    engine, store, poster, thread_target = _deps(tmp_path)

    async with httpx.AsyncClient() as client:
        result = await run_daily_discussion(
            client, thread_target=thread_target, poster=poster, engine=engine, store=store
        )

    assert result is None
    assert poster.count == 0
