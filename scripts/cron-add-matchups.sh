#!/bin/bash
# cron-add-matchups.sh
# 毎日0時に対面ガイドを自動追加する（Gemini 3.1 Flash Lite + Sonnet レビュー）
#
# cron登録:
#   0 0 * * * /home/ojita/lol-guides-jp/scripts/cron-add-matchups.sh >> /home/ojita/lol-guides-jp/scripts/cron.log 2>&1

set -euo pipefail

export NVM_DIR="/home/ojita/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
LOCK_FILE="/tmp/lol-guides-add-matchups.lock"
DATE=$(date +%Y-%m-%d)
LOG_PREFIX="[${DATE} $(date +%H:%M:%S)]"

# 重複実行防止
if [ -f "$LOCK_FILE" ]; then
    echo "${LOG_PREFIX} INFO: 前回の実行が残っているためスキップ"
    exit 0
fi
touch "$LOCK_FILE"
trap "rm -f '${LOCK_FILE}'" EXIT

cd "$PROJECT_DIR"

echo "${LOG_PREFIX} ===== cron-add-matchups 起動 ====="
"${PROJECT_DIR}/scripts/add-matchups.sh" --batch 200 --sleep 4 2>&1 | tee /tmp/add-matchups-last.log
echo "${LOG_PREFIX} ===== cron-add-matchups 終了 ====="

# 実行結果をCLAUDE.local.mdに記録
SUMMARY=$(grep "完了: 成功=" /tmp/add-matchups-last.log | tail -1 || echo "完了行なし")
echo "- [$(date '+%Y-%m-%d %H:%M')] lol-guides-jp: cron-add-matchups ${SUMMARY}" \
    >> /home/ojita/CLAUDE.local.md
