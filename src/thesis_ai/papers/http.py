"""論文ソース API へのアクセスで共有する HTTP 設定。"""

USER_AGENT = "thesis-ai-community/0.1 (+https://github.com/shiyow5/Thesis-AI-Community)"


def default_headers() -> dict[str, str]:
    """論文ソースへのリクエストに付与する共通ヘッダ。"""
    return {"User-Agent": USER_AGENT}
