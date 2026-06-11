# Thesis-AI-Community 実装・デプロイ計画

> 論文理解支援のための Discord AI 議論コミュニティ。複数の AI ペルソナ（教授・ドメイン専門家・他分野の研究生・素人）が、論文について日本語で自律的に議論しあう。

## Context（背景・目的）

ユーザーが論文を多角的に理解できるよう、Discord 上で AI ペルソナ群が論文を議論する。

満たすべき要件:
- **モードA（自動）**: 1日1本、話題の論文を自動取得し、スレッドを立ててペルソナ群が議論
- **モードB（オンデマンド）**: ユーザーが論文URL/タイトルを投稿 → スレッドを立てて議論
- **割り込み応答**: 議論の途中でユーザーが質問・コメントを投げたら、最適なペルソナが応答する
- 予算ほぼゼロ。バージョン管理は GitHub。

### リサーチで判明した重要事実
1. **「すぐ応答しないとトークンが切れる」は誤解**。3秒ACK/15分follow-up制限は **Slash Command (Interaction) 固有**。Gateway接続botの `channel.send` と **Webhook投稿には時間制約がない**（レート制限のみ）。議論本体は `channel.send`/Webhook で出すため、この問題は構造的に発生しない。
2. **割り込み応答にはGateway常時接続（常駐プロセス）が必須**。サーバーレス（GitHub Actions/Cloudflare）では通常メッセージの受動監視ができない。→ **家のWindows PC常駐**で確定。
3. **論文ソース**: Hugging Face Daily Papers JSON API（`GET https://huggingface.co/api/daily_papers` 認証不要・`ai_summary`付き）でトレンド取得、本文は **arxiv-txt.org**（URL置換のみでプレーンテキスト）が最楽。
4. **LLM**: 下記「LLM 戦略」参照。Gemma 4（Gemini API無料枠 ~1,500 RPD）を主力、Gemini 2.5 Flash を品質補完、ローカルをフォールバック。

### 確定した方針
- デプロイ: **家のWindows PC常駐**（NSSM等でサービス化）
- 言語: **Python + discord.py**（uv / pytest / mypy / ruff）
- LLM: **Gemma 4（メイン）+ Gemini 2.5 Flash（品質補完）+ ローカル（フォールバック）**、差し替え可能な抽象化
- Git: **フルワークフロー**（Issue→ブランチ→PR→CI→マージ）

---

## LLM 戦略（2026-06 時点）

| 役割 | モデル | 経由 | 無料枠(free tier) | コンテキスト | 用途 |
|---|---|---|---|---|---|
| **メイン** | **Gemma 4 (27B)** | Gemini API | **~1,500 RPD**（複数情報源, 要AI Studio実値確認） | 1M | 議論ターンの大量生成。Apache 2.0・多言語SOTA級 |
| **品質補完** | **Gemini 2.5 Flash** | Gemini API | 250 RPD / Flash-Lite 1,000 RPD（2025/12削減後） | 1M | 議論の要約・割り込みの的確な回答など品質重視ポイント限定 |
| **フォールバック** | ローカル(Gemma 4 or LFM2軽量) | LM Studio/Ollama OpenAI互換 | 無制限(電気代のみ) | 32K〜 | API枯渇/障害時の縮退運転 |

設計上の含意:
- **メインを Gemma 4 にすることで無料枠が Flash 単独の約6倍**に。日次の議論量に十分な余裕。
- Gemma 4 は **Apache 2.0** なのでローカルフォールバックも同系列で統一でき、振る舞いの一貫性が高い（家PCのVRAMが厳しければローカルは LFM2 系の軽量モデルに切替）。
- レート数値は2026年に複数回変動しており**ブレがある**。`llm/router.py` は日次/分次の枠をconfig化し、起動時にAI Studioの実枠で上書き可能にする。枠超過は次段モデルへ自動退避。

---

## アーキテクチャ全体像

