#!/usr/bin/env python3
"""replace-section-text.py
matchups.md の特定セクションをテキスト入力で置き換える

Usage:
  echo "$entry_text" | python3 scripts/replace-section-text.py <champ_id> <opp_ja> <opp_en>

  - stdin から生テキスト（## vs ... で始まるエントリ）を受け取る
  - セクションが見つからない場合はファイル末尾にフォールバック追記
"""

import os
import re
import sys

CHAMP_DIR = os.path.join(os.path.dirname(__file__), "..", "champions")

champ_id = sys.argv[1]
opp_ja = sys.argv[2]
opp_en = sys.argv[3]

new_content = sys.stdin.read().strip()

path = os.path.join(CHAMP_DIR, champ_id, "matchups.md")
if not os.path.isfile(path):
    print(f"ERROR: {path} が見つかりません", file=sys.stderr)
    sys.exit(1)

content = open(path, encoding="utf-8").read()
header = f"## vs {opp_ja}（{opp_en}）"
pat = re.compile(
    r"^" + re.escape(header) + r"\n.*?(?=\n## |\Z)", re.MULTILINE | re.DOTALL
)

if pat.search(content):
    result = pat.sub(new_content, content)
    open(path, "w", encoding="utf-8").write(result)
    print(f"replaced: {champ_id}/matchups.md  vs {opp_ja}")
else:
    open(path, "a", encoding="utf-8").write(f"\n{new_content}\n")
    print(f"appended (fallback): {champ_id}/matchups.md  vs {opp_ja}")
