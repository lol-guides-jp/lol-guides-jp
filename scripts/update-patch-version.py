#!/usr/bin/env python3
# update-patch-version.py
# 全チャンピオンページのパッチバージョン表記を新バージョンに一括書き換えする (L1)
# 旧バージョンはファイルから自動検出するため、複数バージョンが混在していても対応できる
#
# 使い方:
#   python3 scripts/update-patch-version.py 26.8
#   python3 scripts/update-patch-version.py 26.8 --dry-run

import argparse
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

PATCH_PATTERN = re.compile(r'パッチ(\d+\.\d+)')


def process_file(path: Path, new_version: str, dry_run: bool) -> int:
    """ファイル内の パッチX.Y（新バージョン以外）を パッチNEW に置換する。変更件数を返す。"""
    original = path.read_text(encoding="utf-8")

    def replacer(m: re.Match) -> str:
        return f"パッチ{new_version}" if m.group(1) != new_version else m.group(0)

    updated = PATCH_PATTERN.sub(replacer, original)
    count = sum(1 for o, n in zip(original.split("パッチ"), updated.split("パッチ")) if o != n)
    # 変更件数を正確に数える
    count = len(PATCH_PATTERN.findall(original)) - original.count(f"パッチ{new_version}")

    if updated == original:
        return 0
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="全ページのパッチバージョン表記を一括更新")
    parser.add_argument("new_version", help="新パッチバージョン (例: 26.8)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    new = args.new_version

    targets = sorted(
        list((PROJECT_DIR / "champions").glob("*/guide.md"))
        + list((PROJECT_DIR / "champions").glob("*/matchups.md"))
    )

    total_files = 0
    total_replacements = 0
    for path in targets:
        count = process_file(path, new, args.dry_run)
        if count > 0:
            prefix = "[DRY-RUN] " if args.dry_run else ""
            print(f"{prefix}INFO: {path.relative_to(PROJECT_DIR)}: {count}件置換")
            total_files += 1
            total_replacements += count

    if total_files == 0:
        print(f"INFO: 全ファイルが既にパッチ{new}。更新不要")
    else:
        print(f"INFO: {total_files}ファイル / {total_replacements}件 → パッチ{new} に更新完了")


if __name__ == "__main__":
    main()
