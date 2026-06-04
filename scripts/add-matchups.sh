#!/bin/bash
# add-matchups.sh
# missing-*.txt から未対面を取り出し、gen-matchup（Sonnet 4.6 + WebSearch）で A/B 同時生成して追加する
#
# 使い方:
#   ./scripts/add-matchups.sh [--role トップ|ミッド|ジャング|ADC|サポート] [--batch N] [--sleep N] [--dry-run]
#   ./scripts/add-matchups.sh --cost-mode lite              # コスト最適化版（WebSearch 2クエリ・snippet制限）
#   ./scripts/add-matchups.sh --source scripts/requeue-ADC.txt --force    # パッチ反映用（requeue 消化）
#
# デフォルト: 全ロールから最大3件処理、sleep 4秒、cost-mode=quality
#
# --cost-mode quality|lite: quality は gen-matchup.md（WebSearch 2-3クエリ・全規約適用）。
#   lite は gen-matchup-lite.md（WebSearch 2クエリ固定・snippet 上位3件のみ）。
#   コストの目安: quality は約 $0.49/対面、lite は約 $0.10/対面（cache hit時はさらに低い）。
#
# --source: 任意のキューファイル1つを指定する。--role と排他。--force と組み合わせて
#   requeue-*.txt（パッチ反映）の消化に使う想定（2026-05-16 追加）。
#
# 新パイプライン（2026-05-23 案B 移行）:
#   missing から1対面取得 → run_cmd "gen-matchup{,-lite}" 1回呼び → validate-matchup-format.py
#     → lint-matchup.py で表記揺れ修正 → ファイル書き込み
#   旧フロー（call-gemini.py × 2 + Sonnet review-matchup × 1）は廃止。
#   patch・recent_changes は data.json から取得（recent_changes は将来 requeue-patched-matchups.py と連動）。

set -euo pipefail

export NVM_DIR="/home/ojita/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
log_prefix() { echo "[$(date '+%Y-%m-%d %H:%M:%S')]"; }

source "${PROJECT_DIR}/scripts/lib.sh"

# --- 終了時処理（集計行 + コミット） ---
# coding-standards.md §8 に従い auto_commit / auto_push を使う。
# 3段コミット: 新規追加 → 表記揺れ同期 → data.json 再ビルド。
# 各段は auto_commit の冪等性（変更なし→skip）に任せる。
# 注意: 早期終了パス（503・連続失敗等）でも集計行を出す必要があるため trap で出力する。
#       スクリプト末尾の echo は重複するので削除済み（2026-04-29）。
_finalize() {
    echo "$(log_prefix) ===== 完了: 成功=${PROCESSED:-0} 失敗=${FAILED:-0} ====="
    [ "${DRY_RUN:-0}" = "0" ] && [ "${PROCESSED:-0}" -gt 0 ] || return 0

    # 対面ファイル本体のコミット。TARGET が matchups-sub.md のときはサブロール対面用のパスを含める。
    if [ "${TARGET:-matchups.md}" = "matchups-sub.md" ]; then
        auto_commit champions/*/matchups-sub.md \
            -- "feat: サブロール対面ガイド ${PROCESSED}件追加 (自動生成)"
    else
        auto_commit champions/*/matchups.md \
            -- "feat: 対面ガイド ${PROCESSED}件追加 (自動生成)"
    fi

    echo "$(log_prefix) INFO: quality-fix 実行中..."
    python3 "${PROJECT_DIR}/scripts/quality-fix.py" >> "${PROJECT_DIR}/scripts/cron.log" 2>&1

    echo "$(log_prefix) INFO: guide.md 得意/苦手 同期中..."
    python3 "${PROJECT_DIR}/scripts/fix-guide-matchups.py" --all >> "${PROJECT_DIR}/scripts/cron.log" 2>&1
    if [ "${TARGET:-matchups.md}" = "matchups-sub.md" ]; then
        auto_commit champions/*/matchups-sub.md champions/*/guide.md \
            -- "fix: サブロール対面 表記揺れ・得意苦手同期 (自動)"
    else
        auto_commit champions/*/matchups.md champions/*/guide.md \
            -- "fix: 対面ガイド 表記揺れ・得意苦手同期 (自動)"
    fi

    echo "$(log_prefix) INFO: data.json 再ビルド中..."
    node "${PROJECT_DIR}/scripts/build-json.js" >> "${PROJECT_DIR}/scripts/cron.log" 2>&1
    auto_commit docs/data.json \
        -- "chore: data.json 再ビルド (対面ガイド追加後)"

    echo "$(log_prefix) INFO: push 中..."
    auto_push || echo "$(log_prefix) WARN: push 失敗（trap EXIT 内のため継続）"
}
trap '_finalize' EXIT

