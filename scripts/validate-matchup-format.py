#!/usr/bin/env python3
"""gen-matchup の出力JSONを検証・抽出する。

使い方:
  echo "$json" | python3 scripts/validate-matchup-format.py             # 検証のみ exit 0/1
  echo "$json" | python3 scripts/validate-matchup-format.py --extract a # entry_a を stdout
  echo "$json" | python3 scripts/validate-matchup-format.py --extract b # entry_b を stdout
  echo "$json" | python3 scripts/validate-matchup-format.py --extract sources

exit code:
  0: success（または extract 正常）
  1: error ステータス / JSON parse 失敗 / フォーマット違反
  2: extract 対象が存在しない
"""

import json
import re
import sys

REQUIRED_BULLETS = [
    r"\*\*(有利|やや有利|五分|やや不利|不利)（勝率約\d+%）\*\*",
    r"\*\*Lv1〜2\*\*",
    r"\*\*Lv3〜5\*\*",
    r"\*\*Lv6以降\*\*",
    r"\*\*ウェーブ管理\*\*",
    r"\*\*注意ポイント\*\*",
]


def validate_entry(entry: str, side: str) -> list[str]:
    errs = []
    if not entry.startswith("## vs "):
        errs.append(f"{side}: '## vs ' で始まっていない")
    for pat in REQUIRED_BULLETS:
        if not re.search(pat, entry):
            errs.append(f"{side}: 必須項目 {pat} が見つからない")
    return errs


def main() -> int:
    extract = None
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--extract":
        extract = args[1]

    raw = sys.stdin.read().strip()
    if not raw:
        print("ERROR: 標準入力が空", file=sys.stderr)
        return 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON parse 失敗: {e}", file=sys.stderr)
        print(f"raw[:200]: {raw[:200]}", file=sys.stderr)
        return 1

    if not isinstance(data, dict):
        # lib.sh の DRY-RUN モードが [] を返すケース、または gen-matchup が誤って配列を返したケース
        print(f"ERROR: JSON ルートが dict でない: {type(data).__name__}", file=sys.stderr)
        print(f"raw[:200]: {raw[:200]}", file=sys.stderr)
        return 1

    status = data.get("status")
    if status == "error":
        reason = data.get("reason", "理由なし")
        print(f"ERROR: gen-matchup が error を返した: {reason}", file=sys.stderr)
        return 1

    if status != "success":
        print(f"ERROR: status が success/error 以外: {status!r}", file=sys.stderr)
        return 1

    entry_a = data.get("entry_a", "")
    entry_b = data.get("entry_b", "")
    sources = data.get("sources", [])

    if not entry_a or not entry_b:
        print("ERROR: entry_a または entry_b が空", file=sys.stderr)
        return 1

    errs = validate_entry(entry_a, "entry_a") + validate_entry(entry_b, "entry_b")
    if errs:
        for e in errs:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not isinstance(sources, list) or len(sources) == 0:
        print("WARN: sources が空（内部知識のみで生成された可能性）", file=sys.stderr)

    if extract:
        if extract == "a":
            print(entry_a)
        elif extract == "b":
            print(entry_b)
        elif extract == "sources":
            print(json.dumps(sources, ensure_ascii=False))
        else:
            print(f"ERROR: 未知の --extract {extract!r}", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
