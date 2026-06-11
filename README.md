# Thesis-AI-Community

論文理解支援のための Discord AI 議論コミュニティ。複数の AI ペルソナ（教授・ドメイン専門家・他分野の研究生・素人）が、論文について**日本語で自律的に議論しあう**ことで、ユーザーの理解を助ける。

## 機能

- **モードA（自動）**: 1日1本、話題の論文を自動取得しスレッドで議論
- **モードB（オンデマンド）**: 論文URL/タイトルを投げるとスレッドを立てて議論
- **割り込み応答**: 議論中にユーザーが質問すると最適なペルソナが応答

## 技術スタック

- Python 3.12 / [uv](https://docs.astral.sh/uv/) / discord.py
- LLM: Gemma 4（Gemini API 無料枠・メイン）+ Gemini 2.5 Flash（品質補完）+ ローカル（フォールバック）
- 論文ソース: Hugging Face Daily Papers / arxiv-txt.org / Semantic Scholar・Crossref
- デプロイ: 家庭用 Windows PC 常駐（NSSM サービス化）

詳細な設計は [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) を参照。

## セットアップ

```bash
uv sync                  # 依存インストール
cp .env.example .env     # シークレットを記入
uv run python -m thesis_ai.main
```

事前準備（Discord Bot トークン・Webhook 4本・Gemini API キーの取得）と、家庭用 Windows PC での
**常駐運用（NSSM サービス化）** の手順は [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) を参照。

## 開発

```bash
uv run ruff format .     # フォーマット
uv run ruff check .      # リント
uv run mypy src tests    # 型チェック
uv run pytest            # テスト
```

## ライセンス

MIT
