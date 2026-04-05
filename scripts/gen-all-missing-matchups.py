#!/usr/bin/env python3
"""
gen-all-missing-matchups.py
同じロールのチャンピオン全員分の対面を対象として
matchups.md に未掲載の対面リストを missing-*.txt に出力する。

使い方: python3 scripts/gen-all-missing-matchups.py
"""

import json
import os

DATA = json.load(open("docs/data.json"))

# role → チャンピオンリスト
by_role = {}
for c in DATA["champions"]:
    r = c["role"]
    by_role.setdefault(r, []).append(c)

# 各チャンプに対して、同ロールの他チャンプとの未対面を列挙
by_role_missing = {}
total = 0

for champ in DATA["champions"]:
    role = champ["role"]
    existing_ids = set(m["opponentId"] for m in champ["matchups"])

    missing = []
    for opp in by_role[role]:
        if opp["id"] == champ["id"]:
            continue
        if opp["id"] not in existing_ids:
            missing.append({
                "opp_id": opp["id"],
                "opp_ja": opp["ja"],
                "opp_en": opp["en"],
            })

    if missing:
        by_role_missing.setdefault(role, [])
        for m in missing:
            by_role_missing[role].append({
                "champ_id": champ["id"],
                "champ_ja": champ["ja"],
                "champ_en": champ["en"],
                "opp_id": m["opp_id"],
                "opp_ja": m["opp_ja"],
                "opp_en": m["opp_en"],
            })
            total += 1

# ロール名 → ファイル名サフィックスのマッピング
ROLE_SUFFIX = {
    "トップレーン": "トップ",
    "ミッドレーン": "ミッド",
    "ジャングル": "ジャング",
    "ADC": "ADC",
    "サポート": "サポート",
}

for role, entries in by_role_missing.items():
    suffix = ROLE_SUFFIX.get(role, role)
    fname = f"scripts/missing-{suffix}.txt"
    lines = []
    for e in entries:
        lines.append(
            f"{e['champ_id']}|{e['champ_ja']}|{e['opp_id']}|{e['opp_ja']}|{e['opp_en']}||"
        )
    with open(fname, "w") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    print(f"{fname}: {len(lines)}件")

print(f"\n合計: {total}件の未対面 → scripts/missing-*.txt")
