#!/usr/bin/env bash
# 無 sudo で systemd の Restart=always 相当を実現する監視ループ。
# bot を起動し、終了（クラッシュ含む）したら数秒後に再起動する。tmux 内で実行する想定。
# 停止は tmux セッションごと kill する（deploy/start-tmux.sh のヘルプ参照）。
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR" || exit 1

# cron(@reboot) 経由だと PATH が最小なので uv を絶対パスで解決する
UV="${UV:-$HOME/.local/bin/uv}"
[[ -x "$UV" ]] || UV="$(command -v uv || true)"
if [[ -z "${UV}" || ! -x "${UV}" ]]; then
  echo "[run-forever] error: uv が見つかりません" >&2
  exit 1
fi

LOG_DIR="$DIR/logs"
mkdir -p "$LOG_DIR"
# 標準出力/エラーを画面(tmux pane)とログファイルの両方へ流す
exec > >(tee -a "$LOG_DIR/bot.log") 2>&1

RESTART_WAIT=5
while true; do
  echo "[run-forever] $(date '+%F %T') starting: ${UV} run python -m thesis_ai.main"
  "${UV}" run python -m thesis_ai.main
  code=$?
  echo "[run-forever] $(date '+%F %T') exited (code=${code}); restarting in ${RESTART_WAIT}s  (停止: tmux kill-session -t thesis-ai)"
  sleep "${RESTART_WAIT}"
done
