# デプロイ手順（家庭用 PC 常駐: WSL2 / Windows）

本 bot は「議論中のユーザー割り込みに反応する」ため **Gateway 常時接続（常駐プロセス）** が必要です。
サーバーレス（GitHub Actions / Cloudflare）では通常メッセージの受動監視ができないため、
家庭用 PC を常時稼働させて運用します（電気代以外は無料）。

> **推奨**: WSL2（Ubuntu, systemd 有効）なら「2. WSL2 + systemd」が最も簡単です。
> ネイティブ Windows の場合は「2-alt. Windows + NSSM」を使います。
> 0 章の事前準備（Discord/Webhook/API キー）は共通です。

---

## 0. 事前準備（あなたの手作業 — 一度だけ）

### 0-1. Discord Bot の作成
1. [Discord Developer Portal](https://discord.com/developers/applications) で **New Application** を作成
2. 左メニュー **Bot** → **Add Bot**
3. **Privileged Gateway Intents** で **MESSAGE CONTENT INTENT** を **ON**（メッセージ本文取得に必須）
4. **Reset Token** でトークンを取得 → `.env` の `DISCORD_BOT_TOKEN` に設定
5. 左メニュー **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Create Public Threads`, `Send Messages in Threads`, `Manage Webhooks`, `Read Message History`
   - 生成 URL を開いて対象サーバーへ招待

### 0-2. ペルソナ投稿用 Webhook（対象チャンネルに 4 本）
1. 対象チャンネルの **設定（歯車）→ 連携サービス → ウェブフック → 新しいウェブフック**
2. 4 本作成（教授・専門家・研究生・一般）。名前/アイコンは投稿時に上書きされるので任意
3. 各 **ウェブフック URL をコピー** → `.env` の `WEBHOOK_PROFESSOR` / `WEBHOOK_EXPERT` / `WEBHOOK_GRAD_STUDENT` / `WEBHOOK_LAYPERSON`

### 0-3. チャンネル / サーバー ID
1. Discord の **設定 → 詳細設定 → 開発者モード** を ON
2. 対象チャンネルを右クリック **→ チャンネル ID をコピー** → `.env` の `DISCORD_CHANNEL_ID`
3. サーバー名を右クリック **→ サーバー ID をコピー** → `.env` の `DISCORD_GUILD_ID`

### 0-4. LLM API キー（Gemma 4 / Gemini 2.5 Flash 共通）
1. [Google AI Studio](https://aistudio.google.com/apikey) で **API キーを作成**
2. `.env` の `GEMINI_API_KEY` に設定
3. （任意）`GEMMA_MODEL` / `FLASH_MODEL` は既定値のまま可。AI Studio で利用可能なモデル名を確認のうえ調整

### 0-5. ローカルフォールバック（任意）
- LM Studio または Ollama を入れて OpenAI 互換サーバを起動した場合のみ設定
- `.env` の `LOCAL_LLM_BASE_URL`（既定 `http://localhost:1234/v1`）と `LOCAL_LLM_MODEL` を設定
- `LOCAL_LLM_MODEL` を空のままにするとフォールバックは無効（Gemma4 → Flash のみ）

---

## 1. セットアップ（Windows PC）

### 1-1. 依存のインストール
```powershell
# uv のインストール（未導入の場合）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# リポジトリ取得
git clone https://github.com/shiyow5/Thesis-AI-Community.git
cd Thesis-AI-Community

# 依存の同期
uv sync
```

### 1-2. `.env` の作成
```powershell
copy .env.example .env
# .env をエディタで開き、0章で取得した値をすべて記入
```

### 1-3. 動作確認（フォアグラウンド起動）
```powershell
uv run python -m thesis_ai.main
```
- 起動ログに `Logged in as ...` が出れば成功
- 未設定の Webhook があれば警告ログが出る
- `Ctrl+C` で停止
- 対象チャンネルに arXiv URL を貼る、または `/discuss <URL|タイトル>` で議論が始まることを確認

---

## 2. 常駐サービス化（WSL2 + systemd, 推奨）

WSL2（Ubuntu, systemd 有効）で動かす場合は **systemd ユーザーサービス**にするのが最も簡単です。
「自動起動・クラッシュ時自動再起動（`Restart=always`）」が標準で得られます。

前提: `/etc/wsl.conf` に以下があり、`systemctl is-system-running` が `running` を返すこと。
```ini
[boot]
systemd=true
```

### 2-1. サービス導入（同梱スクリプト）
リポジトリ直下で実行します。`uv` と作業ディレクトリのパスは自動補完されます。
```bash
bash deploy/install-service.sh
```
これで `~/.config/systemd/user/thesis-ai.service` を生成し、`enable --now` で起動します。
起動ログに `Logged in as ...` が出れば成功（`journalctl --user -u thesis-ai` で確認）。

### 2-2. 運用コマンド
```bash
systemctl --user status  thesis-ai     # 状態確認
systemctl --user restart thesis-ai     # 再起動
systemctl --user stop    thesis-ai     # 停止
systemctl --user disable thesis-ai     # 自動起動を無効化
journalctl  --user -u thesis-ai -f     # ログ追尾
```

### 2-3. WSL/ログアウト後も動かす（重要）
ユーザーサービスは既定でログアウト時に止まり、WSL は Windows 起動時に自動では立ち上がりません。常時稼働には次の 2 つを設定します。

1. **linger 有効化**（ログアウト後もユーザーサービスを維持。要 root, 一度だけ）:
   ```bash
   sudo loginctl enable-linger $USER
   ```
2. **Windows ログオン時に WSL を自動起動**（タスクスケジューラ）:
   - 「タスクの作成」→ トリガー「ログオン時」→ 操作「プログラムの開始」
   - プログラム: `wsl.exe`、引数: `-d <ディストリ名> -u <ユーザー名> true`
   - これで WSL（=systemd）が起動し、linger 済みのサービスが自動で立ち上がります

### 2-4. 更新手順
```bash
git pull && uv sync
systemctl --user restart thesis-ai
```

---

## 2-alt. 常駐サービス化（ネイティブ Windows + NSSM）

WSL を使わずネイティブ Windows で動かす場合は [NSSM](https://nssm.cc/) を使います。

```powershell
where uv   # uv の絶対パスを確認
nssm install ThesisAICommunity "C:\Users\<you>\.local\bin\uv.exe" "run python -m thesis_ai.main"
nssm set ThesisAICommunity AppDirectory "C:\path\to\Thesis-AI-Community"
nssm set ThesisAICommunity AppStdout "C:\path\to\Thesis-AI-Community\logs\bot.log"
nssm set ThesisAICommunity AppStderr "C:\path\to\Thesis-AI-Community\logs\bot.err.log"
nssm set ThesisAICommunity AppRotateFiles 1
nssm set ThesisAICommunity Start SERVICE_AUTO_START
nssm start ThesisAICommunity
```
運用: `nssm status|restart|stop ThesisAICommunity` / 削除 `nssm remove ThesisAICommunity confirm`。
> **代替**: NSSM を使わず Windows タスクスケジューラで「スタートアップ時／失敗時に再実行」でも可。

---

## 3. 可用性・再起動耐性

- **自動再起動**: systemd（`Restart=always`）/ NSSM がクラッシュ時に自動復帰。WSL/OS 起動時も自動起動（linger + ログオン時 WSL 起動を設定した場合）
- **セッション復元**: 議論セッションは `data/sessions.sqlite3`（SQLite）に永続化。再起動後もスレッドの割り込み質問に応答継続
- **再接続**: discord.py は Gateway 切断時に自動再接続
- **ネットワーク**: Gateway は outbound 接続のため **ポート開放不要**（NAT 内で可）

### 注意
- Windows Update の自動再起動でプロセスが落ちることがある → 自動起動でカバー
- 停電・PC 電源断時は停止。必要なら UPS や、後日 GitHub Actions による日次バックアップ運用の追加を検討

---

## 4. 更新手順

WSL2 + systemd: 「2-4」を参照（`git pull && uv sync` → `systemctl --user restart thesis-ai`）。
ネイティブ Windows + NSSM:
```powershell
nssm stop ThesisAICommunity; git pull; uv sync; nssm start ThesisAICommunity
```

---

## 5. ログとトラブルシュート

| 症状 | 確認 |
|------|------|
| 起動直後に落ちる | `.env` の必須値（`GEMINI_API_KEY` / `DISCORD_BOT_TOKEN`）欠如 → 起動時に fail-fast。`logs\bot.err.log` を確認 |
| メッセージに反応しない | Developer Portal で **MESSAGE CONTENT INTENT** が ON か |
| `/discuss` が出ない | 初回起動時にコマンド同期。数分待つ／bot を再招待（`applications.commands` スコープ必須） |
| ペルソナが投稿されない | Webhook URL が正しいか、Webhook が対象チャンネルのものか |
| 議論が短い/途切れる | 無料枠の RPD 枯渇 → ローカルフォールバック設定、または `GEMMA_MODEL`/`FLASH_MODEL` の枠を AI Studio で確認 |

ログの場所:
- WSL2 + systemd: journald（`journalctl --user -u thesis-ai`）
- ネイティブ Windows + NSSM: `logs\bot.log`（標準出力）/ `logs\bot.err.log`（エラー）

---

## 6. セキュリティ
- `.env` は **絶対にコミットしない**（`.gitignore` 済み）。トークン/キーが漏れた場合は即ローテーション
- 公開論文のみを扱い、機微情報を LLM に渡さない
