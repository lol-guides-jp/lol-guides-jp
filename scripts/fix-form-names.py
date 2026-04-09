#!/usr/bin/env python3
"""
fix-form-names.py
形態変化チャンプの表記ブレを一括修正する

カテゴリB修正:
- ジェイス: 「レンジフォーム」→「キャノンモード」
- エリス: 「蜘蛛形態」→「クモ形態」（「蜘蛛フォーム」も統一）

--dry-run で変更内容を確認してから実行する
"""

import sys
import re
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv

REPLACEMENTS = [
    # ジェイス: レンジフォーム → キャノンモード
    (re.compile(r"レンジフォーム"), "キャノンモード"),
    # エリス: 蜘蛛形態 → クモ形態
    (re.compile(r"蜘蛛形態"), "クモ形態"),
    # エリス: 蜘蛛フォーム → クモ形態
    (re.compile(r"蜘蛛フォーム"), "クモ形態"),
]

def process_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    new_text = text
    count = 0
    for pattern, replacement in REPLACEMENTS:
        matches = pattern.findall(new_text)
        if matches:
            count += len(matches)
            new_text = pattern.sub(replacement, new_text)
    if count > 0:
        print(f"{'[DRY]' if DRY_RUN else '[FIX]'} {path.relative_to(BASE)} ({count}件)")
        if not DRY_RUN:
            path.write_text(new_text, encoding="utf-8")
    return count

BASE = Path(__file__).parent.parent
total = 0
for md in sorted(BASE.glob("champions/**/*.md")):
    total += process_file(md)

print(f"\n合計: {total}件{'（ドライラン）' if DRY_RUN else '修正済み'}")
