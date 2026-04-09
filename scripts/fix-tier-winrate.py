#!/usr/bin/env python3
"""fix-tier-winrate.py
一言まとめセクションからティア評価・勝率（パッチ依存情報）を除去する

Usage:
  python3 scripts/fix-tier-winrate.py [--dry-run]
"""

import re
import sys
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv

CHAMP_DIR = Path(__file__).parent.parent / "champions"

# ティア・勝率を含む表現にマッチするか（除去対象があるか判定用）
HAS_TIER = re.compile(r'[SABCD][+\-]?ティア|[SABCD][+\-]? tier|勝率\d|パッチ\d+\.\d+では[SABCD]')

# 除去パターン（一言まとめのテキストに順番に適用）
REMOVE_PATTERNS = [
    # 【先に処理】パッチ番号付き文脈ごと除去（先に消さないと残骸が出る）
    r'[。、]?パッチ\d+\.\d+では[SABCD][+\-]?ティア評価[^。]*[。]?',
    r'[。、]?現パッチ[SABCD][+\-]?ティア（勝率\d+[\.\d]*%）[^。]*[。]?',
    r'[。、]?現パッチ[SABCD][+\-]?ティア評価[^。]*[。]?',
    # 中文の「Xティア・勝率N%と現パッチ屈指の安定枠で、」系
    r'[SABCD][+\-]?ティア[・]?勝率\d+[\.\d]*%と現パッチ[^、。]*[、]?',
    # 「Xティア・勝率N%」系（順序どちらでも）
    r'[SABCD][+\-]?ティア[・]?勝率\d+[\.\d]*%',
    r'勝率\d+[\.\d]*%[・]?[SABCD][+\-]?ティア',
    # 「X tier（勝率N%）」系（英字）
    r'[SABCD][+\-]? tier（勝率\d+[\.\d]*%）',
    # 「XティアのN%」「勝率N%のXティア」
    r'勝率\d+[\.\d]*%の[SABCD][+\-]?ティア',
    r'[SABCD][+\-]?ティア（勝率\d+[\.\d]*%）',
    # 単体
    r'[SABCD][+\-]?ティア',
    r'勝率\d+[\.\d]*%',
]

def clean_summary(text):
    for pat in REMOVE_PATTERNS:
        text = re.sub(pat, '', text)
    # 残骸の句読点を整理
    text = re.sub(r'[。、・\s]+。', '。', text)   # 「・。」「  。」→「。」
    text = re.sub(r'。{2,}', '。', text)          # 「。。」→「。」
    text = re.sub(r'[・、]{2,}', '、', text)      # 「・・」→「、」
    text = re.sub(r'[、・]\s*$', '。', text)      # 末尾が「・」「、」→「。」
    text = text.strip()
    if text and not text.endswith('。'):
        text += '。'
    return text

updated = 0
skipped = 0
manual = []

for guide_path in sorted(CHAMP_DIR.glob("*/guide.md")):
    content = guide_path.read_text()
    m = re.search(r'(## 一言まとめ\n)(.*?)(?=\n## |\Z)', content, re.DOTALL)
    if not m:
        continue

    original = m.group(2).strip()

    # 除去対象がなければスキップ
    if not HAS_TIER.search(original):
        skipped += 1
        continue

    cleaned = clean_summary(original)

    # 除去後もティア・勝率数値が残っていたら手動確認
    if HAS_TIER.search(cleaned):
        manual.append((guide_path.parent.name, original, cleaned))
        continue

    champ = guide_path.parent.name
    if DRY_RUN:
        print(f"[DRY-RUN] {champ}:")
        print(f"  前: {original}")
        print(f"  後: {cleaned}")
    else:
        # 元のテキスト（改行含む）を置換
        new_content = content[:m.start(2)] + cleaned + '\n' + content[m.end(2):]
        guide_path.write_text(new_content)
        print(f"更新: {champ}/guide.md")

    updated += 1

print(f"\n完了: 更新={updated}件 / スキップ={skipped}件")

if manual:
    print(f"\n⚠️  手動確認が必要 ({len(manual)}件):")
    for champ, before, after in manual:
        print(f"  {champ}:")
        print(f"    前: {before}")
        print(f"    後: {after}")
