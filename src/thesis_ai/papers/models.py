"""論文を表す不変データモデル。"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Paper:
    """論文のメタデータ。生成後は不変。

    Attributes:
        title: 論文タイトル。
        authors: 著者名のタプル。
        abstract: アブストラクト（原文）。
        url: 参照 URL（通常は arXiv の abs ページ）。
        arxiv_id: arXiv ID（バージョン無し）。arXiv 以外の論文では None。
        ai_summary: HF Daily Papers が付与する AI 要約（あれば）。
        ai_keywords: AI 抽出キーワード（あれば）。
        upvotes: HF 上の upvote 数（あれば）。トレンド選定に使用。
    """

    title: str
    authors: tuple[str, ...]
    abstract: str
    url: str
    arxiv_id: str | None = None
    ai_summary: str | None = None
    ai_keywords: tuple[str, ...] = field(default_factory=tuple)
    upvotes: int | None = None
