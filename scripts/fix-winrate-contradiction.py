#!/usr/bin/env python3
"""勝率と有利/不利の矛盾を一括修正するスクリプト。

- 有利/やや有利なのに勝率50%未満 → 勝率を50%超に反転（例: 48% → 52%）
- 不利/やや不利なのに勝率51%以上 → 勝率を50%未満に反転（例: 53% → 47%）
"""

import re
import glob

MATCHUP_DIR = "/mnt/c/Users/ojita/lol-guides-jp/champions/*/matchups.md"

def flip_winrate(wr):
    """50%を中心に勝率を反転"""
    return 100 - wr

def fix_line(line):
    # 有利系で勝率50%未満
    m = re.search(r'((?:やや)?有利)（勝率約(\d+)[〜~]?(\d*)%）', line)
    if m and '不利' not in m.group(1):
        wr = int(m.group(2))
        wr2 = m.group(3)
        if wr < 50:
            new_wr = flip_winrate(wr)
            if wr2:
                new_wr2 = flip_winrate(int(wr2))
                old = f"勝率約{wr}〜{wr2}%"
                new = f"勝率約{min(new_wr, new_wr2)}〜{max(new_wr, new_wr2)}%"
            else:
                old = f"勝率約{wr}%"
                new = f"勝率約{new_wr}%"
            return line.replace(old, new), old, new

    # 不利系で勝率51%以上
    m = re.search(r'((?:やや)?不利)（勝率約(\d+)[〜~]?(\d*)%）', line)
    if m:
        wr = int(m.group(2))
        wr2 = m.group(3)
        if wr > 50:
            new_wr = flip_winrate(wr)
            if wr2:
                new_wr2 = flip_winrate(int(wr2))
                old = f"勝率約{wr}〜{wr2}%"
                new = f"勝率約{min(new_wr, new_wr2)}〜{max(new_wr, new_wr2)}%"
            else:
                old = f"勝率約{wr}%"
                new = f"勝率約{new_wr}%"
            return line.replace(old, new), old, new

    return None, None, None

fixed_count = 0
for filepath in sorted(glob.glob(MATCHUP_DIR)):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    changed = False
    new_lines = []
    for line in lines:
        result, old, new = fix_line(line)
        if result:
            new_lines.append(result)
            champ = filepath.split('/')[-2]
            print(f"  {champ}: {old} → {new}")
            fixed_count += 1
            changed = True
        else:
            new_lines.append(line)

    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

print(f"\n修正完了: {fixed_count}件")
