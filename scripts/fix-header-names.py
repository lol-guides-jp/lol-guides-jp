#!/usr/bin/env python3
"""fix-header-names.py
matchups.md のヘッダー表記を正規化する（API不要・$0）

修正対象:
  Case B: `## vs {en}（{ja}）` → `## vs {ja}（{en}）`  （991件: 英語↔日本語逆転）
  Case C: 誤ったスペルの日本語名 → 正しい日本語名              （例: アートロックス→エイトロックス）
  Case A: `## vs {en}（{en}）` → `## vs {ja}（{en}）`  （英語のみ）

使い方:
  python3 scripts/fix-header-names.py              # 全件修正
  python3 scripts/fix-header-names.py --dry-run    # ドライラン
"""

import os, re, json, sys

CHAMP_DIR = os.path.join(os.path.dirname(__file__), "..", "champions")
DATA_FILE  = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")

DATA    = json.load(open(DATA_FILE))
en_to_ja = {c["en"]: c["ja"] for c in DATA["champions"]}
ja_to_en = {c["ja"]: c["en"] for c in DATA["champions"]}
ja_set   = {c["ja"] for c in DATA["champions"]}
en_set   = {c["en"] for c in DATA["champions"]}

dry_run = "--dry-run" in sys.argv

HEADER_PAT = re.compile(r'^(## vs )(.+?)（(.+?)）', re.MULTILINE)

def fix_header(m):
    prefix, field1, field2 = m.group(1), m.group(2).strip(), m.group(3).strip()

    # Case B: field1=英語, field2=日本語 → swap
    if field1 in en_set and field2 in ja_set:
        return f"{prefix}{field2}（{field1}）"

    # Case A: field1=英語, field2=英語 → ja（en）
    if field1 in en_set and field2 in en_set:
        ja = en_to_ja.get(field1)
        if ja:
            return f"{prefix}{ja}（{field1}）"

    # Case A2: field1=英語, field2=英語で同じ（"Janna（Janna）"型）
    if field1 in en_set:
        ja = en_to_ja.get(field1)
        if ja:
            return f"{prefix}{ja}（{field1}）"

    # Case C: field1=誤りのある日本語（ja_setにない）, field2=英語
    if field1 not in ja_set and field2 in en_set:
        ja = en_to_ja.get(field2)
        if ja and ja != field1:
            return f"{prefix}{ja}（{field2}）"

    return m.group(0)  # 変更なし

total_files = 0
total_fixes = 0

for champ_dir in sorted(os.listdir(CHAMP_DIR)):
    path = os.path.join(CHAMP_DIR, champ_dir, "matchups.md")
    if not os.path.isfile(path):
        continue
    with open(path) as f:
        content = f.read()

    new_content = HEADER_PAT.sub(fix_header, content)
    if new_content == content:
        continue

    fixes = sum(1 for a, b in zip(content.splitlines(), new_content.splitlines()) if a != b)
    total_files += 1
    total_fixes += fixes

    if dry_run:
        print(f"[DRY] {champ_dir}/matchups.md ({fixes}件)")
        for old, new in zip(content.splitlines(), new_content.splitlines()):
            if old != new:
                print(f"  - {old.strip()}")
                print(f"  + {new.strip()}")
    else:
        with open(path, "w") as f:
            f.write(new_content)
        print(f"修正: {champ_dir}/matchups.md ({fixes}件)")

print(f"\n完了: {total_files}ファイル / {total_fixes}件修正{'（ドライラン）' if dry_run else ''}")
