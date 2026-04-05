#!/bin/bash
# check-patch.sh
# 毎週月曜4時: パッチバージョンを確認し、更新があればガイドを自動更新する
#
# cron登録:
#   0 4 * * 1 /home/ojita/lol-guides-jp/scripts/check-patch.sh >> /home/ojita/lol-guides-jp/scripts/cron.log 2>&1

set -euo pipefail

export NVM_DIR="/home/ojita/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
DATE=$(date +%Y-%m-%d)
LOG_PREFIX="[${DATE} $(date +%H:%M:%S)]"
PATCH_FILE="${PROJECT_DIR}/current-patch.txt"
CLAUDE_LOCAL="/home/ojita/CLAUDE.local.md"

source "${PROJECT_DIR}/scripts/lib.sh"

# --- ドライランフラグ ---
DRY_RUN=0
for _arg in "$@"; do [ "$_arg" = "--dry-run" ] && DRY_RUN=1; done
export DRY_RUN

# --- 失敗通知（CLAUDE.local.md への追記） ---
notify_failure() {
    local reason="$1"
    echo "${LOG_PREFIX} ERROR: ${reason}"
    echo "⚠️ ${DATE}: lol-guides-jp check-patch.sh 失敗（${reason}）" >> "${CLAUDE_LOCAL}"
}

cd "$PROJECT_DIR" || { echo "${LOG_PREFIX} ERROR: ディレクトリが見つかりません"; exit 1; }

echo "${LOG_PREFIX} ===== パッチチェック開始 ====="

# --- 最新パッチバージョンを取得（L1: Python stdlib、公式ニュースページから抽出） ---
LATEST=$(python3 - <<'PYEOF'
import urllib.request, re, sys
try:
    req = urllib.request.Request(
        "https://www.leagueoflegends.com/en-us/news/game-updates/",
        headers={"User-Agent": "Mozilla/5.0 (compatible; patch-checker/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", errors="ignore")
    matches = re.findall(r'patch-(\d+)-(\d+)-notes', html)
    if not matches:
        raise ValueError("パッチノートリンクが見つかりません")
    major, minor = max((int(m), int(n)) for m, n in matches)
    print(f"{major}.{minor}")
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
) || {
    notify_failure "最新パッチバージョン取得失敗"
    exit 1
}

echo "${LOG_PREFIX} INFO: 最新パッチ=${LATEST}"

# --- 既知パッチと比較 ---
CURRENT=$(cat "${PATCH_FILE}" 2>/dev/null | tr -d '[:space:]' || echo "")

if [ "${LATEST}" = "${CURRENT}" ]; then
    echo "${LOG_PREFIX} INFO: パッチ変更なし（${CURRENT}）。終了"
    echo "${LOG_PREFIX} ===== パッチチェック完了 ====="
    exit 0
fi

echo "${LOG_PREFIX} INFO: 新パッチ検出: ${CURRENT} → ${LATEST}"

if [ "${DRY_RUN:-0}" = "1" ]; then
    echo "${LOG_PREFIX} DRY-RUN: fetch-patch-notes.py ${LATEST} をスキップ"
    echo "${LOG_PREFIX} DRY-RUN: update-guides をスキップ"
    echo "${LOG_PREFIX} DRY-RUN: current-patch.txt 更新をスキップ"
    echo "${LOG_PREFIX} ===== パッチチェック完了（DRY-RUN） ====="
    exit 0
fi

# --- パッチノート取得（L1: fetch-patch-notes.py） ---
echo "${LOG_PREFIX} INFO: パッチノート取得中..."
if ! python3 "${PROJECT_DIR}/scripts/fetch-patch-notes.py" "${LATEST}"; then
    notify_failure "fetch-patch-notes.py 失敗（パッチ${LATEST}）"
    exit 1
fi

if [ ! -f "${PROJECT_DIR}/patches/${LATEST}.md" ]; then
    notify_failure "patches/${LATEST}.md が生成されていない"
    exit 1
fi

# --- ガイド更新（L3: Claude） ---
echo "${LOG_PREFIX} INFO: ガイド更新中..."
json=$(run_cmd "update-guides") || { notify_failure "update-guides 失敗"; exit 1; }
if [ -z "$json" ]; then
    notify_failure "update-guides 結果が空"
    exit 1
fi

if ! dispatch_ops "$json"; then
    notify_failure "update-guides dispatch_ops 失敗"
    exit 1
fi

# --- パッチバージョンを更新 ---
echo "${LATEST}" > "${PATCH_FILE}"
echo "${LOG_PREFIX} INFO: current-patch.txt を ${LATEST} に更新"

# --- git push ---
git add .
git -c user.name="lol-guides-jp" -c user.email="lol-guides-jp@users.noreply.github.com" \
    commit -m "[自動] パッチ${LATEST} ガイド更新"
git push origin main

# CLAUDE.local.md に成功通知
grep -v "lol-guides-jp check-patch" "${CLAUDE_LOCAL}" > "${CLAUDE_LOCAL}.tmp" && mv "${CLAUDE_LOCAL}.tmp" "${CLAUDE_LOCAL}" || true
echo "- ${DATE} lol-guides-jp: パッチ${LATEST} ガイド更新完了 → lol-guides-jp/champions/ を確認" >> "${CLAUDE_LOCAL}"

echo "${LOG_PREFIX} ===== パッチチェック完了 ====="
