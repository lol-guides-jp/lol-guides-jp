#!/bin/bash
# list-subrole-targets.sh
# 全チャンプのメイン/サブロール判定を「1体ずつ」Sonnet 4.6 + WebSearch で実行し、
# scripts/subrole-targets.json に書き出す。
#
# 旧実装は「170体を1回・検索3回」で判定していたが、170体ぶんの実 pick 率を3検索で
# 取れず、内部知識ベースの誤判定（例: ノクターン/リリアに MID サブが付く）が多発した。
# → gen-matchup.md と同じ「細粒度1単位ごとに専用 WebSearch を割り当てる」方式に統一。
#   各体で judge-subrole コマンドが pick 率のレーン内訳を読み、15% 閾値で main/sub を判定する。
#
# パッチ追従（check-patch.sh / refresh-subrole-targets.py）から呼ばれる想定だが手動実行も可。
#
# 手動実行:
#   ./scripts/list-subrole-targets.sh                 # 全体フル判定（≈170体ぶんの API 消化）
#   ./scripts/list-subrole-targets.sh --dry-run       # API を叩かず計画とコスト概算のみ表示
#   ./scripts/list-subrole-targets.sh --limit 3       # 先頭3体だけ実判定（パイプライン疎通テスト用）
#
# 出力: scripts/subrole-targets.json（git 管理）
# 旧ファイルは scripts/subrole-targets.json.prev にバックアップされる

set -euo pipefail

export NVM_DIR="${HOME}/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

PROJECT_DIR="/home/ojita/lol-guides-jp"
SCRIPTS_DIR="${PROJECT_DIR}/scripts"
DATE=$(date +%Y-%m-%d)
LOG_PREFIX="[${DATE} $(date +%H:%M:%S)]"
OUTPUT_FILE="${SCRIPTS_DIR}/subrole-targets.json"
BACKUP_FILE="${SCRIPTS_DIR}/subrole-targets.json.prev"
PATCH_FILE="${PROJECT_DIR}/current-patch.txt"

source "${PROJECT_DIR}/scripts/lib.sh"

# --- フラグ ---
DRY_RUN=0
LIMIT=0
RESUME=0
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --limit) LIMIT="${2:-0}"; shift 2 ;;
        # --resume: 既存 subrole-targets.json で note が fallback/preserved の体（＝前回判定
        #   失敗）だけを再判定する。実判定済みはそのまま引き継ぐ。レート上限で中断した
        #   フル判定を、成功分を捨てずに続きから完成させる用途。
        --resume) RESUME=1; shift ;;
        *) echo "${LOG_PREFIX} WARN: 未知の引数 '$1' を無視"; shift ;;
    esac
done

cd "$PROJECT_DIR" || { echo "${LOG_PREFIX} ERROR: ディレクトリが見つかりません"; exit 1; }

echo "${LOG_PREFIX} ===== サブロール判定開始（1体ループ方式） ====="

# --- 現在のパッチ ---
CURRENT_PATCH=$(tr -d '[:space:]' < "${PATCH_FILE}" 2>/dev/null || echo "26.11")
echo "${LOG_PREFIX} INFO: 対象パッチ=${CURRENT_PATCH}"

# --- 全チャンプを data.json から抽出（id/ja/en + role はフォールバック用） ---
TMP_DIR=$(mktemp -d)
trap 'rm -rf "${TMP_DIR}"' EXIT
CHAMPS_JSONL="${TMP_DIR}/champs.jsonl"

node -e "
const data = require('${PROJECT_DIR}/docs/data.json');
const out = data.champions.map(c => ({ id: c.id, ja: c.ja || c.name || c.id, en: c.en || c.id, role: c.role || c.mainRole }));
process.stdout.write(out.map(o => JSON.stringify(o)).join('\n') + '\n');
" > "${CHAMPS_JSONL}" || { echo "${LOG_PREFIX} ERROR: data.json からチャンプ抽出失敗"; exit 1; }

TOTAL=$(wc -l < "${CHAMPS_JSONL}" | tr -d ' ')
echo "${LOG_PREFIX} INFO: 対象チャンプ数=${TOTAL}"