```
[ 家のWindows PC: 単一Pythonプロセス常駐 (NSSM でサービス化) ]
│
├─ discord.py Gateway Bot ×1  ── メッセージ/コマンド受信専用
│    ├─ on_message: 議論スレッド内のユーザー発言を検知 → 割り込みキューへ
│    ├─ /discuss <URL|title>: モードB起動
│    └─ tasks.loop(daily): モードA日次トリガー
│
├─ Discussion Engine ── ターン制オーケストレータ
│    ├─ セッション状態 (SQLite 永続化, 再起動耐性)
│    └─ 割り込みルーター: ユーザー質問 → 最適ペルソナ選定
│
├─ LLM Router ── Gemma4 → Gemini Flash(品質補完) → ローカル(フォールバック) + レート制御
│
├─ Paper Layer ── HF Daily Papers / arxiv-txt / Semantic Scholar・Crossref
│
└─ Persona Webhooks ×4 ── username/avatar_url 上書きで各ペルソナとして投稿
```

**ペルソナ実装**: 「受信用 Bot 1個（Gateway）+ 投稿用 Webhook 4本」のハイブリッド。
Webhook は botトークン不要・`username`/`avatar_url` を投稿ごとに上書きでき、4ペルソナを別アバターで安価に表現。ユーザー発言の受動検知には Gateway bot が1個必要。両者の組み合わせが管理コスト最小。

---

## モジュール / ファイル構成

uv プロジェクト。小さく分割（200-400行目安）。

```
Thesis-AI-Community/
├─ pyproject.toml                 # uv, deps, ruff/mypy設定
├─ .env.example                   # 必要なシークレット一覧（実値はコミットしない）
├─ README.md
├─ docs/IMPLEMENTATION_PLAN.md    # 本ファイル
├─ src/thesis_ai/
│  ├─ config.py                   # pydantic-settings で .env ロード・必須値検証(起動時fail-fast)
│  ├─ personas.py                 # 4ペルソナ定義(name, avatar, system prompt, webhook env key)
│  ├─ llm/
│  │  ├─ base.py                  # LLMClient Protocol (generate(messages)->str)
│  │  ├─ gemini.py                # Gemini API実装(google-genai)。Gemma4 / Gemini Flash 両対応
│  │  ├─ local.py                 # ローカル(OpenAI互換API: LM Studio/Ollama)
│  │  └─ router.py                # 用途別ルーティング + 日次枠管理 + フォールバック + 指数バックオフ
│  ├─ papers/
│  │  ├─ trending.py              # HF Daily Papers から当日のトレンド論文選定(upvotes降順)
│  │  ├─ fetch.py                 # 本文取得: arxiv-txt → arxiv/html → ar5iv → PDF(PyMuPDF)
│  │  ├─ resolve.py               # URL/タイトル/DOI → 論文メタ解決(arxiv id抽出, S2, Crossref)
│  │  └─ models.py                # Paper データクラス(frozen dataclass)
│  ├─ discussion/
│  │  ├─ engine.py                # ターン制議論生成オーケストレータ
│  │  ├─ session.py               # セッション状態(frozen, update関数で新コピー)
│  │  ├─ interrupt.py             # 割り込み→ペルソナ選定ルーター
│  │  └─ store.py                 # SQLite 永続化(セッション復元)
│  ├─ discord_bot/
│  │  ├─ bot.py                   # discord.py Client, on_message, on_ready
│  │  ├─ webhooks.py              # ペルソナWebhook投稿(レート制御, スレッド対応)
│  │  ├─ commands.py              # /discuss スラッシュコマンド(3秒defer→Webhookで議論出力)
│  │  └─ scheduler.py             # tasks.loop による日次モードA起動
│  └─ main.py                     # エントリポイント(bot起動)
├─ tests/                         # pytest, 各レイヤ単体 + 結合
└─ .github/workflows/ci.yml       # ruff + mypy + pytest
```

---

## 主要フロー

### モードA（日次自動議論）
1. `scheduler.py` が `tasks.loop(time=...)` で1日1回起動
2. `trending.py` が HF Daily Papers から当日トップ論文を選定（arxiv id, タイトル, ai_summary 取得）
3. `fetch.py` が本文取得（arxiv-txt.org 優先、失敗時フォールバック）
4. 指定チャンネルに導入メッセージを投稿 → `startThread()` でスレッド作成
5. `engine.py` がターン制で各ペルソナの発言を生成、`webhooks.py` で順次投稿（投稿間 1-2秒 wait）
6. セッションを `store.py` に保存（スレッドID=セッションキー）

