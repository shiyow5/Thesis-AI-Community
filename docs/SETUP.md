# 実環境の準備ガイド（ステップバイステップ）

ローカルで bot を動かすために必要な準備をまとめます。所要時間は全部で 15〜20 分ほどです。
常駐運用（NSSM サービス化）の手順は [DEPLOYMENT.md](DEPLOYMENT.md) を参照してください。

集める値は最終的にリポジトリルートの `.env` に記入します（[E章](#e-env-の記入)）。

---

## A. Discord Bot トークンの取得

### A-1. アプリ作成
1. https://discord.com/developers/applications を開く（Discord アカウントでログイン）
2. 右上 **New Application** → 名前（例: `Thesis-AI-Community`）を入力 → **Create**

### A-2. Bot 化と Intent 設定
3. 左メニュー **Bot** を開く
4. **Privileged Gateway Intents** の **MESSAGE CONTENT INTENT** を **ON**
   （⚠️必須。これが無いと割り込み・URL 検知が動きません）→ 下の **Save Changes**

### A-3. トークン取得
5. 同じ **Bot** ページの **Reset Token** → **Yes, do it!** → 表示された文字列をコピー
   - → `.env` の **`DISCORD_BOT_TOKEN`**（一度しか表示されないので必ず控える）

### A-4. サーバーへ招待
6. 左メニュー **OAuth2** → **URL Generator**
7. **Scopes** で `bot` と `applications.commands` にチェック
8. 下に出る **Bot Permissions** で以下にチェック:
   - `Send Messages` / `Create Public Threads` / `Send Messages in Threads` / `Manage Webhooks` / `Read Message History`
9. 最下部の **Generated URL** をコピーしてブラウザで開く → bot を入れたいサーバーを選んで **認証**

---

## B. ペルソナ投稿用 Webhook（対象チャンネルに4本）

> Webhook は bot とは別物で、ペルソナごとに名前・アイコンを変えて投稿するために使います。

1. Discord で、議論させたい**チャンネル**を用意（例: `#論文議論`）
2. そのチャンネルの **歯車アイコン（チャンネルの編集）** → **連携サービス（Integrations）** → **ウェブフック（Webhooks）**
3. **新しいウェブフック** を押す → 作成された Webhook をクリック → **ウェブフック URL をコピー**
4. これを **4回繰り返して4本**作り、それぞれを `.env` の以下へ割り当て:
   - 1本目 → `WEBHOOK_PROFESSOR`（教授）
   - 2本目 → `WEBHOOK_EXPERT`（専門家）
   - 3本目 → `WEBHOOK_GRAD_STUDENT`（研究生）
   - 4本目 → `WEBHOOK_LAYPERSON`（一般）

> 名前・アイコンは投稿時にコードが上書きするので、ここでは適当で OK です。

---

## C. チャンネル / サーバー ID の取得

1. Discord の **ユーザー設定（左下の歯車）** → **詳細設定（Advanced）** → **開発者モード** を **ON**
2. 対象チャンネルを**右クリック** → **チャンネル ID をコピー** → `.env` の **`DISCORD_CHANNEL_ID`**
3. サーバー名（左の一番上）を**右クリック** → **サーバー ID をコピー** → `.env` の **`DISCORD_GUILD_ID`**

---

## D. Google AI Studio の API キー（Gemma 4 / Gemini Flash 共通）

1. https://aistudio.google.com/apikey を開く（Google アカウントでログイン）
2. **Create API key** → プロジェクトを選択（無ければ自動作成）→ キーが表示される
3. コピー → `.env` の **`GEMINI_API_KEY`**
   - クレジットカード登録は不要（無料枠で利用可能）

---

## E. `.env` の記入

リポジトリのルートで `.env.example` をコピーして `.env` を作り、上で集めた値を貼ります:

```env
DISCORD_BOT_TOKEN=（Aで取得）
DISCORD_GUILD_ID=（Cで取得）
DISCORD_CHANNEL_ID=（Cで取得）

WEBHOOK_PROFESSOR=（Bの1本目）
WEBHOOK_EXPERT=（Bの2本目）
WEBHOOK_GRAD_STUDENT=（Bの3本目）
WEBHOOK_LAYPERSON=（Bの4本目）

GEMINI_API_KEY=（Dで取得）

# ローカルフォールバックを使わないなら空のままでOK
LOCAL_LLM_MODEL=
```

```bash
cp .env.example .env   # 既に .env があれば上書きに注意
```

> `.env` は `.gitignore` 済みなのでコミットされません。漏れたら必ず再発行してください。

---

## F. 動作確認

```bash
uv sync                          # 初回のみ依存インストール
uv run python -m thesis_ai.main
```

- ログに `Logged in as ...` が出れば成功
- 対象チャンネルに arXiv URL（例: `https://arxiv.org/abs/1706.03762`）を貼る、または
  `/discuss 1706.03762` を実行 → スレッドが立って4ペルソナが議論を始めます
- スレッド内で質問を投げると、適切なペルソナが割り込み応答します
- `Ctrl+C` で停止。常駐化（NSSM）は [DEPLOYMENT.md](DEPLOYMENT.md) の2章へ

---

## つまずきやすいポイント

| 症状 | 対処 |
|------|------|
| bot がメッセージに反応しない | A-2 の **MESSAGE CONTENT INTENT** が ON か再確認 |
| `/discuss` がコマンド一覧に出ない | 初回は同期に数分かかることあり。出ない場合は A-4 の招待 URL に `applications.commands` が入っているか確認して入れ直し |
| 起動直後に落ちる | `GEMINI_API_KEY` か `DISCORD_BOT_TOKEN` が未記入（起動時にエラーで止まる仕様） |
| ペルソナが投稿されない | Webhook URL が正しいか、対象チャンネルの Webhook か |
| 議論が短い/途切れる | 無料枠の RPD 枯渇 → ローカルフォールバック設定、または AI Studio で実枠を確認し `main.py` の定数を調整 |
