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
  4. サブ卒業 → そのレーンの missing/requeue 両キューから当該チャンプを掃除
                 （卒業＝再生成不要。matchups-sub.md の生成物は残し build-json が非表示化）

cron 経由: check-patch.sh の末尾から呼ばれる
手動実行: ./scripts/refresh-subrole-targets.py [--dry-run] [--skip-list]
  --skip-list: list-subrole-targets.sh をスキップして diff だけ計算
               （subrole-targets.json を手動編集した直後のテスト用）

冪等性: 同じ subrole-targets.json で再実行しても何も増えない（diff が空になる）
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path("/home/ojita/lol-guides-jp")
TARGETS_FILE = PROJECT_DIR / "scripts" / "subrole-targets.json"
TARGETS_PREV = PROJECT_DIR / "scripts" / "subrole-targets.json.prev"
LIST_SCRIPT = PROJECT_DIR / "scripts" / "list-subrole-targets.sh"
GEN_QUEUE_SCRIPT = PROJECT_DIR / "scripts" / "gen-subrole-queue.py"
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


def remove_from_queue(prefix: str, role: str, champ_id: str, dry_run: bool) -> None:
    """{prefix}-{role_suffix}.txt から champ_id が関与する行を削除する。

    prefix は "missing-subrole" / "requeue-subrole" を想定。

    卒業（サブから外れた）レーンの対面はもう生成不要。未生成キュー（missing）にも
    再生成キュー（requeue）にも当該チャンプの行が残っていると、cron が「もう使わない
    レーンの対面」を生成し続ける。卒業を検知した時点で両キューから掃除する。

    キューフォーマット: a_id|a_ja|b_id|b_ja|b_en||
    そのレーンで champ_id が a 側（field[0]）か b 側（field[2]）どちらかに居る行を消す。
    どちらの guide も「両者がそのレーンを実プレイする」前提なので、片方が卒業したら
    そのレーンの対面自体が成立しない。冪等（該当行が無ければ何もしない）。

    matchups-sub.md の該当セクションは削除しない（build-json が非表示化する。
    サブ復活時に冪等再表示できるよう生成物は残す）。
    """
    suffix = ROLE_TO_FILE_SUFFIX.get(role)
    if not suffix:
        log(f"WARN: 未知のロール '{role}'、{prefix} 掃除スキップ")
        return
    target = SCRIPTS_DIR / f"{prefix}-{suffix}.txt"
    if not target.exists():
        return
    with open(target, encoding="utf-8") as f:
        lines = f.read().splitlines()

    def involves(line: str) -> bool:
        fields = line.split("|")
        return len(fields) >= 3 and (fields[0] == champ_id or fields[2] == champ_id)

    kept = [ln for ln in lines if not involves(ln)]
    removed = len(lines) - len(kept)
    if removed == 0:
        return
    if dry_run:
        log(f"  → DRY-RUN: {target.name} から {champ_id} 関与 {removed} 行を削除（実行しない）")
        return
    with open(target, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + ("\n" if kept else ""))
    log(f"  → {target.name}: {champ_id} 関与 {removed} 行を削除")


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

    # Step 5: 卒業 → そのレーンのキューを掃除（missing / requeue 両方）
    #   旧実装は卒業対面を requeue に積み直していたが、これは誤り。卒業＝もうそのレーンで
    #   使わないので再生成は不要。逆に積むと build-json が非表示にしたサブを cron が作り直し、
    #   表示と生成が永久にイタチごっこになる。卒業を検知したら両キューから掃除する。
    #   matchups-sub.md の生成物は残す（build-json が非表示化。サブ復活時に冪等再表示）。
    if drops:
        log("INFO: 卒業エントリのキューを掃除（missing / requeue 両方）")
        for champ_id, roles in drops.items():
            for role in roles:
                remove_from_queue("missing-subrole", role, champ_id, args.dry_run)
                remove_from_queue("requeue-subrole", role, champ_id, args.dry_run)

    log("===== refresh-subrole-targets 完了 =====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
