#!/bin/bash
# add-matchups.sh
# missing-*.txt から未対面を取り出し、Gemini 生成 → lint → Sonnet レビュー のパイプラインで追加する
#
# 使い方:
#   ./scripts/add-matchups.sh [--role トップ|ミッド|ジャング|ADC|サポート] [--batch N] [--sleep N] [--dry-run]
#
# デフォルト: 全ロールから最大3件処理、sleep 4秒（RPM 15 対策）

set -euo pipefail

export NVM_DIR="/home/ojita/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
log_prefix() { echo "[$(date '+%Y-%m-%d %H:%M:%S')]"; }

source "${PROJECT_DIR}/scripts/lib.sh"

# --- 終了時コミット（正常終了・503中断どちらでも PROCESSED > 0 なら実行） ---
# coding-standards.md §8 に従い auto_commit / auto_push を使う。
# 3段コミット: 新規追加 → 表記揺れ同期 → data.json 再ビルド。
# 各段は auto_commit の冪等性（変更なし→skip）に任せる。
_commit_if_processed() {
    [ "$DRY_RUN" = "0" ] && [ "$PROCESSED" -gt 0 ] || return 0

    auto_commit champions/*/matchups.md \
        -- "feat: 対面ガイド ${PROCESSED}件追加 (自動生成)"

    echo "$(log_prefix) INFO: quality-fix 実行中..."
    python3 "${PROJECT_DIR}/scripts/quality-fix.py" >> "${PROJECT_DIR}/scripts/cron.log" 2>&1

    echo "$(log_prefix) INFO: guide.md 得意/苦手 同期中..."
    python3 "${PROJECT_DIR}/scripts/fix-guide-matchups.py" --all >> "${PROJECT_DIR}/scripts/cron.log" 2>&1
    auto_commit champions/*/matchups.md champions/*/guide.md \
        -- "fix: 対面ガイド 表記揺れ・得意苦手同期 (自動)"

    echo "$(log_prefix) INFO: data.json 再ビルド中..."
    node "${PROJECT_DIR}/scripts/build-json.js" >> "${PROJECT_DIR}/scripts/cron.log" 2>&1
    auto_commit docs/data.json \
        -- "chore: data.json 再ビルド (対面ガイド追加後)"

    echo "$(log_prefix) INFO: push 中..."
    auto_push || echo "$(log_prefix) WARN: push 失敗（trap EXIT 内のため継続）"
}
trap '_commit_if_processed' EXIT

# --- 引数解析 ---
ROLE=""
BATCH=3
DRY_RUN=0
FORCE=0  # 1 = 既存エントリでもスキップせず再生成（両方向再生成用）

SLEEP=4  # API コール間の sleep 秒数（RPM 15 対策）

while [[ $# -gt 0 ]]; do
    case "$1" in
        --role)    ROLE="$2";    shift 2 ;;
        --batch)   BATCH="$2";   shift 2 ;;
        --sleep)   SLEEP="$2";   shift 2 ;;
        --force)   FORCE=1;      shift ;;
        --dry-run) DRY_RUN=1;    shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

export DRY_RUN

cd "$PROJECT_DIR"

echo "$(log_prefix) ===== add-matchups 開始 (batch=${BATCH}, role=${ROLE:-全て}, sleep=${SLEEP}s) ====="

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
    echo "$(log_prefix) INFO: 未対面なし。終了"
    exit 0
fi

echo "$(log_prefix) INFO: ${#JOBS[@]} 件処理します"

# --- 各ジョブを処理 ---
PROCESSED=0
FAILED=0
_ITER=0
SONNET_FAIL_STREAK=0

for job in "${JOBS[@]}"; do
    if [ "$_ITER" -gt 0 ] && [ "$SLEEP" -gt 0 ]; then
        echo "$(log_prefix) INFO: ${SLEEP}秒 sleep..."
        sleep "$SLEEP"
    fi
    _ITER=$((_ITER + 1))

    # フィールド分解: champ_id|champ_ja|opp_id|opp_ja|opp_en|type|summary|source_file
    IFS='|' read -r champ_id champ_ja opp_id opp_ja opp_en type summary source_file <<< "$job"

    echo "$(log_prefix) INFO: ${champ_ja} vs ${opp_ja} ..."

    # --- 重複チェック ---
    matchup_file="${PROJECT_DIR}/champions/${champ_id}/matchups.md"
    ENTRY_EXISTS=0
    if [ -f "$matchup_file" ] && grep -q "^## vs ${opp_ja}" "$matchup_file"; then
        ENTRY_EXISTS=1
    fi
    if [ "$ENTRY_EXISTS" = "1" ] && [ "$FORCE" = "0" ]; then
        echo "$(log_prefix) SKIP: ${champ_ja} vs ${opp_ja} は既に存在"
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
    [ "$ENTRY_EXISTS" = "1" ] && echo "$(log_prefix) INFO: ${champ_ja} vs ${opp_ja} を強制再生成 (--force)"

    # --- スキル名・英語名を data.json から抽出 ---
    champ_en=$(python3 -c "
import json
data = json.load(open('${PROJECT_DIR}/docs/data.json'))
cmap = {c['id']:c for c in data['champions']}
print(cmap.get('${champ_id}', {}).get('en', '${champ_id}'))
" 2>/dev/null || echo "$champ_id")

    opp_en_from_data=$(python3 -c "
import json
data = json.load(open('${PROJECT_DIR}/docs/data.json'))
cmap = {c['id']:c for c in data['champions']}
print(cmap.get('${opp_id}', {}).get('en', '${opp_en}'))
" 2>/dev/null || echo "$opp_en")

    # Lolalytics URL スラグ: ddragonKey.lower() を使う（en は空白・記号を含む場合があるため）
    # 例外: Wukong の ddragonKey は "MonkeyKing" だが Lolalytics URL は "wukong"。
    #       理由不明（Riot 内部の歴史的経緯と推測）。全 170 体を実測して確認済み（2026-04-14）。
    champ_slug=$(python3 -c "
import json
_OVERRIDE = {'monkeyking': 'wukong'}  # Wukong: ddragonKey=MonkeyKing だが Lolalytics は wukong
data = json.load(open('${PROJECT_DIR}/docs/data.json'))
cmap = {c['id']:c for c in data['champions']}
slug = cmap.get('${champ_id}', {}).get('ddragonKey', '${champ_id}').lower()
print(_OVERRIDE.get(slug, slug))
" 2>/dev/null || echo "$champ_id")

    opp_slug=$(python3 -c "
import json
_OVERRIDE = {'monkeyking': 'wukong'}  # Wukong: ddragonKey=MonkeyKing だが Lolalytics は wukong
data = json.load(open('${PROJECT_DIR}/docs/data.json'))
cmap = {c['id']:c for c in data['champions']}
slug = cmap.get('${opp_id}', {}).get('ddragonKey', '${opp_id}').lower()
print(_OVERRIDE.get(slug, slug))
" 2>/dev/null || echo "$opp_id")

    read -r champ_skills opp_skills < <(python3 - << PYEOF
import json
data = json.load(open("${PROJECT_DIR}/docs/data.json"))
cmap = {c["id"]: c for c in data["champions"]}
def skills_str(cid):
    c = cmap.get(cid, {})
    parts = []
    for s in c.get("skills", []):
        if s["key"] in "PQWER":
            parts.append(f"{s['key']}({s['name']})")
    return ", ".join(parts)
print(skills_str("${champ_id}"), skills_str("${opp_id}"))
PYEOF
)

    # --- 勝率取得 ---
    winrate=$(python3 "${PROJECT_DIR}/scripts/scrape-winrate.py" "$champ_slug" "$opp_slug") || {
        echo "$(log_prefix) WARN: winrate 取得失敗 → 50 で代替 (${champ_ja} vs ${opp_ja})"
        winrate="50"
    }
    if [ -z "$winrate" ]; then
        echo "$(log_prefix) WARN: winrate が空 → 50 で代替"
        winrate="50"
    fi
    winrate_b=$(python3 -c "print(round(100 - float('${winrate}'), 1))")

    # --- Gemini 生成 A 側 ---
    args_a="${champ_id}|${champ_ja}|${champ_en}|${opp_id}|${opp_ja}|${opp_en_from_data}||${winrate}|${champ_skills}|${opp_skills}"

    entry_a=$(python3 "${PROJECT_DIR}/scripts/call-gemini.py" "$args_a") || {
        ec=$?
        if [ $ec -eq 2 ]; then
            echo "$(log_prefix) ERROR: Gemini RPD上限に達した。バッチを中断 (${champ_ja} vs ${opp_ja})"
            exit 1
        fi
        if [ $ec -eq 3 ]; then
            echo "$(log_prefix) ERROR: Gemini 503。次のcronに委ねる (${champ_ja} vs ${opp_ja})"
            exit 1
        fi
        echo "$(log_prefix) ERROR: Gemini A 側失敗 (${champ_ja} vs ${opp_ja})"
        FAILED=$((FAILED + 1))
        continue
    }
    if [ -z "$entry_a" ]; then
        echo "$(log_prefix) ERROR: Gemini A 側が空 (${champ_ja} vs ${opp_ja})"
        FAILED=$((FAILED + 1))
        continue
    fi

    sleep "$SLEEP"

    # --- Gemini 生成 B 側 ---
    args_b="${opp_id}|${opp_ja}|${opp_en_from_data}|${champ_id}|${champ_ja}|${champ_en}||${winrate_b}|${opp_skills}|${champ_skills}"

    entry_b=$(python3 "${PROJECT_DIR}/scripts/call-gemini.py" "$args_b") || {
        ec=$?
        if [ $ec -eq 2 ]; then
            echo "$(log_prefix) ERROR: Gemini RPD上限に達した。バッチを中断 (${opp_ja} vs ${champ_ja})"
            exit 1
        fi
        if [ $ec -eq 3 ]; then
            echo "$(log_prefix) ERROR: Gemini 503。次のcronに委ねる (${opp_ja} vs ${champ_ja})"
            exit 1
        fi
        echo "$(log_prefix) ERROR: Gemini B 側失敗 (${opp_ja} vs ${champ_ja})"
        FAILED=$((FAILED + 1))
        continue
    }
    if [ -z "$entry_b" ]; then
        echo "$(log_prefix) ERROR: Gemini B 側が空 (${opp_ja} vs ${champ_ja})"
        FAILED=$((FAILED + 1))
        continue
    fi

    # --- L1 lint + 自動修正 ---
    # A側: OPP_SKILLS=対戦相手スキル / B側: OPP_SKILLS=メインチャンプスキル（視点が逆転するため）
    linted_a=$(echo "$entry_a" | OPP_SKILLS="$opp_skills" python3 "${PROJECT_DIR}/scripts/lint-matchup.py" --fix 2>/dev/null) || linted_a="$entry_a"
    linted_b=$(echo "$entry_b" | OPP_SKILLS="$champ_skills" python3 "${PROJECT_DIR}/scripts/lint-matchup.py" --fix 2>/dev/null) || linted_b="$entry_b"

    # --- DRY_RUN: review + 書き込みスキップ ---
    if [ "$DRY_RUN" = "1" ]; then
        echo "$(log_prefix) [DRY-RUN] A 側:"
        echo "$linted_a"
        echo ""
        echo "$(log_prefix) [DRY-RUN] B 側:"
        echo "$linted_b"
        echo "$(log_prefix) [DRY-RUN] review + ファイル書き込みスキップ"
        PROCESSED=$((PROCESSED + 1))
        continue
    fi

    # --- Sonnet レビュー ---
    review_input=$(CHAMP_ID="$champ_id" CHAMP_JA="$champ_ja" CHAMP_EN="$champ_en" \
        CHAMP_SKILLS="$champ_skills" OPP_ID="$opp_id" OPP_JA="$opp_ja" OPP_EN="$opp_en_from_data" \
        OPP_SKILLS="$opp_skills" ENTRY_A="$linted_a" ENTRY_B="$linted_b" \
        python3 -c "
import json, os
print(json.dumps({
    'champ_a': {
        'id': os.environ['CHAMP_ID'],
        'ja': os.environ['CHAMP_JA'],
        'en': os.environ['CHAMP_EN'],
        'skills': os.environ['CHAMP_SKILLS'],
        'entry': os.environ['ENTRY_A'],
    },
    'champ_b': {
        'id': os.environ['OPP_ID'],
        'ja': os.environ['OPP_JA'],
        'en': os.environ['OPP_EN'],
        'skills': os.environ['OPP_SKILLS'],
        'entry': os.environ['ENTRY_B'],
    }
}, ensure_ascii=False))
")

    review_result=$(run_cmd "review-matchup" "$review_input") || {
        SONNET_FAIL_STREAK=$((SONNET_FAIL_STREAK + 1))
        echo "$(log_prefix) ERROR: review-matchup 失敗 (${champ_ja} vs ${opp_ja}) [streak=${SONNET_FAIL_STREAK}]"
        FAILED=$((FAILED + 1))
        if [ "$SONNET_FAIL_STREAK" -ge 2 ]; then
            echo "$(log_prefix) INFO: Sonnet review 2件連続失敗 → spending limit と判断してバッチ終了"
            exit 0
        fi
        continue
    }
    if [ -z "$review_result" ]; then
        SONNET_FAIL_STREAK=$((SONNET_FAIL_STREAK + 1))
        echo "$(log_prefix) ERROR: review 結果が空 (${champ_ja} vs ${opp_ja}) [streak=${SONNET_FAIL_STREAK}]"
        FAILED=$((FAILED + 1))
        if [ "$SONNET_FAIL_STREAK" -ge 2 ]; then
            echo "$(log_prefix) INFO: Sonnet review 2件連続失敗 → spending limit と判断してバッチ終了"
            exit 0
        fi
        continue
    fi

    # --- レビュー結果パース ---
    review_status=$(echo "$review_result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || echo "")

    if [ "$review_status" = "approved" ]; then
        final_a=$(echo "$review_result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['entry_a'])")
        final_b=$(echo "$review_result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['entry_b'])")

    elif [ "$review_status" = "rejected" ]; then
        reject_reason=$(echo "$review_result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('reason','unknown'))" 2>/dev/null || echo "unknown")
        echo "$(log_prefix) WARN: rejected: ${reject_reason} (${champ_ja} vs ${opp_ja})"

        # --- リトライ（最大 2 回） ---
        RETRY_OK=0
        for retry_i in 1 2; do
            echo "$(log_prefix) INFO: リトライ ${retry_i}/2 (${champ_ja} vs ${opp_ja})"
            sleep "$SLEEP"

            retry_a=$(python3 "${PROJECT_DIR}/scripts/call-gemini.py" --feedback "$reject_reason" "$args_a") || {
                ec=$?
                if [ $ec -eq 3 ]; then
                    echo "$(log_prefix) ERROR: リトライ Gemini A 503。次のcronに委ねる"
                    exit 1
                fi
                echo "$(log_prefix) ERROR: リトライ Gemini A 失敗"
                continue
            }
            sleep "$SLEEP"
            retry_b=$(python3 "${PROJECT_DIR}/scripts/call-gemini.py" --feedback "$reject_reason" "$args_b") || {
                ec=$?
                if [ $ec -eq 3 ]; then
                    echo "$(log_prefix) ERROR: リトライ Gemini B 503。次のcronに委ねる"
                    exit 1
                fi
                echo "$(log_prefix) ERROR: リトライ Gemini B 失敗"
                continue
            }

            # lint
            retry_a=$(echo "$retry_a" | OPP_SKILLS="$opp_skills" python3 "${PROJECT_DIR}/scripts/lint-matchup.py" --fix 2>/dev/null) || true
            retry_b=$(echo "$retry_b" | OPP_SKILLS="$champ_skills" python3 "${PROJECT_DIR}/scripts/lint-matchup.py" --fix 2>/dev/null) || true

            # re-review
            retry_review_input=$(CHAMP_ID="$champ_id" CHAMP_JA="$champ_ja" CHAMP_EN="$champ_en" \
                CHAMP_SKILLS="$champ_skills" OPP_ID="$opp_id" OPP_JA="$opp_ja" OPP_EN="$opp_en_from_data" \
                OPP_SKILLS="$opp_skills" ENTRY_A="$retry_a" ENTRY_B="$retry_b" \
                python3 -c "
import json, os
print(json.dumps({
    'champ_a': {
        'id': os.environ['CHAMP_ID'],
        'ja': os.environ['CHAMP_JA'],
        'en': os.environ['CHAMP_EN'],
        'skills': os.environ['CHAMP_SKILLS'],
        'entry': os.environ['ENTRY_A'],
    },
    'champ_b': {
        'id': os.environ['OPP_ID'],
        'ja': os.environ['OPP_JA'],
        'en': os.environ['OPP_EN'],
        'skills': os.environ['OPP_SKILLS'],
        'entry': os.environ['ENTRY_B'],
    }
}, ensure_ascii=False))
")
            sleep "$SLEEP"
            retry_review=$(run_cmd "review-matchup" "$retry_review_input") || {
                echo "$(log_prefix) ERROR: リトライ review 失敗"
                continue
            }

            retry_status=$(echo "$retry_review" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || echo "")
            if [ "$retry_status" = "approved" ]; then
                final_a=$(echo "$retry_review" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['entry_a'])")
                final_b=$(echo "$retry_review" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['entry_b'])")
                RETRY_OK=1
                echo "$(log_prefix) INFO: リトライ ${retry_i} で approved"
                break
            else
                reject_reason=$(echo "$retry_review" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('reason','unknown'))" 2>/dev/null || echo "unknown")
                echo "$(log_prefix) WARN: リトライ ${retry_i} も rejected: ${reject_reason}"
            fi
        done

        if [ "$RETRY_OK" = "0" ]; then
            echo "$(log_prefix) ERROR: 2回リトライ後も rejected (${champ_ja} vs ${opp_ja})"
            echo "[$(date +%Y-%m-%d)] RETRY_FAILED: ${champ_ja} vs ${opp_ja} [${reject_reason}]" \
                >> "${PROJECT_DIR}/scripts/add-matchups-review.log"
            FAILED=$((FAILED + 1))
            continue
        fi
    else
        echo "$(log_prefix) ERROR: review パース失敗 (${champ_ja} vs ${opp_ja})"
        echo "$(log_prefix) DEBUG: review_result=${review_result:0:200}"
        FAILED=$((FAILED + 1))
        continue
    fi

    SONNET_FAIL_STREAK=0

    # --- ファイル書き込み ---
    # A 側
    if [ "$FORCE" = "1" ] && [ "$ENTRY_EXISTS" = "1" ]; then
        echo "$final_a" | python3 "${PROJECT_DIR}/scripts/replace-section-text.py" \
            "$champ_id" "$opp_ja" "$opp_en_from_data" || {
            echo "$(log_prefix) ERROR: A 側 replace 失敗 (${champ_ja} vs ${opp_ja})"
            FAILED=$((FAILED + 1))
            continue
        }
    else
        printf '\n%s\n' "$final_a" >> "$matchup_file"
        echo "$(log_prefix) INFO: A 側追記 → ${champ_id}/matchups.md"
    fi

    # B 側
    matchup_b="${PROJECT_DIR}/champions/${opp_id}/matchups.md"
    if [ -f "$matchup_b" ] && grep -q "^## vs ${champ_ja}" "$matchup_b"; then
        echo "$final_b" | python3 "${PROJECT_DIR}/scripts/replace-section-text.py" \
            "$opp_id" "$champ_ja" "$champ_en" || \
            echo "$(log_prefix) WARN: B 側 replace 失敗 (${opp_ja} vs ${champ_ja})"
    else
        printf '\n%s\n' "$final_b" >> "$matchup_b"
        echo "$(log_prefix) INFO: B 側追記 → ${opp_id}/matchups.md"
    fi

    # --- missing ファイルから削除 ---
    # A 側
    python3 -c "
lines = open('${source_file}').read().splitlines()
lines = [l for l in lines if not l.startswith('${champ_id}|') or '|${opp_id}|' not in l]
open('${source_file}', 'w').write('\n'.join(lines) + ('\n' if lines else ''))
"

    # B 側（全ロールの missing を検索）
    for mf in "${PROJECT_DIR}/scripts/missing-トップ.txt" \
               "${PROJECT_DIR}/scripts/missing-ミッド.txt" \
               "${PROJECT_DIR}/scripts/missing-ジャング.txt" \
               "${PROJECT_DIR}/scripts/missing-ADC.txt" \
               "${PROJECT_DIR}/scripts/missing-サポート.txt"; do
        [ -f "$mf" ] || continue
        python3 -c "
lines = open('${mf}').read().splitlines()
new = [l for l in lines if not (l.startswith('${opp_id}|') and '|${champ_id}|' in l)]
if len(new) < len(lines):
    open('${mf}', 'w').write('\n'.join(new) + ('\n' if new else ''))
"
    done

    echo "$(log_prefix) OK: ${champ_ja} vs ${opp_ja} 追加完了"
    PROCESSED=$((PROCESSED + 1))
done

echo "$(log_prefix) ===== 完了: 成功=${PROCESSED} 失敗=${FAILED} ====="
