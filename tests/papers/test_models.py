"""Paper モデルのテスト。"""

import dataclasses

import pytest

from thesis_ai.papers.models import Paper


def test_paper_defaults() -> None:
    paper = Paper(title="T", authors=("A",), abstract="abs", url="http://x")

    assert paper.arxiv_id is None
    assert paper.ai_summary is None
    assert paper.ai_keywords == ()
    assert paper.upvotes is None


def test_paper_is_immutable() -> None:
    paper = Paper(title="T", authors=(), abstract="", url="")

    with pytest.raises(dataclasses.FrozenInstanceError):
        paper.title = "changed"  # type: ignore[misc]
