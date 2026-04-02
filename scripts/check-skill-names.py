#!/usr/bin/env python3
"""matchups.md内のスキル名をdata.jsonのスキルデータと突合し、不一致を検出する。

検出対象:
- 「〇〇のQ（スキル名）」形式で、スキル名がdata.jsonと異なるもの
- 自チャンプ・相手チャンプ両方をチェック
"""

import json
import re
import glob
import sys

DATA_PATH = "/home/ojita/lol-guides-jp/docs/data.json"
MATCHUP_GLOB = "/home/ojita/lol-guides-jp/champions/*/matchups.md"

with open(DATA_PATH, encoding="utf-8") as f:
    data = json.load(f)

# チャンプ名 → {Q: スキル名, W: ...} の辞書
skill_db = {}
# 英語名/ID → 日本語名のマッピング
name_map = {}
for c in data["champions"]:
    if not c.get("skills"):
        continue
    skills = {}
    for s in c["skills"]:
        skills[s["key"]] = s["name"]
    skill_db[c["ja"]] = skills
    # 短縮名・別名も登録
    name_map[c["en"]] = c["ja"]
    name_map[c["ja"]] = c["ja"]

# matchups.mdで使われる略称パターン（例: モルデ→モルデカイザー）
# 部分一致で探す
def find_champ_name(text):
    """テキストに含まれるチャンプ名を特定"""
    # 完全一致を優先
    if text in skill_db:
        return text
    # 部分一致（前方一致）
    for ja_name in skill_db:
        if ja_name.startswith(text) or text.startswith(ja_name):
            return ja_name
    # 略称パターン
    abbrevs = {
        "モルデ": "モルデカイザー",
        "セト": "セト",
        "エイトロックス": "エイトロックス",
        "TF": "ツイステッド・フェイト",
        "こちら": None,  # 自チャンプ参照
        "自分": None,
    }
    return abbrevs.get(text)

# スキルキーパターン
# スキル名の後に「、CD○秒」等の補足がつくパターンを考慮
SKILL_PATTERN = re.compile(r'(\S+?)の([QWER])（([^）、]+)(?:、[^）]*)?）')

issues = []
fix_mode = "--fix" in sys.argv

for filepath in sorted(glob.glob(MATCHUP_GLOB)):
    champ_id = filepath.split("/")[-2]
    # 自チャンプの日本語名を取得
    self_champ = None
    for c in data["champions"]:
        if c["id"] == champ_id:
            self_champ = c["ja"]
            break

    with open(filepath, encoding="utf-8") as f:
        lines = f.readlines()

    changed = False
    new_lines = []
    for line_no, line in enumerate(lines, 1):
        new_line = line
        for m in SKILL_PATTERN.finditer(line):
            ref_name = m.group(1)
            key = m.group(2)
            written_name = m.group(3).strip()

            # チャンプ特定
            champ_ja = find_champ_name(ref_name)
            if champ_ja is None and ref_name == "こちら":
                champ_ja = self_champ
            if champ_ja is None:
                continue
            if champ_ja not in skill_db:
                continue

            correct_name = skill_db[champ_ja].get(key)
            if correct_name is None:
                continue

            # 一致チェック（正式名が読点含みで前方一致する場合はOK）
            if written_name != correct_name and not correct_name.startswith(written_name):
                issues.append({
                    "file": filepath,
                    "line": line_no,
                    "champ": champ_ja,
                    "key": key,
                    "written": written_name,
                    "correct": correct_name,
                })
                if fix_mode:
                    old = f"{key}（{written_name}"
                    new = f"{key}（{correct_name}"
                    new_line = new_line.replace(old, new, 1)
                    changed = True

        new_lines.append(new_line)

    if fix_mode and changed:
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

if issues:
    print(f"スキル名不一致: {len(issues)}件\n")
    for iss in issues:
        champ_id = iss["file"].split("/")[-2]
        print(f"  {champ_id}:{iss['line']}  {iss['champ']}の{iss['key']}  "
              f"「{iss['written']}」→ 正:「{iss['correct']}」")
    if fix_mode:
        print(f"\n{len(issues)}件を自動修正しました")
    else:
        print(f"\n自動修正するには: python3 scripts/check-skill-names.py --fix")
else:
    print("スキル名不一致: 0件")
