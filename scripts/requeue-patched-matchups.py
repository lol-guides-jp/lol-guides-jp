#!/usr/bin/env python3
# requeue-patched-matchups.py
# パッチノートで変更されたチャンピオンの既存matchupをmissing-*.txtの先頭に再投入する
# 複数パッチを渡すと変更チャンピオンを合算・重複排除してから1回だけキューに追加する
#
# 使い方:
#   python3 scripts/requeue-patched-matchups.py 26.8
#   python3 scripts/requeue-patched-matchups.py 26.7 26.8        # 複数パッチ（重複排除）
#   python3 scripts/requeue-patched-matchups.py 26.7 26.8 --dry-run

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_DIR / "scripts"

ROLE_TO_MISSING = {
    "トップレーン": "missing-トップ.txt",
    "ミッドレーン": "missing-ミッド.txt",
    "ジャングル": "missing-ジャング.txt",
    "ADC": "missing-ADC.txt",
    "サポート": "missing-サポート.txt",
}


def load_champions() -> tuple[dict, dict]:
    with open(PROJECT_DIR / "docs" / "data.json", encoding="utf-8") as f:
        data = json.load(f)
    id_map, ja_map = {}, {}
    for champ in data.get("champions", []):
        cid = champ["id"]
        id_map[cid] = champ
        ja_map[champ["ja"]] = cid
    return id_map, ja_map


def find_changed_ids(patch_version: str, id_map: dict) -> set[str]:
    """パッチノートに英語名が登場するチャンピオンIDのsetを返す。"""
    patch_file = PROJECT_DIR / "patches" / f"{patch_version}.md"
    if not patch_file.exists():
        print(f"ERROR: patches/{patch_version}.md が見つかりません", file=sys.stderr)
        sys.exit(1)
    content = patch_file.read_text(encoding="utf-8")
    return {
        champ["id"]
        for champ in id_map.values()
        if re.search(rf'\b{re.escape(champ["en"])}\b', content, re.IGNORECASE)
    }


def get_existing_opponents(champ_id: str, ja_map: dict) -> list[str]:
    matchup_file = PROJECT_DIR / "champions" / champ_id / "matchups.md"
    if not matchup_file.exists():
        return []
    content = matchup_file.read_text(encoding="utf-8")
    opp_ids = []
    for ja_name in re.findall(r'^## vs (.+?)（', content, re.MULTILINE):
        opp_id = ja_map.get(ja_name)
        if opp_id:
            opp_ids.append(opp_id)
        else:
            print(f"WARN: '{ja_name}' がdata.jsonに見つかりません", file=sys.stderr)
    return opp_ids


def load_existing_missing(role: str) -> set[str]:
    fname = ROLE_TO_MISSING.get(role)
    if not fname:
        return set()
    missing_file = SCRIPTS_DIR / fname
    if not missing_file.exists():
        return set()
    return set(l for l in missing_file.read_text(encoding="utf-8").splitlines() if l.strip())


def prepend_to_missing(role: str, entries: list[str], dry_run: bool) -> int:
    """missing-{role}.txt の先頭にエントリを挿入する（パッチ対応を優先処理するため）。"""
    fname = ROLE_TO_MISSING.get(role)
    if not fname:
        return 0
    missing_file = SCRIPTS_DIR / fname
    if dry_run:
        for e in entries:
            print(f"[DRY-RUN] {fname} の先頭に挿入: {e}")
        return len(entries)
    existing = missing_file.read_text(encoding="utf-8") if missing_file.exists() else ""
    missing_file.write_text("\n".join(entries) + "\n" + existing, encoding="utf-8")
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description="パッチ対象チャンプのmatchupをmissingに再投入")
    parser.add_argument("patch_versions", nargs="+", help="パッチバージョン (例: 26.7 26.8)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    id_map, ja_map = load_champions()

    # 全パッチの変更チャンピオンを合算・重複排除
    all_changed: set[str] = set()
    for pv in args.patch_versions:
        changed = find_changed_ids(pv, id_map)
        print(f"INFO: パッチ{pv}: {len(changed)}体変更")
        all_changed |= changed

    if not all_changed:
        print("INFO: 変更チャンピオンなし。終了")
        return

    print(f"INFO: 合算・重複排除後 {len(all_changed)}体: {', '.join(sorted(all_changed))}")

    total_added = 0
    for champ_id in sorted(all_changed):
        champ = id_map[champ_id]
        role = champ["role"]
        existing_missing = load_existing_missing(role)

        opp_ids = get_existing_opponents(champ_id, ja_map)
        if not opp_ids:
            print(f"INFO: {champ['ja']}: 既存matchupなし。スキップ")
            continue

        entries_to_add = []
        for opp_id in opp_ids:
            opp = id_map.get(opp_id)
            if not opp:
                continue
            entry = f"{champ_id}|{champ['ja']}|{opp_id}|{opp['ja']}|{opp['en']}||"
            if entry not in existing_missing:
                entries_to_add.append(entry)

        if not entries_to_add:
            print(f"INFO: {champ['ja']}: 全対面が既にmissingに存在。スキップ")
            continue

        added = prepend_to_missing(role, entries_to_add, args.dry_run)
        total_added += added
        print(f"INFO: {champ['ja']}（{role}）: {added}件")

    print(f"INFO: 合計 {total_added}件 をmissing-*.txtの先頭に追加")


if __name__ == "__main__":
    main()
