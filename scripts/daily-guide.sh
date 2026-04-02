#!/bin/bash
# daily-guide.sh
# 毎日4時: TODO.mdの先頭チャンピオンのガイドを1体生成してpush
#
# cron登録:
#   0 4 * * 1-6 /home/ojita/lol-guides-jp/scripts/daily-guide.sh >> /home/ojita/lol-guides-jp/scripts/cron.log 2>&1

set -euo pipefail

export NVM_DIR="/home/ojita/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
DATE=$(date +%Y-%m-%d)
LOG_PREFIX="[${DATE} $(date +%H:%M:%S)]"

source "${PROJECT_DIR}/scripts/lib.sh"

# --- 予算サーキットブレーカー（月額$50超過でcron停止） ---
BUDGET_LIMIT=50.00
COST_SCRIPT="${HOME}/.claude/scripts/cost-report.py"
if [ -f "$COST_SCRIPT" ]; then
    if ! python3 "$COST_SCRIPT" --budget-check "$BUDGET_LIMIT" > /dev/null 2>&1; then
        echo "${LOG_PREFIX} ERROR: 月額予算超過（\$${BUDGET_LIMIT}）。ガイド生成停止"
        exit 1
    fi
fi

cd "$PROJECT_DIR" || { echo "${LOG_PREFIX} ERROR: ディレクトリが見つかりません"; exit 1; }

# 未完了チャンピオンが残っているか確認
PENDING=$(grep -c '^\- \[ \]' TODO.md 2>/dev/null || echo 0)
if [ "$PENDING" -eq 0 ]; then
    echo "${LOG_PREFIX} INFO: TODO.mdに未完了チャンピオンなし。スキップします"
    exit 0
fi

echo "${LOG_PREFIX} ===== LoL ガイド生成開始（残り${PENDING}体） ====="

BEFORE_COUNT=$(find "${PROJECT_DIR}/champions" -name "guide.md" | wc -l)

if ! run_cmd "write-guide"; then
    echo "${LOG_PREFIX} ERROR: ガイド生成失敗"
    exit 1
fi

AFTER_COUNT=$(find "${PROJECT_DIR}/champions" -name "guide.md" | wc -l)
if [ "${BEFORE_COUNT}" = "${AFTER_COUNT}" ]; then
    echo "${LOG_PREFIX} ERROR: write-guideはexit 0だがガイドが増えていない"
    exit 1
fi

# git push
git add . 2>&1
git -c user.name="lol-guides-jp" -c user.email="lol-guides-jp@users.noreply.github.com" \
    commit -m "[自動] ${DATE} ガイド追加" 2>&1
git push origin main 2>&1

echo "${LOG_PREFIX} ===== 完了 ====="
