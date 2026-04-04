#!/bin/bash
# lib.sh - 各スクリプトが source する共通関数

# コストログのパス（全リポジトリ共通）
COST_LOG="${HOME}/.claude/cost.log"

# run_cmd <コマンド名> [引数]
# .claude/commands/<コマンド名>.md の内容を claude --print に渡す。
# ローカル優先・グローバルフォールバック。
# frontmatter に model: が指定されていれば --model フラグを自動付与する。
# 実行結果の使用量を ~/.claude/cost.log に記録する。
run_cmd() {
    local cmd_name="$1"
    local args="${2:-}"

    # ローカル優先、なければグローバルを参照
    local local_file="${PROJECT_DIR}/.claude/commands/${cmd_name}.md"
    local global_file="${HOME}/.claude/commands/${cmd_name}.md"
    local cmd_file

    if [ -f "$local_file" ]; then
        cmd_file="$local_file"
    elif [ -f "$global_file" ]; then
        cmd_file="$global_file"
    else
        echo "${LOG_PREFIX:-} ERROR: コマンド ${cmd_name} が見つかりません" >&2
        return 1
    fi

    # frontmatter から model を抽出（---で囲まれたブロック内の model: 行）
    local model
    model=$(sed -n '1{/^---$/!q}; 2,/^---$/{/^model:/s/^model:[[:space:]]*//p}' "$cmd_file")

    # frontmatter を除いたプロンプトを生成
    local prompt
    prompt=$(awk 'NR==1 && /^---$/{skip=1;next} skip && /^---$/{skip=0;next} !skip' "$cmd_file" \
             | sed "s|\\\$ARGUMENTS|${args}|")

    # DRY_RUN モード
    if [ "${DRY_RUN:-0}" = "1" ]; then
        echo "${LOG_PREFIX:-[DRY-RUN]} DRY-RUN: run_cmd ${cmd_name} をスキップ" >&2
        echo "[]"
        return 0
    fi

    # JSON出力で実行し、コスト情報を抽出
    local json_output
    json_output=$(claude --print --output-format json --allowed-tools "Read,Glob,Grep" ${model:+--model "$model"} "$prompt" < /dev/null 2>&1)
    local exit_code=$?

    # 使用量をログに記録
    local usage_usd duration_ms input_tokens output_tokens
    usage_usd=$(echo "$json_output" | node -e "try{const d=JSON.parse(require('fs').readFileSync(0,'utf8'));console.log(d.total_cost_usd||0)}catch{console.log(0)}" 2>/dev/null)
    duration_ms=$(echo "$json_output" | node -e "try{const d=JSON.parse(require('fs').readFileSync(0,'utf8'));console.log(d.duration_ms||0)}catch{console.log(0)}" 2>/dev/null)
    input_tokens=$(echo "$json_output" | node -e "try{const d=JSON.parse(require('fs').readFileSync(0,'utf8'));const u=d.usage||{};console.log((u.input_tokens||0)+(u.cache_creation_input_tokens||0)+(u.cache_read_input_tokens||0))}catch{console.log(0)}" 2>/dev/null)
    output_tokens=$(echo "$json_output" | node -e "try{const d=JSON.parse(require('fs').readFileSync(0,'utf8'));console.log((d.usage||{}).output_tokens||0)}catch{console.log(0)}" 2>/dev/null)

    local repo_name
    repo_name=$(basename "${PROJECT_DIR}")
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
        "$(date +%Y-%m-%d)" "$(date +%H:%M:%S)" "$repo_name" "$cmd_name" \
        "$usage_usd" "$duration_ms" "$input_tokens" "$output_tokens" "$exit_code" >> "$COST_LOG"

    # 本文を標準出力に返す（JSONからresultフィールドを抽出）
    local result_text
    result_text=$(echo "$json_output" | node -e "try{const d=JSON.parse(require('fs').readFileSync(0,'utf8'));process.stdout.write(d.result||'')}catch{}" 2>/dev/null)
    echo "$result_text"

    return $exit_code
}

# dispatch_ops <json> [base_dir]
# JSON ops配列を受け取り、ファイル操作を実行する（L1）。
# ops: write / append / copy / move / delete
# パスはbase_dir相対 or 絶対パスどちらも可。
# base_dir省略時は PROJECT_DIR を使う。
dispatch_ops() {
    local json="$1"
    local base_dir="${2:-${PROJECT_DIR}}"

    # DRY_RUN モード
    if [ "${DRY_RUN:-0}" = "1" ]; then
        echo "$json" | node -e "
const ops = JSON.parse(require('fs').readFileSync(0, 'utf8'));
ops.forEach(op => console.log('[DRY-RUN]', JSON.stringify(op)));
" 2>/dev/null
        return 0
    fi

    echo "$json" | DISPATCH_BASE="$base_dir" node -e "
const fs = require('fs');
const path = require('path');
const base = process.env.DISPATCH_BASE;
const resolve = p => path.isAbsolute(p) ? p : path.join(base, p);
const raw = require('fs').readFileSync(0, 'utf8').trim();
const cleaned = raw.replace(/^\`\`\`(?:json)?\n?/, '').replace(/\n?\`\`\`$/, '').trim();
const ops = JSON.parse(cleaned);
ops.forEach(op => {
    try {
        if (op.op === 'write') {
            fs.mkdirSync(path.dirname(resolve(op.path)), {recursive: true});
            fs.writeFileSync(resolve(op.path), op.content, 'utf8');
            console.log('write:', op.path);
        } else if (op.op === 'append') {
            fs.mkdirSync(path.dirname(resolve(op.path)), {recursive: true});
            fs.appendFileSync(resolve(op.path), op.content, 'utf8');
            console.log('append:', op.path);
        } else if (op.op === 'copy') {
            fs.mkdirSync(path.dirname(resolve(op.dest)), {recursive: true});
            fs.copyFileSync(resolve(op.src), resolve(op.dest));
            console.log('copy:', op.src, '->', op.dest);
        } else if (op.op === 'move') {
            fs.mkdirSync(path.dirname(resolve(op.dest)), {recursive: true});
            fs.renameSync(resolve(op.src), resolve(op.dest));
            console.log('move:', op.src, '->', op.dest);
        } else if (op.op === 'delete') {
            fs.unlinkSync(resolve(op.path));
            console.log('delete:', op.path);
        } else {
            console.error('WARN: unknown op:', op.op);
        }
    } catch (e) {
        console.error('ERROR:', op.op, JSON.stringify(op), e.message);
        process.exit(1);
    }
});
"
}