# --- 引数解析 ---
ROLE=""
SOURCE=""  # 任意のキューファイル1つを指定（--role と排他、2026-05-16 追加）
BATCH=3
DRY_RUN=0
FORCE=0  # 1 = 既存エントリでもスキップせず再生成（両方向再生成用）
COST_MODE="quality"  # quality (gen-matchup) or lite (gen-matchup-lite)
TARGET="matchups.md"  # 書き込み先ファイル名（matchups.md or matchups-sub.md）。サブロール対面用に 2026-05-25 追加

SLEEP=4  # API コール間の sleep 秒数（Sonnet RPM 緩和）

while [[ $# -gt 0 ]]; do
    case "$1" in
        --role)      ROLE="$2";      shift 2 ;;
        --source)    SOURCE="$2";    shift 2 ;;
        --batch)     BATCH="$2";     shift 2 ;;
        --sleep)     SLEEP="$2";     shift 2 ;;
        --cost-mode) COST_MODE="$2"; shift 2 ;;
        --target)    TARGET="$2";    shift 2 ;;
        --force)     FORCE=1;        shift ;;
        --dry-run)   DRY_RUN=1;      shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# TARGET は matchups.md / matchups-sub.md のみ許可（不正値の早期検出）
case "$TARGET" in
    matchups.md|matchups-sub.md) ;;
    *) echo "ERROR: --target は matchups.md か matchups-sub.md (received: ${TARGET})" >&2; exit 1 ;;
esac

# サブロール対面のキューファイル名から「対面が起きたレーン」のフルロール名を導出する。
# 例: missing-subrole-ミッド.txt → ミッドレーン、requeue-subrole-ADC.txt → ADC。
# suffix は gen-subrole-queue.py の ROLE_TO_FILE_SUFFIX と対で、ここはその逆引き。
# A 側（サブ起用チャンプ）も B 側（相手）も同じレーンセクションに書く（レーン基準マージ）。
sub_lane_from_source() {
    local sf base suffix
    sf="$1"
    base=$(basename "$sf" .txt)   # missing-subrole-ミッド
    suffix="${base##*-}"          # ミッド
    case "$suffix" in
        トップ)   echo "トップレーン" ;;
        ジャング) echo "ジャングル" ;;
        ミッド)   echo "ミッドレーン" ;;
        ADC)      echo "ADC" ;;
        サポート) echo "サポート" ;;
        *)        echo "" ;;       # 不明 → 呼び出し側でエラー扱い
    esac
}

if [ -n "$ROLE" ] && [ -n "$SOURCE" ]; then
    echo "ERROR: --role と --source は同時に指定できません" >&2
    exit 1
fi

# cost-mode → コマンド名を決定
case "$COST_MODE" in
    quality) COMMAND_NAME="gen-matchup" ;;
    lite)    COMMAND_NAME="gen-matchup-lite" ;;
    *) echo "ERROR: --cost-mode は quality か lite (received: ${COST_MODE})"; exit 1 ;;
esac

# パッチ番号を Data Dragon API から直接取得（"16.10.1" → "16.10"）
# data.json は check-patch.sh（毎週月曜4時）に依存しており、月曜以外のパッチ発行を追従できない。
# WebSearch の検索精度を確保するため、API から最新を取りに行く。失敗時のみ data.json にフォールバック。
PATCH=$(curl -s --max-time 8 'https://ddragon.leagueoflegends.com/api/versions.json' 2>/dev/null \
    | python3 -c "import json,sys; v=json.load(sys.stdin)[0]; print('.'.join(v.split('.')[:2]))" 2>/dev/null \
    || echo "")