# --- 保持(prev)参照元の決定 ---
# 判定失敗時に normalize が前回値を保持するための参照。
#   resume: .prev（前回の確定判定。中断したフル判定の汚染を受けていないクリーン版）
#   full  : 現 OUTPUT_FILE（最後にコミットした確定判定）
# どちらも無ければ空 {} で、その場合は従来どおりメインのみフォールバックになる。
PREV_JSON="${TMP_DIR}/prev.json"
if [ "${RESUME}" = "1" ] && [ -f "${BACKUP_FILE}" ]; then
    cp "${BACKUP_FILE}" "${PREV_JSON}"
elif [ -f "${OUTPUT_FILE}" ]; then
    cp "${OUTPUT_FILE}" "${PREV_JSON}"
else
    echo '{"champions":{}}' > "${PREV_JSON}"
fi

# --- resume: 再判定対象（note が fallback/preserved）だけに絞り、成功分はシード ---
GOOD_SEED="${TMP_DIR}/good-seed.jsonl"
: > "${GOOD_SEED}"
if [ "${RESUME}" = "1" ]; then
    [ -f "${OUTPUT_FILE}" ] || { echo "${LOG_PREFIX} ERROR: --resume だが ${OUTPUT_FILE} が無い"; exit 1; }
    # 既存判定を「再判定対象 id 集合」と「成功シード(正規エントリ)」に分ける。
    REJUDGE_IDS="${TMP_DIR}/rejudge-ids.txt"
    node -e "
      const t = require('${OUTPUT_FILE}').champions || {};
      const fs = require('fs');
      const rej = [];
      const seed = [];
      for (const [id, e] of Object.entries(t)) {
        const note = e.note || '';
        const failed = note.startsWith('fallback') || note.startsWith('preserved');
        if (failed) { rej.push(id); }
        else {
          seed.push(JSON.stringify({ id, ja: e.ja, en: e.en, main: e.main, sub: e.sub || [],
            roleShares: e.roleShares || {}, note: e.note || '', sources: e.sources || [] }));
        }
      }
      fs.writeFileSync('${REJUDGE_IDS}', rej.join('\n') + (rej.length ? '\n' : ''));
      fs.writeFileSync('${GOOD_SEED}', seed.join('\n') + (seed.length ? '\n' : ''));
    " || { echo "${LOG_PREFIX} ERROR: resume 仕分け失敗"; exit 1; }

    # CHAMPS_JSONL を再判定対象だけに絞る
    CHAMPS_FILTERED="${TMP_DIR}/champs-rejudge.jsonl"
    node -e "
      const fs = require('fs');
      const ids = new Set(fs.readFileSync('${REJUDGE_IDS}','utf-8').split('\n').filter(Boolean));
      const out = fs.readFileSync('${CHAMPS_JSONL}','utf-8').split('\n').filter(Boolean)
        .filter(l => ids.has(JSON.parse(l).id));
      process.stdout.write(out.join('\n') + (out.length ? '\n' : ''));
    " > "${CHAMPS_FILTERED}" || { echo "${LOG_PREFIX} ERROR: resume 絞り込み失敗"; exit 1; }
    CHAMPS_JSONL="${CHAMPS_FILTERED}"

    SEED_COUNT=$(wc -l < "${GOOD_SEED}" | tr -d ' ')
    TOTAL=$(wc -l < "${CHAMPS_JSONL}" | tr -d ' ')
    echo "${LOG_PREFIX} INFO: RESUME — 引き継ぎ(実判定済み)=${SEED_COUNT} / 再判定=${TOTAL}"
fi

# --- ドライラン ---
if [ "${DRY_RUN}" = "1" ]; then
    echo "${LOG_PREFIX} DRY-RUN: judge-subrole を ${TOTAL} 体ぶん Sonnet 4.6 で実行する想定"
    echo "${LOG_PREFIX} DRY-RUN: 1体あたり WebSearch 最大3回。推定コスト ≈ \$0.2/体 → 全体 ≈ \$$(awk "BEGIN{printf \"%.0f\", ${TOTAL}*0.2}")"
    echo "${LOG_PREFIX} DRY-RUN: 出力先 → ${OUTPUT_FILE}"
    echo "${LOG_PREFIX} DRY-RUN: 疎通だけ見るなら --limit 3 で先頭3体を実判定できる"
    echo "${LOG_PREFIX} ===== サブロール判定終了（DRY-RUN） ====="
    exit 0
fi

