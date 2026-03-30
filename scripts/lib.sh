#!/bin/bash
# lib.sh - 共通関数（content-pipelineと同パターン）

# run_cmd <コマンド名> [引数]
run_cmd() {
    local cmd_name="$1"
    local args="${2:-}"
    local cmd_file="${GUIDE_DIR}/.claude/commands/${cmd_name}.md"

    local model
    model=$(sed -n '1{/^---$/!q}; 2,/^---$/{/^model:/s/^model:[[:space:]]*//p}' "$cmd_file")

    local prompt
    prompt=$(awk 'NR==1 && /^---$/{skip=1;next} skip && /^---$/{skip=0;next} !skip' "$cmd_file" \
             | sed "s/\\\$ARGUMENTS/${args}/")

    claude --print --permission-mode acceptEdits ${model:+--model "$model"} "$prompt" < /dev/null
}
