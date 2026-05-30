#!/usr/bin/env python3
"""apply-item-aliases.py — 既存ガイドのアイテム名を公式名へ一括正規化

目的:
  lint-matchup.py の check_item_aliases は「これから生成するエントリ」の保険。
  既に champions/ に書かれてしまった誤表記（英語直訳カタカナ・英語名）を一掃するのが本スクリプト。
  スキル名の lint-matchup.py + quality-fix.py の2本立てと対称に、アイテム名にも
  「生成時 lint」と「既存一括修正」の両方を用意する。

  辞書は item-aliases.json（gen-item-aliases.py が Data Dragon から生成）を共有する。
  パッチでアイテム名が変わったら gen-item-aliases.py を再実行 → 本スクリプトで既存に追従できる。

使い方:
  python3 scripts/apply-item-aliases.py --dry-run   # 変更箇所を出すだけ（書き込まない）
  python3 scripts/apply-item-aliases.py             # champions/ 配下を実際に修正
"""

import glob
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ALIASES_PATH = os.path.join(SCRIPT_DIR, "item-aliases.json")
CHAMPIONS_DIR = os.path.join(SCRIPT_DIR, "..", "champions")


def load_aliases() -> list[dict]:
    with open(ALIASES_PATH, encoding="utf-8") as f:
        return json.load(f).get("aliases", [])


def main():
    dry_run = "--dry-run" in sys.argv[1:]
    aliases = load_aliases()
    # 長い pattern を先に適用して部分マッチの二重置換を防ぐ（lint-matchup.py と同方針）。
    aliases = sorted(aliases, key=lambda r: len(r["pattern"]), reverse=True)

    md_files = glob.glob(os.path.join(CHAMPIONS_DIR, "**", "*.md"), recursive=True)

    per_pattern: dict[str, int] = {}
    changed_files = 0
    for path in sorted(md_files):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        original = text
        for rule in aliases:
            pat, rep = rule["pattern"], rule["replacement"]
            if pat in text:
                cnt = text.count(pat)
                text = text.replace(pat, rep)
                per_pattern[pat] = per_pattern.get(pat, 0) + cnt
        if text != original:
            changed_files += 1
            if not dry_run:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)

    total = sum(per_pattern.values())
    label = "[dry-run] " if dry_run else ""
    print(f"{label}対象ファイル: {len(md_files)} / 変更ファイル: {changed_files} / 置換総数: {total}", file=sys.stderr)
    for pat, cnt in sorted(per_pattern.items(), key=lambda kv: -kv[1]):
        rep = next(r["replacement"] for r in aliases if r["pattern"] == pat)
        print(f"  {cnt:4d}  {pat} -> {rep}", file=sys.stderr)
    if dry_run and total:
        print("\n[dry-run] 上記を適用するには --dry-run を外して再実行", file=sys.stderr)


if __name__ == "__main__":
    main()
