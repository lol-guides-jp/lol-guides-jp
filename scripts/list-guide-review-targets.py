#!/usr/bin/env python3
# list-guide-review-targets.py
# guide.md の品質レビュー対象を優先度順に N体選定する（L1）
#
# 優先度:
#   1. 直近2パッチで変更されたチャンプ
#   2. review-history.json に未記録のチャンプ
#   3. last_reviewed が古い順
#
# 使い方:
#   python3 scripts/list-guide-review-targets.py [--count N] [--json]
#
# 出力（デフォルト）: チャンプIDを1行ずつ
# 出力（--json）: [{"id": "...", "ja": "...", "reason": "..."}]

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
HISTORY_FILE = PROJECT_DIR / "scripts" / "review-history.json"
PATCH_FILE = PROJECT_DIR / "current-patch.txt"


def load_champions() -> dict:
    """data.json から id_map を返す。"""
    data = json.loads((PROJECT_DIR / "docs" / "data.json").read_text(encoding="utf-8"))
    return {c["id"]: c for c in data.get("champions", [])}


def load_history() -> dict:
    if not HISTORY_FILE.exists():
        return {}
    return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))


def recent_patched_ids(id_map: dict, count: int = 2) -> set[str]:
    """current-patch.txt から直近 N パッチで変更された英語名がパッチノートに登場するIDのset。"""
    current = PATCH_FILE.read_text(encoding="utf-8").strip()
    major, minor = current.split(".")
    minor = int(minor)
    patches = [f"{major}.{minor - i}" for i in range(count)]

    changed: set[str] = set()
    for pv in patches:
        pf = PROJECT_DIR / "patches" / f"{pv}.md"
        if not pf.exists():
            continue
        content = pf.read_text(encoding="utf-8")
        for champ in id_map.values():
            if re.search(rf'\b{re.escape(champ["en"])}\b', content, re.IGNORECASE):
                changed.add(champ["id"])
    return changed


def main():
    parser = argparse.ArgumentParser(description="guide.md レビュー対象を優先度順に選定")
    parser.add_argument("--count", type=int, default=3, help="出力する件数（default: 3）")
    parser.add_argument("--json", action="store_true", help="JSON 形式で出力")
    parser.add_argument("--patch-window", type=int, default=2, help="直近何パッチを優先するか（default: 2）")
    args = parser.parse_args()

    id_map = load_champions()
    history = load_history()
    patched = recent_patched_ids(id_map, count=args.patch_window)

    def sort_key(cid: str) -> tuple:
        h = history.get(cid, {})
        last = h.get("last_reviewed", "")  # 未レビューは "" で最古扱い
        is_patched = 0 if cid in patched else 1  # 0 が優先
        return (is_patched, last, cid)

    sorted_ids = sorted(id_map.keys(), key=sort_key)
    selected = sorted_ids[: args.count]

    if args.json:
        out = []
        for cid in selected:
            reason = []
            if cid in patched:
                reason.append("直近パッチで変更")
            if cid not in history:
                reason.append("未レビュー")
            else:
                reason.append(f"最後のレビュー: {history[cid].get('last_reviewed', '?')}")
            out.append({"id": cid, "ja": id_map[cid]["ja"], "reason": " / ".join(reason)})
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for cid in selected:
            print(cid)


if __name__ == "__main__":
    main()