# --- 1体ずつ判定 ---
RESULTS_JSONL="${TMP_DIR}/results.jsonl"
: > "${RESULTS_JSONL}"
# resume: 実判定済みエントリを先にシード（再判定しない）
if [ "${RESUME}" = "1" ] && [ -s "${GOOD_SEED}" ]; then
    cat "${GOOD_SEED}" >> "${RESULTS_JSONL}"
fi
success=0; fallback=0; preserve=0; idx=0

while IFS= read -r champ_line || [ -n "$champ_line" ]; do
    [ -z "$champ_line" ] && continue
    idx=$((idx + 1))
    if [ "${LIMIT}" -gt 0 ] && [ "${idx}" -gt "${LIMIT}" ]; then
        echo "${LOG_PREFIX} INFO: --limit ${LIMIT} に到達、打ち切り"
        break
    fi

    cid=$(printf '%s' "$champ_line" | node -e "process.stdout.write(JSON.parse(require('fs').readFileSync(0,'utf-8')).id)")
    input=$(node -e "
      const c = JSON.parse(process.argv[1]);
      process.stdout.write(JSON.stringify({ champ: { id: c.id, ja: c.ja, en: c.en }, patch: process.argv[2] }));
    " "$champ_line" "$CURRENT_PATCH")
    # このチャンプの前回判定（保持用）を prev.json から取り出す。無ければ空文字。
    prev_entry=$(node -e "
      const t = require('${PREV_JSON}').champions || {};
      const e = t[process.argv[1]];
      process.stdout.write(e ? JSON.stringify(e) : '');
    " "$cid")

    echo "${LOG_PREFIX} INFO: [${idx}/${TOTAL}] ${cid} 判定中..."
    # run_cmd 失敗（API エラー・レート上限等）は1回リトライ（30s 待ち）。それでも駄目なら
    # normalize 側で prev を保持（PRESERVE）し、本物のサブを壊さない。
    result=$(run_cmd "judge-subrole" "$input") || result=""
    if [ -z "$result" ]; then
        echo "${LOG_PREFIX} WARN: ${cid} 1回目失敗、30s 後リトライ"
        sleep 30
        result=$(run_cmd "judge-subrole" "$input") || result=""
    fi

    # 生出力 → 正規エントリ1行を RESULTS_JSONL に追記。OK/PRESERVE/FALLBACK を stderr から集計。
    status_file="${TMP_DIR}/status.txt"
    printf '%s' "$result" \
        | node "${SCRIPTS_DIR}/normalize-subrole-result.js" "$champ_line" "$prev_entry" \
        >> "${RESULTS_JSONL}" 2> "${status_file}"
    last_status=$(head -1 "${status_file}" 2>/dev/null || true)
    case "$last_status" in
        OK*) success=$((success + 1)) ;;
        PRESERVE*) preserve=$((preserve + 1)); echo "${LOG_PREFIX} WARN: ${cid} 前回値を保持（${last_status}）" ;;
        *) fallback=$((fallback + 1)); echo "${LOG_PREFIX} WARN: ${cid} 空フォールバック（${last_status}）" ;;
    esac
done < "${CHAMPS_JSONL}"

echo "${LOG_PREFIX} INFO: 判定完了 成功=${success} 保持=${preserve} 空フォールバック=${fallback}"

# --- 集約して書き出し（バックアップ付き） ---
MIN_COUNT=100
[ "${LIMIT}" -gt 0 ] && MIN_COUNT="${LIMIT}"

# resume では .prev（クリーンな pre-中断 判定）を上書きしない。保持参照を壊さないため。
if [ "${RESUME}" != "1" ] && [ -f "${OUTPUT_FILE}" ]; then
    cp "${OUTPUT_FILE}" "${BACKUP_FILE}"
    echo "${LOG_PREFIX} INFO: 旧ファイルを ${BACKUP_FILE} にバックアップ"
fi

node "${SCRIPTS_DIR}/assemble-subrole-targets.js" \
    "${RESULTS_JSONL}" "${CURRENT_PATCH}" "${OUTPUT_FILE}" "${MIN_COUNT}" \
    || { echo "${LOG_PREFIX} ERROR: 集約失敗（subrole-targets.json は更新しない）"; exit 1; }

echo "${LOG_PREFIX} INFO: ${OUTPUT_FILE} に書き出し完了"
echo "${LOG_PREFIX} ===== サブロール判定終了 ====="