### モードB（オンデマンド議論）
- **経路1（推奨・自動検知）**: ユーザーが対象チャンネルに論文URLを貼る → `on_message` が arxiv URL を検知 → `resolve.py` で論文解決 → 以降モードAと同じ議論フロー
- **経路2（明示コマンド）**: `/discuss <URL|title>` → 3秒以内に defer ACK（「議論を開始しました」）→ スレッド作成 → 議論本体は Webhook で出力（15分制限を回避）

### 割り込み応答
1. `on_message` が「議論スレッド内」かつ「bot/webhook以外」の発言を検知
2. 該当スレッドのアクティブセッションの**割り込みキュー**に追加
3. `engine.py` は次のターン境界で割り込みを優先処理:
   - `interrupt.py` がユーザー質問 + 直近議論履歴 + 各ペルソナ定義を LLM に渡し、**最も適切に答えられるペルソナを1人（必要なら複数）選定**
   - 選ばれたペルソナがユーザーに向けて回答を生成 → Webhook 投稿
4. 議論が一旦終了/アイドル化していた場合でも、`store.py` からセッションを復元して応答（再起動耐性）

---

## LLM 抽象化とレート制御（`llm/`）

- `base.py`: `LLMClient` Protocol。`async generate(messages, *, max_tokens) -> str`
- `gemini.py`: google-genai SDK。モデル名を引数化し **Gemma 4 と Gemini 2.5 Flash の両方を同一実装**で呼ぶ
- `router.py`:
  - **用途別ルーティング**: 通常の議論ターン=Gemma 4、要約・割り込みの的確回答=Gemini Flash
  - **日次/分次枠管理**: モデルごとに RPD/RPM をトークンバケットで管理、枠超過前に次段へ退避
  - **フォールバック連鎖**: Gemma 4 → Gemini Flash → ローカル
  - **指数バックオフ**: 429 は `Retry-After` 準拠でリトライ
  - **コンテキスト効率**: 1M を活かし「論文全文 + 議論履歴 + 全ペルソナ定義」を1プロンプトに詰め、1ターン=1コールで複数ペルソナ生成も選択可（RPD節約）。多様性が要る場面はペルソナ別コールに切替可能
- ローカルは LM Studio / Ollama の **OpenAI互換エンドポイント** 経由

---

## ペルソナ設計（`personas.py`）

4ペルソナ。各々 system prompt でキャラ・口調・着眼点を定義:
- **教授**: 理論的背景・先行研究との関係・限界を指摘。厳密で俯瞰的
- **ドメイン専門家**: 手法の新規性・実装的妥当性・再現性を実務目線で評価
- **他分野の研究生**: 専門外から素朴な疑問・他分野への応用可能性を投げる
- **素人**: 専門用語を噛み砕いて質問し、議論を平易化する触媒

各ペルソナは `webhook_url`（env）と `avatar_url`、表示名を持つ。割り込みルーターはこの定義で担当を選ぶ。

---

## デプロイ（家のWindows PC常駐）

- **サービス化**: NSSM で `uv run python -m thesis_ai.main` を Windows サービス登録（OS起動時自動起動・クラッシュ自動再起動）。代替: タスクスケジューラ
- **可用性対策**: ヘルスログ出力、例外は握りつぶさず再接続（discord.py は自動再接続あり）。SQLite 永続化で再起動後にセッション復元
- **シークレット**: `.env`（Bot Token, 4 Webhook URL, Gemini API Key）。`.gitignore` でコミット禁止、`.env.example` で項目を明示。起動時 `config.py` が必須値を検証し fail-fast
- **ネットワーク**: Gateway は outbound 接続のため**ポート開放不要**（NAT内でOK）

---

## GitHub フルワークフロー & CI

