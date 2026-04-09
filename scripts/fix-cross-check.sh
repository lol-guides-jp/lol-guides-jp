#!/bin/bash
# fix-cross-check.sh
# 指定された対面ペアについて cross-check-matchup を実行し、矛盾を修正する。
# add-matchups.sh から呼び出されるか、単体で使用する。
#
# 使い方:
#   ./scripts/fix-cross-check.sh <champ_id> <champ_ja> <opp_id> <opp_ja> <opp_en>
#
# 終了コード:
#   0: ok / fixed（修正済み）
#   1: エラー
#   2: needs_review（cross-check-review.log に記録済み）

set -euo pipefail

export NVM_DIR="/home/ojita/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
DATE=$(date +%Y-%m-%d)
LOG_PREFIX="[${DATE} $(date +%H:%M:%S)]"
REVIEW_LOG="${PROJECT_DIR}/scripts/cross-check-review.log"
CLAUDE_LOCAL="/home/ojita/lol-guides-jp/CLAUDE.local.md"

source "${PROJECT_DIR}/scripts/lib.sh"

champ_id="$1"
champ_ja="$2"
opp_id="$3"
opp_ja="$4"
opp_en="$5"

matchup_a="${PROJECT_DIR}/champions/${champ_id}/matchups.md"
matchup_b="${PROJECT_DIR}/champions/${opp_id}/matchups.md"

# --- 両エントリが存在するか確認 ---
if [ ! -f "$matchup_a" ] || ! grep -q "^## vs ${opp_ja}" "$matchup_a"; then
    echo "${LOG_PREFIX} SKIP: ${champ_ja}/matchups.md に vs ${opp_ja} が存在しない"
    exit 0
fi
if [ ! -f "$matchup_b" ] || ! grep -q "^## vs ${champ_ja}" "$matchup_b"; then
    echo "${LOG_PREFIX} SKIP: ${opp_ja}/matchups.md に vs ${champ_ja} が存在しない"
    exit 0
fi

# --- エントリを抽出（## vs X から次の ## vs まで） ---
# header は前方一致で検索する（「## vs アーゴット」が「## vs アーゴット（Urgot）」にもマッチ）
extract_entry() {
    local file="$1"
    local header="$2"
    python3 -c "
import sys
lines = open('$file').read().splitlines()
in_section = False
result = []
for line in lines:
    if line.startswith('## vs ') and in_section:
        break
    if line.startswith('$header'):
        in_section = True
    if in_section:
        result.append(line)
print('\n'.join(result))
"
}

entry_a=$(extract_entry "$matchup_a" "## vs ${opp_ja}（${opp_en}）")
entry_b=$(extract_entry "$matchup_b" "## vs ${champ_ja}")

if [ -z "$entry_a" ] || [ -z "$entry_b" ]; then
    echo "${LOG_PREFIX} SKIP: エントリ抽出失敗 (${champ_ja} vs ${opp_ja})"
    exit 0
fi

# --- DRY_RUN モード ---
if [ "${DRY_RUN:-0}" = "1" ]; then
    echo "${LOG_PREFIX} [DRY-RUN] cross-check-matchup をスキップ (${champ_ja} vs ${opp_ja})"
    exit 0
fi

# --- review_log に記録するヘルパー ---
log_review() {
    local label="$1"
    local issue="$2"
    echo "${LOG_PREFIX} ${label}: ${champ_ja} vs ${opp_ja} — ${issue}"
    echo "[${DATE}] ${label}: ${champ_ja} vs ${opp_ja} — ${issue}" >> "${REVIEW_LOG}"
}

run_cross_check() {
    local args="${champ_id}|${champ_ja}|${opp_id}|${opp_ja}|${entry_a}|${entry_b}"
    run_cmd "cross-check-matchup" "$args"
}

# --- 1回目チェック ---
result=$(run_cross_check) || {
    echo "${LOG_PREFIX} ERROR: cross-check-matchup 失敗 (${champ_ja} vs ${opp_ja})"
    exit 1
}
if [ -z "$result" ]; then
    echo "${LOG_PREFIX} ERROR: cross-check 結果が空 (${champ_ja} vs ${opp_ja})"
    exit 1
fi

status=$(echo "$result" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('status', 'error'))
except json.JSONDecodeError:
    print('error')
") || { echo "${LOG_PREFIX} ERROR: cross-check JSON解析失敗 (${champ_ja} vs ${opp_ja})"; exit 1; }

if [ "$status" = "error" ]; then
    echo "${LOG_PREFIX} ERROR: cross-check 無効なJSON (${champ_ja} vs ${opp_ja})"
    exit 1
fi

if [ "$status" = "ok" ]; then
    echo "${LOG_PREFIX} OK: 整合性問題なし (${champ_ja} vs ${opp_ja})"
    exit 0
fi

if [ "$status" = "needs_review" ]; then
    issue=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('issue',''))")
    log_review "NEEDS_REVIEW" "$issue"
    exit 2
fi

if [ "$status" = "fixed" ]; then
    fix_side=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('fix_side',''))")
    fix_entry=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('fix_entry',''))")
    issue=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('issue',''))")

    if [ "$fix_side" = "a" ]; then
        target_file="$matchup_a"
        target_header="## vs ${opp_ja}"
    else
        target_file="$matchup_b"
        target_header="## vs ${champ_ja}"
    fi

    # セクション置換
    python3 -c "
import sys
content = open('${target_file}').read()
lines = content.splitlines(keepends=True)
result = []
skip = False
for line in lines:
    if line.rstrip() == '${target_header}' or line.startswith('${target_header}（'):
        skip = True
        result.append('${fix_entry}\n')
        continue
    if skip and line.startswith('## vs '):
        skip = False
    if not skip:
        result.append(line)
open('${target_file}', 'w').write(''.join(result))
"
    echo "${LOG_PREFIX} FIXED: ${champ_ja} vs ${opp_ja} (fix_side=${fix_side}) — ${issue}"

    # --- 1回リトライ: 修正後に再チェック ---
    entry_a=$(extract_entry "$matchup_a" "## vs ${opp_ja}（${opp_en}）")
    entry_b=$(extract_entry "$matchup_b" "## vs ${champ_ja}")

    result2=$(run_cross_check) || {
        echo "${LOG_PREFIX} WARN: リトライチェック失敗 (${champ_ja} vs ${opp_ja})"
        exit 0
    }
    status2=$(echo "$result2" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','error'))" 2>/dev/null || echo "error")

    if [ "$status2" != "ok" ]; then
        issue2=$(echo "$result2" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('issue','リトライ後も不整合'))" 2>/dev/null || echo "リトライ後も不整合")
        log_review "RETRY_EXCEEDED" "$issue2"
        # リトライ超過はCLAUDE.local.mdにサマリを書く（件数のみ）
        python3 -c "
count_line = '[cross-check リトライ超過あり]'
content = open('${CLAUDE_LOCAL}').read()
if count_line not in content:
    marker = '## タスク（未完了）'
    if marker in content:
        content = content.replace(marker, marker + '\n- ' + count_line + ' → scripts/cross-check-review.log を参照\n', 1)
        open('${CLAUDE_LOCAL}', 'w').write(content)
"
        exit 2
    fi

    echo "${LOG_PREFIX} OK: リトライ後に整合性確認 (${champ_ja} vs ${opp_ja})"
    exit 0
fi

echo "${LOG_PREFIX} ERROR: 不明なステータス: ${status}"
exit 1
