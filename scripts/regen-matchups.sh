#!/bin/bash
# regen-matchups.sh
# scan-broken.py の broken / quality エントリを再生成する
#
# 処理方式:
#   broken  — research-matchup → write-matchup → replace-section（フル再生成）
#   quality — build-rewrite-input.py → rewrite-matchup → replace-section（スキル名追加のみ）
#
# 使い方:
#   ./scripts/regen-matchups.sh [--tier broken|quality|all] [--batch N] [--dry-run]
#
# デフォルト: --tier all --batch 3

set -euo pipefail

export NVM_DIR="/home/ojita/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
DATE=$(date +%Y-%m-%d)
LOG_PREFIX="[${DATE} $(date +%H:%M:%S)]"

source "${PROJECT_DIR}/scripts/lib.sh"

# --- 引数解析 ---
TIER="all"    # broken | quality | all
BATCH=3
DRY_RUN=0
SLEEP=0       # ジョブ間のsleep秒数

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tier)   TIER="$2";  shift 2 ;;
        --batch)  BATCH="$2"; shift 2 ;;
        --sleep)  SLEEP="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

export DRY_RUN

cd "$PROJECT_DIR"

echo "${LOG_PREFIX} ===== regen-matchups 開始 (tier=${TIER}, batch=${BATCH}) ====="

# --- scan-broken.py から対象エントリを取得（broken を quality より先に処理）---
mapfile -t JOBS < <(
    python3 scripts/scan-broken.py --tsv 2>/dev/null \
    | python3 scripts/list-regen-targets.py --tier "$TIER" --batch "$BATCH"
)

