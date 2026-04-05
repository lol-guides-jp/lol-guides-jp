#!/usr/bin/env python3
"""list-regen-targets.py
scan-broken.py --tsv の出力を受け取り、再生成対象を tier 順・上限件数でフィルタして stdout に返す

Usage:
  python3 scripts/scan-broken.py --tsv | python3 scripts/list-regen-targets.py --tier all --batch 3

出力形式: scan-broken.py --tsv と同じ（ヘッダーなし）
"""

import sys

tier  = "all"
batch = 10

args = sys.argv[1:]
i = 0
while i < len(args):
    if args[i] == "--tier":
        tier = args[i+1]; i += 2
    elif args[i] == "--batch":
        batch = int(args[i+1]); i += 2
    else:
        i += 1

lines = [l for l in sys.stdin.read().splitlines() if l]
data  = lines[1:] if lines and lines[0].startswith("champ_id") else lines

broken  = [l for l in data if l.split('\t')[3] == 'broken']
quality = [l for l in data if l.split('\t')[3] == 'quality']

if tier == "broken":
    ordered = broken
elif tier == "quality":
    ordered = quality
else:
    ordered = broken + quality  # broken を先に処理

print('\n'.join(ordered[:batch]))
