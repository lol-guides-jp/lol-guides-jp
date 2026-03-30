#!/bin/bash
# lib.sh - 共通関数（ローカル優先・グローバルフォールバック）

# run_cmd <コマンド名> [引数]
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

    local model
    model=$(sed -n '1{/^---$/!q}; 2,/^---$/{/^model:/s/^model:[[:space:]]*//p}' "$cmd_file")

    local prompt
    prompt=$(awk 'NR==1 && /^---$/{skip=1;next} skip && /^---$/{skip=0;next} !skip' "$cmd_file" \
             | sed "s/\\\$ARGUMENTS/${args}/")

    claude --print --permission-mode acceptEdits ${model:+--model "$model"} "$prompt" < /dev/null
}