if [ ${#JOBS[@]} -eq 0 ]; then
    echo "${LOG_PREFIX} INFO: 対象エントリなし。終了"
    exit 0
fi

echo "${LOG_PREFIX} INFO: ${#JOBS[@]} 件処理します"

# --- data.json からチャンプ情報を取得するヘルパー ---
get_champ_info() {
    local cid="$1"
    python3 -c "
import json, sys
data = json.load(open('${PROJECT_DIR}/docs/data.json'))
cmap = {c['id']:c for c in data['champions']}
c = cmap.get('$cid', {})
print(c.get('ja',''), c.get('en',''))
"
}

get_skills_str() {
    local cid="$1"
    python3 -c "
import json
data = json.load(open('${PROJECT_DIR}/docs/data.json'))
cmap = {c['id']:c for c in data['champions']}
c = cmap.get('$cid', {})
parts = []
for s in c.get('skills', []):
    if s['key'] in 'PQWER':
        name = s['name'].split('/')[0].strip()
        parts.append(f\"{s['key']}:{name}\")
print(','.join(parts))
"
}

# --- メイン処理 ---
PROCESSED=0
FAILED=0

for job in "${JOBS[@]}"; do
    IFS=$'\t' read -r champ_id opp_id opp_ja tier reasons <<< "$job"

    # champ_ja / opp_en を data.json から補完
    read -r champ_ja _  < <(get_champ_info "$champ_id")
    read -r _  opp_en   < <(get_champ_info "$opp_id")

    # opp_en が取れない場合（opp_id 不明）はスキップ
    if [ -z "$opp_en" ]; then
        echo "${LOG_PREFIX} SKIP: opp_en 不明 (${champ_id} vs ${opp_ja}, opp_id=${opp_id})"
        FAILED=$((FAILED + 1))
        continue
    fi

    echo "${LOG_PREFIX} INFO: [${tier}] ${champ_ja} vs ${opp_ja} ..."

    champ_skills=$(get_skills_str "$champ_id")
    opp_skills=$(get_skills_str "$opp_id")

    if [ "$tier" = "broken" ]; then
        # --- フル再生成: research → write → replace ---

        # 既存エントリの type/summary を guide.md から取得（なければ空）
        type_hint=$(python3 -c "
import re, os
path = '${PROJECT_DIR}/champions/${champ_id}/guide.md'
if not os.path.isfile(path):
    print('苦手')
    exit()
content = open(path).read()
fav, unfav = set(), set()
cur = None
for line in content.splitlines():
    if '得意マッチアップ' in line: cur = 'fav'
    elif '苦手マッチアップ' in line: cur = 'unfav'
    elif line.startswith('## '): cur = None
    elif cur and line.startswith('- **'):
        m = re.match(r'- \*\*(.+?)\*\*', line)
        if m:
            (fav if cur=='fav' else unfav).add(m.group(1))
if '${opp_ja}' in fav: print('得意')
elif '${opp_ja}' in unfav: print('苦手')
else: print('五分')
" 2>/dev/null || echo "五分")

        args="${champ_id}|${champ_ja}|${opp_id}|${opp_ja}|${opp_en}|${type_hint}||${champ_skills}|${opp_skills}"

        research_json=$(run_cmd "research-matchup" "$args") || {
            echo "${LOG_PREFIX} ERROR: research-matchup 失敗 (${champ_ja} vs ${opp_ja})"
            FAILED=$((FAILED + 1))
            continue
        }
        if [ -z "$research_json" ]; then
            echo "${LOG_PREFIX} ERROR: research 結果が空 (${champ_ja} vs ${opp_ja})"
            FAILED=$((FAILED + 1))
            continue
        fi
        # リスト形式で返ってきた場合はunwrap（空リストはスキップ）
        if echo "$research_json" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if isinstance(d,list) and len(d)>0 else 1)" 2>/dev/null; then
            research_json=$(echo "$research_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d[0]))")
        fi

        ops_json=$(run_cmd "write-matchup" "$research_json") || {
            echo "${LOG_PREFIX} ERROR: write-matchup 失敗 (${champ_ja} vs ${opp_ja})"
            FAILED=$((FAILED + 1))
            continue
        }

    else
        # --- リライト: 既存body + スキル名注入 → replace ---

        rewrite_input=$(python3 scripts/build-rewrite-input.py \
            "$champ_id" "$champ_ja" "$opp_id" "$opp_ja" "$opp_en" \
            "$champ_skills" "$opp_skills" 2>&1) || {
            echo "${LOG_PREFIX} ERROR: build-rewrite-input 失敗 (${champ_ja} vs ${opp_ja}): ${rewrite_input}"
            FAILED=$((FAILED + 1))
            continue
        }

        ops_json=$(run_cmd "rewrite-matchup" "$rewrite_input") || {
            echo "${LOG_PREFIX} ERROR: rewrite-matchup 失敗 (${champ_ja} vs ${opp_ja})"
            FAILED=$((FAILED + 1))
            continue
        }
    fi

    if [ -z "$ops_json" ]; then
        echo "${LOG_PREFIX} ERROR: ops_json が空 (${champ_ja} vs ${opp_ja})"
        FAILED=$((FAILED + 1))
        continue
    fi

    # --- セクション置換 ---
    if [ "$DRY_RUN" = "1" ]; then
        echo "${LOG_PREFIX} [DRY-RUN] replace-section をスキップ (ops_json長=${#ops_json})"
    else
        echo "$ops_json" | python3 scripts/replace-section.py "$champ_id" "$opp_ja" "$opp_en" || {
            echo "${LOG_PREFIX} ERROR: replace-section 失敗 (${champ_ja} vs ${opp_ja})"
            FAILED=$((FAILED + 1))
            continue
        }
    fi

    echo "${LOG_PREFIX} OK: ${champ_ja} vs ${opp_ja} [${tier}] 完了"
    PROCESSED=$((PROCESSED + 1))

    if [ "$SLEEP" -gt 0 ] && [ "$PROCESSED" -lt "${#JOBS[@]}" ]; then
        echo "${LOG_PREFIX} INFO: ${SLEEP}秒 sleep..."
        sleep "$SLEEP"
    fi
done

echo "${LOG_PREFIX} ===== 完了: 成功=${PROCESSED} 失敗=${FAILED} ====="

# --- post-processing ---
if [ "$DRY_RUN" = "0" ] && [ "$PROCESSED" -gt 0 ]; then
    git -C "$PROJECT_DIR" add champions/*/matchups.md

    # 変更がなければスキップ
    if git -C "$PROJECT_DIR" diff --cached --quiet; then
        echo "${LOG_PREFIX} INFO: matchups.md に変更なし（コミットスキップ）"
        exit 0
    fi

    git -C "$PROJECT_DIR" commit -m "fix: 対面ガイド ${PROCESSED}件再生成 (tier=${TIER})"
    echo "${LOG_PREFIX} INFO: git commit 完了"

    # guide.md 得意/苦手を同期
    echo "${LOG_PREFIX} INFO: fix-guide-matchups.py 実行中..."
    python3 "${PROJECT_DIR}/scripts/fix-guide-matchups.py" --all >> "${PROJECT_DIR}/scripts/cron.log" 2>&1
    git -C "$PROJECT_DIR" add champions/*/guide.md
    git -C "$PROJECT_DIR" diff --cached --quiet || \
        git -C "$PROJECT_DIR" commit -m "fix: guide.md 得意/苦手 同期 (regen後)"

    # data.json 再ビルド
    echo "${LOG_PREFIX} INFO: data.json 再ビルド中..."
    node "${PROJECT_DIR}/scripts/build-json.js" >> "${PROJECT_DIR}/scripts/cron.log" 2>&1
    git -C "$PROJECT_DIR" add docs/data.json
    git -C "$PROJECT_DIR" diff --cached --quiet || \
        git -C "$PROJECT_DIR" commit -m "chore: data.json 再ビルド (regen後)"

    echo "${LOG_PREFIX} INFO: push 中..."
    git -C "$PROJECT_DIR" push
    echo "${LOG_PREFIX} INFO: push 完了"
fi
