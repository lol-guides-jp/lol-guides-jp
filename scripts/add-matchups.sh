#!/bin/bash
# add-matchups.sh
# missing-*.txt から未対面を取り出し、research → write → append のパイプラインで追加する
#
# 使い方:
#   ./scripts/add-matchups.sh [--role トップ|ミッド|ジャング|ADC|サポート] [--batch N] [--dry-run]
#
# デフォルト: 全ロールから最大3件処理

set -euo pipefail

export NVM_DIR="/home/ojita/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
DATE=$(date +%Y-%m-%d)
LOG_PREFIX="[${DATE} $(date +%H:%M:%S)]"

source "${PROJECT_DIR}/scripts/lib.sh"

# --- 引数解析 ---
ROLE=""
BATCH=3
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --role) ROLE="$2"; shift 2 ;;
        --batch) BATCH="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

export DRY_RUN

cd "$PROJECT_DIR"

echo "${LOG_PREFIX} ===== add-matchups 開始 (batch=${BATCH}, role=${ROLE:-全て}) ====="

# --- 対象ファイルを決定 ---
if [ -n "$ROLE" ]; then
    MISSING_FILES=("scripts/missing-${ROLE}.txt")
else
    MISSING_FILES=(scripts/missing-トップ.txt scripts/missing-ミッド.txt scripts/missing-ジャング.txt scripts/missing-ADC.txt scripts/missing-サポート.txt)
fi

