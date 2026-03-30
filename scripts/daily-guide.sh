#!/bin/bash
# daily-guide.sh
# 毎日4時: TODO.mdの先頭チャンピオンのガイドを1体生成してpush
#
# cron登録:
#   0 4 * * * /mnt/c/Users/ojita/lol-guides-jp/scripts/daily-guide.sh >> /mnt/c/Users/ojita/lol-guides-jp/scripts/cron.log 2>&1

export NVM_DIR="/home/ojita/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

GUIDE_DIR="/mnt/c/Users/ojita/lol-guides-jp"
DATE=$(date +%Y-%m-%d)
LOG_PREFIX="[${DATE} $(date +%H:%M:%S)]"

source "${GUIDE_DIR}/scripts/lib.sh"

cd "$GUIDE_DIR" || { echo "${LOG_PREFIX} ERROR: ディレクトリが見つかりません"; exit 1; }

# 未完了チャンピオンが残っているか確認
PENDING=$(grep -c '^\- \[ \]' TODO.md 2>/dev/null || echo 0)
if [ "$PENDING" -eq 0 ]; then
    echo "${LOG_PREFIX} INFO: TODO.mdに未完了チャンピオンなし。スキップします"
    exit 0
fi

echo "${LOG_PREFIX} ===== LoL ガイド生成開始（残り${PENDING}体）====="

run_cmd "write-guide"
if [ $? -ne 0 ]; then
    echo "${LOG_PREFIX} ERROR: ガイド生成失敗"
    exit 1
fi

# git push
git.exe -C 'C:\Users\ojita\lol-guides-jp' add . 2>&1
git.exe -C 'C:\Users\ojita\lol-guides-jp' \
    -c user.name="ojita" \
    -c user.email="ojita@users.noreply.github.com" \
    commit -m "[自動] ${DATE} ガイド追加" 2>&1
git.exe -C 'C:\Users\ojita\lol-guides-jp' push origin main 2>&1

echo "${LOG_PREFIX} ===== 完了 ====="