if [ -z "$PATCH" ]; then
    echo "$(log_prefix) WARN: Data Dragon API 取得失敗 → data.json にフォールバック"
    PATCH=$(python3 -c "
import json
d = json.load(open('${PROJECT_DIR}/docs/data.json', encoding='utf-8'))
ver = d.get('meta', {}).get('ddragonVersion', '')
print('.'.join(ver.split('.')[:2]) if ver else 'unknown')
" 2>/dev/null || echo "unknown")
fi

# 注意: DRY_RUN は export しない。export すると lib.sh の run_cmd が
# 「[DRY-RUN] スキップ」して [] を返してしまい、validate に進めない。
# ドライランは「実 API call を投げて生成物だけ確認し、ファイル書き込みはスキップ」が意図。
# 旧フロー（call-gemini.py 経由）からの引き継ぎで export していたが、新パイプでは不要。

cd "$PROJECT_DIR"

echo "$(log_prefix) ===== add-matchups 開始 (batch=${BATCH}, role=${ROLE:-全て}, sleep=${SLEEP}s, cost-mode=${COST_MODE}, target=${TARGET}, patch=${PATCH}) ====="

# --- 対象ファイルを決定 ---
if [ -n "$SOURCE" ]; then
    MISSING_FILES=("$SOURCE")
elif [ -n "$ROLE" ]; then
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
    # matchups.md はフラット「## vs」、matchups-sub.md はセクション配下「### vs」。
    matchup_file="${PROJECT_DIR}/champions/${champ_id}/${TARGET}"
    ENTRY_EXISTS=0
    if [ -f "$matchup_file" ]; then
        if [ "$TARGET" = "matchups-sub.md" ]; then
            grep -q "^### vs ${opp_ja}" "$matchup_file" && ENTRY_EXISTS=1
        else
            grep -q "^## vs ${opp_ja}" "$matchup_file" && ENTRY_EXISTS=1
        fi
    fi
    if [ "$ENTRY_EXISTS" = "1" ] && [ "$FORCE" = "0" ]; then
        echo "$(log_prefix) SKIP: ${champ_ja} vs ${opp_ja} は既に存在"
        # missing から削除
        if [ "$DRY_RUN" = "0" ]; then
            python3 -c "
import sys
lines = open('${source_file}', encoding='utf-8').read().splitlines()
lines = [l for l in lines if not l.startswith('${champ_id}|') or '|${opp_id}|' not in l]
open('${source_file}', 'w', encoding='utf-8').write('\n'.join(lines) + ('\n' if lines else ''))
"
        fi
        continue
    fi
    [ "$ENTRY_EXISTS" = "1" ] && echo "$(log_prefix) INFO: ${champ_ja} vs ${opp_ja} を強制再生成 (--force)"

    # --- スキル名・英語名を data.json から抽出 ---
    champ_en=$(python3 -c "
import json
data = json.load(open('${PROJECT_DIR}/docs/data.json', encoding='utf-8'))
cmap = {c['id']:c for c in data['champions']}
print(cmap.get('${champ_id}', {}).get('en', '${champ_id}'))
" 2>/dev/null || echo "$champ_id")

    opp_en_from_data=$(python3 -c "
import json
data = json.load(open('${PROJECT_DIR}/docs/data.json', encoding='utf-8'))
cmap = {c['id']:c for c in data['champions']}
print(cmap.get('${opp_id}', {}).get('en', '${opp_en}'))
" 2>/dev/null || echo "$opp_en")

    # champ_slug / opp_slug は scrape-winrate.py 用のみだったため削除（2026-05-24 案B 移行）。
    # gen-matchup は en 名で WebSearch するためスラグ不要。

    # champ/opp のスキル文字列はタブ区切りで返し、タブで分割する。
    # NG: print(a, b) は空白区切り → skills 内部の ", " 空白で read -r が誤分割し、
    #     champ_skills が1スキル目で切れて残りが opp_skills に混入していた（2026-05-29 修正）。
    IFS=$'\t' read -r champ_skills opp_skills < <(python3 - << PYEOF
import json
data = json.load(open("${PROJECT_DIR}/docs/data.json", encoding="utf-8"))
cmap = {c["id"]: c for c in data["champions"]}
def skills_str(cid):
    c = cmap.get(cid, {})
    parts = []
    for s in c.get("skills", []):
        if s["key"] in "PQWER":
            parts.append(f"{s['key']}({s['name']})")
    return ", ".join(parts)
print(skills_str("${champ_id}") + "\t" + skills_str("${opp_id}"))
PYEOF
)

    # --- gen-matchup 用 JSON 入力構築 ---
    # 勝率は gen-matchup 側で WebSearch から取得する（Lolalytics が Cloudflare ブロックで scrape 不可、
    # 2026-05-24 移行）。matchup tips の検索結果に勝率が含まれるため二度引きにならない。
    gen_input=$(CHAMP_ID="$champ_id" CHAMP_JA="$champ_ja" CHAMP_EN="$champ_en" CHAMP_SKILLS="$champ_skills" \
        OPP_ID="$opp_id" OPP_JA="$opp_ja" OPP_EN="$opp_en_from_data" OPP_SKILLS="$opp_skills" \
        PATCH="$PATCH" \
        python3 -c "
import json, os
print(json.dumps({
    'champ_a': {
        'id': os.environ['CHAMP_ID'],
        'ja': os.environ['CHAMP_JA'],
        'en': os.environ['CHAMP_EN'],
        'skills': os.environ['CHAMP_SKILLS'],
    },
    'champ_b': {
        'id': os.environ['OPP_ID'],
        'ja': os.environ['OPP_JA'],
        'en': os.environ['OPP_EN'],
        'skills': os.environ['OPP_SKILLS'],
    },
    'patch': os.environ['PATCH'],
    'recent_changes': []
}, ensure_ascii=False))
")

    # --- gen-matchup 実行（多層 timeout: 600 > run_cmd内 540 > Sonnet API 300）---
    # クォート安全のため入力ファイルを介す（gen_input が " を含むため heredoc 不可）。
    gen_input_file=$(mktemp /tmp/gen-matchup-input.XXXXXX.json)
    echo "$gen_input" > "$gen_input_file"

    gen_result=$(timeout 600 bash -c "
        export NVM_DIR='${HOME}/.nvm'
        [ -s \"\$NVM_DIR/nvm.sh\" ] && . \"\$NVM_DIR/nvm.sh\"
        export PROJECT_DIR='${PROJECT_DIR}'
        export CLAUDE_SUBPROCESS=1
        source '${PROJECT_DIR}/scripts/lib.sh'
        run_cmd '${COMMAND_NAME}' \"\$(cat '${gen_input_file}')\"
    ") || {
        ec=$?
        rm -f "$gen_input_file"
        SONNET_FAIL_STREAK=$((SONNET_FAIL_STREAK + 1))
        if [ $ec -eq 124 ]; then
            echo "$(log_prefix) ERROR: ${COMMAND_NAME} timeout 600s (${champ_ja} vs ${opp_ja}) [streak=${SONNET_FAIL_STREAK}]"
        else
            echo "$(log_prefix) ERROR: ${COMMAND_NAME} 失敗 ec=${ec} (${champ_ja} vs ${opp_ja}) [streak=${SONNET_FAIL_STREAK}]"
        fi
        FAILED=$((FAILED + 1))
        # 連続失敗閾値: 4。一時障害（API瞬断・503・タイムアウト）を spending limit と誤検知しないため。
        # 詳細: known-failures.md「連続失敗で打ち切る判定の閾値が低いと一時障害で誤検知する」
        if [ "$SONNET_FAIL_STREAK" -ge 4 ]; then
            echo "$(log_prefix) INFO: ${COMMAND_NAME} ${SONNET_FAIL_STREAK}件連続失敗 → 一時障害の可能性が高いためバッチ中断"
            exit 0
        fi
        continue
    }
    rm -f "$gen_input_file"

    if [ -z "$gen_result" ]; then
        SONNET_FAIL_STREAK=$((SONNET_FAIL_STREAK + 1))
        echo "$(log_prefix) ERROR: ${COMMAND_NAME} 結果が空 (${champ_ja} vs ${opp_ja}) [streak=${SONNET_FAIL_STREAK}]"
        FAILED=$((FAILED + 1))
        if [ "$SONNET_FAIL_STREAK" -ge 4 ]; then
            echo "$(log_prefix) INFO: ${COMMAND_NAME} ${SONNET_FAIL_STREAK}件連続空結果 → バッチ中断"
            exit 0
        fi
        continue
    fi

    # --- validate-matchup-format.py で検証 ---
    validate_err=$(echo "$gen_result" | python3 "${PROJECT_DIR}/scripts/validate-matchup-format.py" 2>&1) || {
        echo "$(log_prefix) ERROR: validate 失敗 (${champ_ja} vs ${opp_ja}): ${validate_err}"
        echo "$(log_prefix) DEBUG: gen_result=${gen_result:0:200}"
        echo "[$(date +%Y-%m-%d)] VALIDATE_FAILED: ${champ_ja} vs ${opp_ja} [${validate_err}]" \
            >> "${PROJECT_DIR}/scripts/add-matchups-review.log"
        FAILED=$((FAILED + 1))
        continue
    }

    # --- entry_a / entry_b / sources を抽出 ---
    entry_a=$(echo "$gen_result" | python3 "${PROJECT_DIR}/scripts/validate-matchup-format.py" --extract a)
    entry_b=$(echo "$gen_result" | python3 "${PROJECT_DIR}/scripts/validate-matchup-format.py" --extract b)
    sources_json=$(echo "$gen_result" | python3 "${PROJECT_DIR}/scripts/validate-matchup-format.py" --extract sources)

    # --- lint-matchup.py で表記揺れ修正（gen-matchup でも漏れる規約があるため保険として残す）---
    final_a=$(echo "$entry_a" | OPP_SKILLS="$opp_skills" python3 "${PROJECT_DIR}/scripts/lint-matchup.py" --fix 2>/dev/null) || final_a="$entry_a"
    final_b=$(echo "$entry_b" | OPP_SKILLS="$champ_skills" python3 "${PROJECT_DIR}/scripts/lint-matchup.py" --fix 2>/dev/null) || final_b="$entry_b"

    # --- DRY_RUN: 書き込みスキップ ---
    if [ "$DRY_RUN" = "1" ]; then
        echo "$(log_prefix) [DRY-RUN] A 側:"
        echo "$final_a"
        echo ""
        echo "$(log_prefix) [DRY-RUN] B 側:"
        echo "$final_b"
        echo "$(log_prefix) [DRY-RUN] sources: ${sources_json}"
        echo "$(log_prefix) [DRY-RUN] ファイル書き込みスキップ"
        SONNET_FAIL_STREAK=0
        PROCESSED=$((PROCESSED + 1))
        continue
    fi

    SONNET_FAIL_STREAK=0

    # --- ファイル書き込み ---
    matchup_b="${PROJECT_DIR}/champions/${opp_id}/${TARGET}"

    if [ "$TARGET" = "matchups-sub.md" ]; then
        # サブロール対面: レーンセクション構造へ upsert（冪等。同一相手は置換、無ければ追記）。
        # A 側（サブ起用チャンプ）も B 側（相手）も「対面が起きたレーン」＝ source_file 由来の
        # 同一 ## {lane} セクションに入れる。build-json.js がそのレーンへレーン基準マージする。
        sub_lane=$(sub_lane_from_source "$source_file")
        if [ -z "$sub_lane" ]; then
            echo "$(log_prefix) ERROR: source_file からレーン導出失敗 (${source_file}) — スキップ"
            FAILED=$((FAILED + 1))
            continue
        fi
        echo "$final_a" | python3 "${PROJECT_DIR}/scripts/sub_matchup_io.py" upsert \
            "$matchup_file" "$sub_lane" || {
            echo "$(log_prefix) ERROR: A 側 upsert 失敗 (${champ_ja} vs ${opp_ja})"
            FAILED=$((FAILED + 1))
            continue
        }
        echo "$(log_prefix) INFO: A 側 upsert → ${champ_id}/${TARGET} [## ${sub_lane}]"
        echo "$final_b" | python3 "${PROJECT_DIR}/scripts/sub_matchup_io.py" upsert \
            "$matchup_b" "$sub_lane" || \
            echo "$(log_prefix) WARN: B 側 upsert 失敗 (${opp_ja} vs ${champ_ja})"
    else
        # メインロール対面（matchups.md、フラット ## vs 構造）。
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
            echo "$(log_prefix) INFO: A 側追記 → ${champ_id}/${TARGET}"
        fi
        # B 側
        if [ -f "$matchup_b" ] && grep -q "^## vs ${champ_ja}" "$matchup_b"; then
            echo "$final_b" | python3 "${PROJECT_DIR}/scripts/replace-section-text.py" \
                "$opp_id" "$champ_ja" "$champ_en" || \
                echo "$(log_prefix) WARN: B 側 replace 失敗 (${opp_ja} vs ${champ_ja})"
        else
            printf '\n%s\n' "$final_b" >> "$matchup_b"
            echo "$(log_prefix) INFO: B 側追記 → ${opp_id}/${TARGET}"
        fi
    fi

    # --- missing ファイルから削除 ---
    # A 側
    python3 -c "
lines = open('${source_file}', encoding='utf-8').read().splitlines()
lines = [l for l in lines if not l.startswith('${champ_id}|') or '|${opp_id}|' not in l]
open('${source_file}', 'w', encoding='utf-8').write('\n'.join(lines) + ('\n' if lines else ''))
"

    # B 側（全キューを検索: missing/requeue/missing-subrole/requeue-subrole）
    # TARGET によって対象キューを切り替える:
    #   matchups.md     → missing-{role}.txt / requeue-{role}.txt （メインロール対面）
    #   matchups-sub.md → missing-subrole-{role}.txt / requeue-subrole-{role}.txt （サブロール対面）
    if [ "$TARGET" = "matchups-sub.md" ]; then
        queue_glob="${PROJECT_DIR}/scripts/missing-subrole-*.txt ${PROJECT_DIR}/scripts/requeue-subrole-*.txt"
    else
        # B側エントリは missing だけでなく requeue-{role}.txt にも残りうる（対称ペア）。
        # requeue を含めないと opp|champ が消えず、後で --force で重複再生成され二度手間になる（2026-05-29 追加）。
        # requeue-[!s]*.txt はメインロールの requeue のみ（requeue-subrole-* は除外）。
        queue_glob="${PROJECT_DIR}/scripts/missing-トップ.txt ${PROJECT_DIR}/scripts/missing-ミッド.txt ${PROJECT_DIR}/scripts/missing-ジャング.txt ${PROJECT_DIR}/scripts/missing-ADC.txt ${PROJECT_DIR}/scripts/missing-サポート.txt ${PROJECT_DIR}/scripts/requeue-[!s]*.txt"
    fi
    for mf in $queue_glob; do
        [ -f "$mf" ] || continue
        python3 -c "
lines = open('${mf}', encoding='utf-8').read().splitlines()
new = [l for l in lines if not (l.startswith('${opp_id}|') and '|${champ_id}|' in l)]
if len(new) < len(lines):
    open('${mf}', 'w', encoding='utf-8').write('\n'.join(new) + ('\n' if new else ''))
"
    done

    echo "$(log_prefix) OK: ${champ_ja} vs ${opp_ja} 追加完了"
    PROCESSED=$((PROCESSED + 1))
done
# 集計行は trap '_finalize' EXIT で出力する（早期終了パスでも一貫させるため）。