# --- missing から最大 BATCH 件取り出す ---
JOBS=()
for f in "${MISSING_FILES[@]}"; do
    [ -f "$f" ] || continue
    while IFS= read -r line && [ ${#JOBS[@]} -lt "$BATCH" ]; do
        [ -z "$line" ] && continue
        JOBS+=("$line|$f")
    done < "$f"
done

if [ ${#JOBS[@]} -eq 0 ]; then
    echo "${LOG_PREFIX} INFO: 未対面なし。終了"
    exit 0
fi

echo "${LOG_PREFIX} INFO: ${#JOBS[@]} 件処理します"

# --- 各ジョブを処理 ---
PROCESSED=0
FAILED=0

for job in "${JOBS[@]}"; do
    # フィールド分解: champ_id|champ_ja|opp_id|opp_ja|opp_en|type|summary|source_file
    IFS='|' read -r champ_id champ_ja opp_id opp_ja opp_en type summary source_file <<< "$job"
    args="${champ_id}|${champ_ja}|${opp_id}|${opp_ja}|${opp_en}|${type}|${summary}"

    echo "${LOG_PREFIX} INFO: ${champ_ja} vs ${opp_ja} (${type}) ..."

    # --- 重複チェック ---
    matchup_file="${PROJECT_DIR}/champions/${champ_id}/matchups.md"
    if [ -f "$matchup_file" ] && grep -q "^## vs ${opp_ja}" "$matchup_file"; then
        echo "${LOG_PREFIX} SKIP: ${champ_ja} vs ${opp_ja} は既に存在"
        # missing から削除
        if [ "$DRY_RUN" = "0" ]; then
            python3 -c "
import sys
lines = open('${source_file}').read().splitlines()
lines = [l for l in lines if not l.startswith('${champ_id}|') or '|${opp_id}|' not in l]
open('${source_file}', 'w').write('\n'.join(lines) + ('\n' if lines else ''))
"
        fi
        continue
    fi

    # --- スキル名を data.json から抽出して引数に付加 ---
    read -r champ_skills opp_skills < <(python3 - << PYEOF
import json
data = json.load(open("${PROJECT_DIR}/docs/data.json"))
cmap = {c["id"]: c for c in data["champions"]}
def skills_str(cid):
    c = cmap.get(cid, {})
    parts = []
    for s in c.get("skills", []):
        if s["key"] in "PQWER":
            name = s["name"].split("/")[0].strip()
            parts.append(f"{s['key']}:{name}")
    return ",".join(parts)
print(skills_str("${champ_id}"), skills_str("${opp_id}"))
PYEOF
)
    args="${champ_id}|${champ_ja}|${opp_id}|${opp_ja}|${opp_en}|${type}|${summary}|${champ_skills}|${opp_skills}"

    # --- L3-research: WebSearch で対面情報収集 ---
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

    # research がリスト形式 [{...}] で返ってきた場合はunwrap
    if echo "$research_json" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if isinstance(d,list) else 1)" 2>/dev/null; then
        research_json=$(echo "$research_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d[0]))")
    fi

    # --- L3-write: matchups.md フォーマットに整形 ---
    ops_json=$(run_cmd "write-matchup" "$research_json") || {
        echo "${LOG_PREFIX} ERROR: write-matchup 失敗 (${champ_ja} vs ${opp_ja})"
        FAILED=$((FAILED + 1))
        continue
    }
    if [ -z "$ops_json" ]; then
        echo "${LOG_PREFIX} ERROR: write 結果が空 (${champ_ja} vs ${opp_ja})"
        FAILED=$((FAILED + 1))
        continue
    fi

    # --- L1: dispatch_ops でファイルに追記 ---
    if [ "$DRY_RUN" = "1" ]; then
        echo "${LOG_PREFIX} [DRY-RUN] dispatch_ops をスキップ"
        echo "$ops_json"
    else
        dispatch_ops "$ops_json" || {
            echo "${LOG_PREFIX} ERROR: dispatch_ops 失敗 (${champ_ja} vs ${opp_ja})"
            FAILED=$((FAILED + 1))
            continue
        }

        # missing から処理済み行を削除
        python3 -c "
lines = open('${source_file}').read().splitlines()
lines = [l for l in lines if not l.startswith('${champ_id}|') or '|${opp_id}|' not in l]
open('${source_file}', 'w').write('\n'.join(lines) + ('\n' if lines else ''))
"

        # --- 相手側エントリとの整合性チェック ---
        bash "${PROJECT_DIR}/scripts/fix-cross-check.sh" \
            "$champ_id" "$champ_ja" "$opp_id" "$opp_ja" "$opp_en" || true
    fi

    echo "${LOG_PREFIX} OK: ${champ_ja} vs ${opp_ja} 追加完了"
    PROCESSED=$((PROCESSED + 1))
done

echo "${LOG_PREFIX} ===== 完了: 成功=${PROCESSED} 失敗=${FAILED} ====="

# git commit → quality-fix → build-json → push
if [ "$DRY_RUN" = "0" ] && [ "$PROCESSED" -gt 0 ]; then
    git -C "$PROJECT_DIR" add champions/*/matchups.md
    git -C "$PROJECT_DIR" commit -m "feat: 対面ガイド ${PROCESSED}件追加 (自動生成)"
    echo "${LOG_PREFIX} INFO: git commit 完了"

    # 表記揺れ・日英混在を修正
    echo "${LOG_PREFIX} INFO: quality-fix 実行中..."
    python3 "${PROJECT_DIR}/scripts/quality-fix.py" >> "${PROJECT_DIR}/scripts/cron.log" 2>&1
    git -C "$PROJECT_DIR" add champions/*/matchups.md
    # 変更があればコミット
    git -C "$PROJECT_DIR" diff --cached --quiet || \
        git -C "$PROJECT_DIR" commit -m "fix: 対面ガイド 表記揺れ・日英混在修正 (自動)"

    # data.json 再ビルド
    echo "${LOG_PREFIX} INFO: data.json 再ビルド中..."
    node "${PROJECT_DIR}/scripts/build-json.js" >> "${PROJECT_DIR}/scripts/cron.log" 2>&1
    git -C "$PROJECT_DIR" add docs/data.json
    git -C "$PROJECT_DIR" diff --cached --quiet || \
        git -C "$PROJECT_DIR" commit -m "chore: data.json 再ビルド (対面ガイド追加後)"

    # push
    echo "${LOG_PREFIX} INFO: push 中..."
    git -C "$PROJECT_DIR" push
    echo "${LOG_PREFIX} INFO: push 完了"
fi