- 各実装フェーズを Issue 化 → `feature/*` ブランチ → PR（Issueリンク）→ CI 通過 → マージ
- `.github/workflows/ci.yml`: `uv sync` → `ruff format --check` → `ruff check` → `mypy` → `pytest`
- コミット規約: `feat:` / `fix:` / `test:` 等。小さく頻繁に
- 議論実行自体は家PC常駐プロセスが担う。Actions は CI（テスト/lint）専用

---

## 実装フェーズ（TDD: 各フェーズで先にテスト）

| Phase | 内容 | 主な成果物 |
|---|---|---|
| 0 | リポジトリ初期化 | uv 構成, ci.yml, .env.example, ruff/mypy 設定 |
| 1 | 論文取得レイヤ | `papers/*` + テスト（HTTPモック、フォールバック分岐） |
| 2 | LLM抽象+Gemini(Gemma4/Flash)+レート制御 | `llm/base,gemini,router` + テスト |
| 3 | 議論エンジン | `discussion/engine,session,store`, `personas.py` + テスト |
| 4 | Discord統合 | `discord_bot/bot,webhooks`, `main.py`（手動E2E） |
| 5 | モードA日次 | `scheduler.py` + 結合 |
| 6 | モードB | `commands.py` + URL貼付検知 |
| 7 | 割り込み応答 | `discussion/interrupt.py` + `on_message` 連携 + テスト |
| 8 | ローカルフォールバック | `llm/local.py` + router 連携 |
| 9 | デプロイ | NSSM サービス化手順, 運用 README |

---

## 検証方法（end-to-end）

- **単体/結合**: `uv run pytest`（HTTP・LLM・Discord はモック化）。カバレッジ 80%+ を目標
- **論文レイヤ スモーク**: 実 HF API / arxiv-txt を叩く `@pytest.mark.smoke`（CI では skip、手動実行）
- **LLM スモーク**: 実 Gemma4 / Gemini に1コールして日本語応答を確認
- **Discord E2E（手動）**: 専用テストサーバーで
  1. `/discuss <arxiv URL>` → スレッド生成 + 4ペルソナ議論を確認
  2. 議論スレッドにユーザーが質問投稿 → 適切なペルソナが応答（割り込み要件）
  3. プロセス再起動後にセッション復元・応答継続を確認
  4. メインLLMを意図的に失敗させフォールバックを確認
- **モードA**: スケジューラのトリガー時刻を直近に設定し、日次フローが最後まで通ることを確認

---

## リスクと対策

| リスク | 対策 |
|---|---|
| 家PCの停止（停電/再起動） | NSSM 自動再起動 + SQLite セッション復元。必要なら後日 Actions による日次バックアップ追加 |
| HF Daily Papers は非公式API（スキーマ変更） | キー欠損耐性・UA設定、失敗時 arxiv API へフォールバック |
| 無料枠 RPD 枯渇/変動 | 枠をconfig化し起動時に実値確認、超過前に次段モデルへ退避、最終はローカル |
| arxiv-txt/ar5iv 変換失敗(~25%) | 多段フォールバック（arxiv/html → ar5iv → PDF+PyMuPDF） |
| 無料LLM入出力が学習に使われうる | 公開論文のみ扱い機微情報を載せない設計 |
| Webhook レート(30/min・サーバー内共有) | 投稿間 1-2秒 wait、ターン制で逐次投稿 |

---

## 出典（主要）
- Gemma 4 / Gemini API 無料枠: https://thesoogroup.com/blog/google-ai-breakthrough-gemini-api-tiers-vids-lyria-veo-gemma-4 , https://gemma4-ai.com/blog/gemma4-free-api-limits , https://openrouter.ai/google/gemma-4-31b-it:free , https://ai.google.dev/gemini-api/docs/rate-limits
- Discord: https://docs.discord.com/developers/interactions/receiving-and-responding , https://docs.discord.com/developers/topics/rate-limits
- 論文ソース: https://huggingface.co/docs/hub/en/api , https://info.arxiv.org/help/api/user-manual.html , https://www.arxiv-txt.org/ , https://ar5iv.labs.arxiv.org/
