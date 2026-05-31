#!/usr/bin/env python3
"""gen-champion-queue.py

新規チャンピオン1体について、同じメインロールの全チャンプとの対面ペアを
missing-{role}.txt に追記する。対面ガイド生成（cron-add-matchups → add-matchups.sh）が
最優先で消化する（missing は requeue より先に処理される 4 段切替の先頭）。

使い方:
  python3 scripts/gen-champion-queue.py <slug>

前提:
  docs/data.json に <slug> が登録済みであること（build-json.js 実行後に呼ぶ）。
  role / ja / en は data.json から引く。

ペア生成:
  対象 A と「A と同じ role を持つ既存チャンプ B」全員でペアを作る。自分自身は除く。
  対面ガイドは A/B 同時生成（gen-matchup が entry_a/entry_b を両方返す）ため、
  片方向（A|...|B）だけ積めば双方の matchups.md が埋まる。

重複除去:
  - 既存キュー行に同じペアがある場合はスキップ
  - 逆順ペア（B|...|A）が既出ならスキップ（複数新チャンが同ロールのときの二重生成を防ぐ）
  キューフォーマット（既存 missing-*.txt と同じ）: {id_a}|{ja_a}|{id_b}|{ja_b}|{en_b}||
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

PROJECT_DIR = Path("/home/ojita/lol-guides-jp")
DATA_FILE = PROJECT_DIR / "docs" / "data.json"
SCRIPTS_DIR = PROJECT_DIR / "scripts"

ROLE_TO_SUFFIX = {
    "トップレーン": "トップ",
    "ジャングル": "ジャング",
    "ミッドレーン": "ミッド",
    "ADC": "ADC",
    "サポート": "サポート",
}


def norm_pair(a: str, b: str) -> tuple[str, str]:
    """方向に依存しない正規化ペアキー。"""
    return (a, b) if a <= b else (b, a)


def main() -> int:
    if len(sys.argv) < 2:
        print("ERROR: slug を引数で渡す", file=sys.stderr)
        return 1
    slug = sys.argv[1]

    champions = json.loads(DATA_FILE.read_text(encoding="utf-8"))["champions"]
    by_id = {c["id"]: c for c in champions}
    if slug not in by_id:
        print(f"ERROR: {slug} は data.json に未登録。build-json.js を先に実行する", file=sys.stderr)
        return 1

    target = by_id[slug]
    role = target.get("role", "")
    suffix = ROLE_TO_SUFFIX.get(role)
    if not suffix:
        print(f"ERROR: role が不正（{role!r}）", file=sys.stderr)
        return 1

    queue_file = SCRIPTS_DIR / f"missing-{suffix}.txt"

    # 既存キュー行の正規化ペア集合
    seen: set[tuple[str, str]] = set()
    existing_lines = []
    if queue_file.exists():
        for line in queue_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            existing_lines.append(line)
            cols = line.split("|")
            if len(cols) >= 3:
                seen.add(norm_pair(cols[0], cols[2]))

    # 同ロールの相手を列挙（自分自身は除く）
    peers = [c for c in champions if c.get("role") == role and c["id"] != slug]

    new_lines = []
    for b in sorted(peers, key=lambda c: c["id"]):
        pair = norm_pair(slug, b["id"])
        if pair in seen:
            continue
        seen.add(pair)
        new_lines.append(f"{slug}|{target['ja']}|{b['id']}|{b['ja']}|{b['en']}||")

    if not new_lines:
        print(f"INFO: {slug}（{role}）の新規対面ペアなし（全て既出）", file=sys.stderr)
        return 0

    with queue_file.open("a", encoding="utf-8") as f:
        for line in new_lines:
            f.write(line + "\n")

    print(f"INFO: {slug}（{role}）対面 {len(new_lines)}件を {queue_file.name} に追加", file=sys.stderr)
    print(len(new_lines))  # stdout は件数のみ
    return 0


if __name__ == "__main__":
    sys.exit(main())
