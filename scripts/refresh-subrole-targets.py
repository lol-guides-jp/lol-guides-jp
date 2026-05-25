#!/usr/bin/env python3
"""refresh-subrole-targets.py

サブロール判定を再生成し、前回 JSON との diff を取って、サブロール対面キュー
(missing-subrole-{role}.txt / requeue-subrole-{role}.txt) を更新する。

役割（オーケストレータ）:
  1. list-subrole-targets.sh を実行して subrole-targets.json を更新
  2. subrole-targets.json.prev との diff を計算
     - 新規サブ化: チャンプ X が新たにロール R を sub に追加
     - サブ卒業: チャンプ X が sub からロール R を外した
  3. 新規サブ化 → gen-subrole-queue.py を呼んで missing-subrole-{role}.txt に追加
  4. サブ卒業 → champions/{champ}/matchups-sub.md の該当ロールセクションを
                 抽出して requeue-subrole-{role}.txt に積む

cron 経由: check-patch.sh の末尾から呼ばれる
手動実行: ./scripts/refresh-subrole-targets.py [--dry-run] [--skip-list]
  --skip-list: list-subrole-targets.sh をスキップして diff だけ計算
               （subrole-targets.json を手動編集した直後のテスト用）

冪等性: 同じ subrole-targets.json で再実行しても何も増えない（diff が空になる）
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path("/home/ojita/lol-guides-jp")
TARGETS_FILE = PROJECT_DIR / "scripts" / "subrole-targets.json"
TARGETS_PREV = PROJECT_DIR / "scripts" / "subrole-targets.json.prev"
LIST_SCRIPT = PROJECT_DIR / "scripts" / "list-subrole-targets.sh"
GEN_QUEUE_SCRIPT = PROJECT_DIR / "scripts" / "gen-subrole-queue.py"
CHAMPIONS_DIR = PROJECT_DIR / "champions"
SCRIPTS_DIR = PROJECT_DIR / "scripts"

ROLE_TO_FILE_SUFFIX = {
    "トップレーン": "トップ",
    "ジャングル": "ジャング",
    "ミッドレーン": "ミッド",
    "ADC": "ADC",
    "サポート": "サポート",
}


def log(msg: str) -> None:
    from datetime import datetime
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def load_targets(path: Path) -> dict:
    if not path.exists():
        return {"champions": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compute_diff(old: dict, new: dict) -> tuple[dict, dict]:
    """旧 → 新 の差分を計算。
    返り値:
      new_subs: {champ_id: [role, ...]}  新規にサブ化したロール
      drops:    {champ_id: [role, ...]}  サブから卒業したロール
    """
    old_champs = old.get("champions", {})
    new_champs = new.get("champions", {})

    new_subs: dict[str, list[str]] = {}
    drops: dict[str, list[str]] = {}

    for champ_id, new_entry in new_champs.items():
        new_sub = set(new_entry.get("sub", []))
        old_entry = old_champs.get(champ_id, {})
        old_sub = set(old_entry.get("sub", []))

        added = new_sub - old_sub
        removed = old_sub - new_sub

        if added:
            new_subs[champ_id] = sorted(added)
        if removed:
            drops[champ_id] = sorted(removed)

    # 旧 JSON にあって新 JSON に無いチャンプ（リリース削除など）はスキップ

    return new_subs, drops


def extract_opponents_from_matchups_sub(champ_id: str, role: str) -> list[tuple[str, str, str]]:
    """champions/{champ_id}/matchups-sub.md から指定ロールセクションの対面相手を抽出。
    返り値: [(opp_id, opp_ja, opp_en), ...]
    matchups-sub.md が存在しない・該当ロールが無い場合は空リスト。
    """
    sub_file = CHAMPIONS_DIR / champ_id / "matchups-sub.md"
    if not sub_file.exists():
        return []

    with open(sub_file, encoding="utf-8") as f:
        content = f.read()

    # ## {role} セクションを抽出
    role_pattern = re.compile(
        rf"^## {re.escape(role)}\s*$(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = role_pattern.search(content)
    if not m:
        return []

    section = m.group(1)
    # ### vs <name> (en名) — ja名と en名を抽出
    # 例: "### vs ヴェイガー（Veigar）" or "### vs Veigar"
    opp_pattern = re.compile(r"^### vs (.+?)(?:（(.+?)）)?\s*$", re.MULTILINE)
    opponents: list[tuple[str, str, str]] = []
    for om in opp_pattern.finditer(section):
        ja = om.group(1).strip()
        en = (om.group(2) or ja).strip()
        # id は champions/ ディレクトリから en 名で逆引き（ない場合は空）
        opp_id = lookup_champ_id_by_en(en) or lookup_champ_id_by_ja(ja) or ""
        if opp_id:
            opponents.append((opp_id, ja, en))
    return opponents


def lookup_champ_id_by_en(en: str) -> str | None:
    """docs/data.json から en 名で id を逆引き。"""
    data_file = PROJECT_DIR / "docs" / "data.json"
    if not data_file.exists():
        return None
    with open(data_file, encoding="utf-8") as f:
        data = json.load(f)
    en_lower = en.lower().replace(" ", "").replace("'", "").replace(".", "")
    for c in data.get("champions", []):
        cen = (c.get("en") or c.get("id") or "").lower().replace(" ", "").replace("'", "").replace(".", "")
        if cen == en_lower:
            return c.get("id")
    return None


def lookup_champ_id_by_ja(ja: str) -> str | None:
    data_file = PROJECT_DIR / "docs" / "data.json"
    if not data_file.exists():
        return None
    with open(data_file, encoding="utf-8") as f:
        data = json.load(f)
    for c in data.get("champions", []):
        if c.get("ja") == ja:
            return c.get("id")
    return None


def append_to_requeue(role: str, lines: list[str], dry_run: bool) -> None:
    """requeue-subrole-{role_suffix}.txt に行を追加（重複除去）。"""
    suffix = ROLE_TO_FILE_SUFFIX.get(role)
    if not suffix:
        log(f"WARN: 未知のロール '{role}'、スキップ")
        return
    target = SCRIPTS_DIR / f"requeue-subrole-{suffix}.txt"
    existing = set()
    if target.exists():
        with open(target, encoding="utf-8") as f:
            existing = set(f.read().splitlines())
    new_lines = [ln for ln in lines if ln not in existing]
    if not new_lines:
        log(f"  → {target.name}: 追加なし（既存と重複）")
        return
    if dry_run:
        log(f"  → DRY-RUN: {target.name} に {len(new_lines)} 行追加（実行しない）")
        for ln in new_lines[:3]:
            log(f"      {ln}")
        return
    with open(target, "a", encoding="utf-8") as f:
        for ln in new_lines:
            f.write(ln + "\n")
    log(f"  → {target.name}: {len(new_lines)} 行追加")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="ファイル変更を行わず差分のみ表示")
    parser.add_argument(
        "--skip-list",
        action="store_true",
        help="list-subrole-targets.sh をスキップ（既存 subrole-targets.json で diff だけ計算）",
    )
    args = parser.parse_args()

    log("===== refresh-subrole-targets 開始 =====")

    # Step 1: list-subrole-targets.sh を実行（または skip）
    if args.skip_list:
        log("INFO: --skip-list 指定。list-subrole-targets.sh をスキップ")
    else:
        log("INFO: list-subrole-targets.sh 実行中...")
        cmd = [str(LIST_SCRIPT)]
        if args.dry_run:
            cmd.append("--dry-run")
        result = subprocess.run(cmd, capture_output=False)
        if result.returncode != 0:
            log("ERROR: list-subrole-targets.sh 失敗")
            return 1
        if args.dry_run:
            log("INFO: DRY-RUN 完了。diff 計算はスキップ")
            return 0

    # Step 2: 旧 / 新 JSON ロード
    old = load_targets(TARGETS_PREV)
    new = load_targets(TARGETS_FILE)

    if not new.get("champions"):
        log("ERROR: subrole-targets.json が空。中止")
        return 1

    # Step 3: diff 計算
    new_subs, drops = compute_diff(old, new)

    log(f"INFO: diff 結果 — 新規サブ化 {sum(len(v) for v in new_subs.values())} 件 / 卒業 {sum(len(v) for v in drops.values())} 件")

    if not new_subs and not drops:
        log("INFO: 変更なし。終了")
        return 0

    # Step 4: 新規サブ化 → gen-subrole-queue.py に委譲
    if new_subs:
        log("INFO: 新規サブ化エントリを gen-subrole-queue.py に渡す")
        payload = json.dumps({"new_subs": new_subs}, ensure_ascii=False)
        cmd = ["python3", str(GEN_QUEUE_SCRIPT), "--from-stdin"]
        if args.dry_run:
            cmd.append("--dry-run")
        result = subprocess.run(cmd, input=payload, text=True, capture_output=False)
        if result.returncode != 0:
            log("ERROR: gen-subrole-queue.py 失敗")
            return 1

    # Step 5: 卒業 → matchups-sub.md から該当対面を requeue に積む
    if drops:
        log("INFO: 卒業エントリを requeue-subrole-{role}.txt に積む")
        for champ_id, roles in drops.items():
            for role in roles:
                opponents = extract_opponents_from_matchups_sub(champ_id, role)
                if not opponents:
                    log(f"  {champ_id} ({role}): matchups-sub.md に対面なし、スキップ")
                    continue
                champ_ja = new.get("champions", {}).get(champ_id, {}).get("ja") or champ_id
                # キューフォーマット: id_a|ja_a|id_b|ja_b|en_b||
                lines = [f"{champ_id}|{champ_ja}|{opp_id}|{opp_ja}|{opp_en}||"
                         for opp_id, opp_ja, opp_en in opponents]
                append_to_requeue(role, lines, args.dry_run)

    log("===== refresh-subrole-targets 完了 =====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
