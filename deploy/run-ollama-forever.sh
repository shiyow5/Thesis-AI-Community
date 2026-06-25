#!/usr/bin/env bash
# ollama(:11435) を常時監視する watchdog ループ。
# - ポートが応答しなければ ollama serve を前面で起動し、そのまま監視する
# - serve がクラッシュ/終了したら数秒後に再起動する（systemd Restart=always 相当）
# - 既に別インスタンスが :11435 を握っている場合は何もせず監視継続（非破壊）
# tmux セッション 'ollama-11435' 内で実行する想定（start-ollama-local.sh が起動）。
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${OLLAMA_LOCAL_HOST:-127.0.0.1:11435}"

# cron(@reboot) は PATH が最小なので ollama を絶対パスで解決する
OLLAMA_BIN="${OLLAMA_BIN:-$HOME/ollama/dist/bin/ollama}"
[[ -x "${OLLAMA_BIN}" ]] || OLLAMA_BIN="$(command -v ollama || true)"

LOG_DIR="${DIR}/logs"; mkdir -p "${LOG_DIR}"
LOG="${LOG_DIR}/ollama-${HOST##*:}.log"
exec > >(tee -a "${LOG}") 2>&1

if [[ -z "${OLLAMA_BIN}" || ! -x "${OLLAMA_BIN}" ]]; then
  echo "[ollama-watchdog] error: ollama バイナリが見つかりません (${OLLAMA_BIN})"
  exit 1
fi

CHECK_INTERVAL=10
RESTART_WAIT=5
echo "[ollama-watchdog] $(date '+%F %T') start (host=${HOST}, bin=${OLLAMA_BIN})"
while true; do
  if curl -s -m 3 "http://${HOST}/api/version" >/dev/null 2>&1; then
    # 稼働中（自分が起動した serve か既存インスタンスかを問わず）→ 監視継続
    sleep "${CHECK_INTERVAL}"
    continue
  fi
  echo "[ollama-watchdog] $(date '+%F %T') ${HOST} 応答なし → ollama serve を起動（前面で監視）"
  OLLAMA_HOST="${HOST}" "${OLLAMA_BIN}" serve
  echo "[ollama-watchdog] $(date '+%F %T') ollama serve 終了(code=$?) → ${RESTART_WAIT}s 後に再確認"
  sleep "${RESTART_WAIT}"
done
