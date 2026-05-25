#!/usr/bin/env python3
"""gen-subrole-queue.py

subrole-targets.json をもとに、サブロール対面キュー
(missing-subrole-{role}.txt) を生成・追記する。

呼び出しモード:
  1) --full          全 sub エントリを処理して missing-subrole-{role}.txt を再生成
                     （初回投入時に使う。既存キューは上書きされる）
  2) --from-stdin    stdin から {"new_subs": {champ_id: [role, ...]}} を受け取り、
                     その差分だけを missing-subrole-{role}.txt に追記する
                     （refresh-subrole-targets.py から呼ばれる）

ペア生成ロジック:
  対象チャンプ A がサブロール R で起用される場合、
  「ロール R に居る全チャンプ（main または sub に R を含む全員）」を相手にペアを生成する。
  自分自身（A）とは生成しない。
  ロール対応マップは subrole-targets.json の champions[*].main + champions[*].sub から動的に構築。

キューフォーマット（既存 missing-*.txt と同じ）:
  {id_a}|{ja_a}|{id_b}|{ja_b}|{en_b}||

重複除去:
  - 既存キューに同じ a|b ペアが存在する場合はスキップ
  - matchups-sub.md に既に生成済みのペアは missing には積まない
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

PROJECT_DIR = Path("/home/ojita/lol-guides-jp")
TARGETS_FILE = PROJECT_DIR / "scripts" / "subrole-targets.json"
SCRIPTS_DIR = PROJECT_DIR / "scripts"
CHAMPIONS_DIR = PROJECT_DIR / "champions"

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


def load_targets() -> dict:
    with open(TARGETS_FILE, encoding="utf-8") as f:
        return json.load(f)


def already_in_matchups_sub(champ_id: str, opp_id: str, role: str) -> bool:
    """champions/{champ_id}/matchups-sub.md の {role} セクションに opp が既にあるか。
    まだ生成前のフェーズ4ではほぼ False になる想定。"""
    sub_file = CHAMPIONS_DIR / champ_id / "matchups-sub.md"
    if not sub_file.exists():
        return False
    with open(sub_file, encoding="utf-8") as f:
        content = f.read()
    # 簡易判定: opp_id を含む `### vs` 行があるか（部分一致）
    # 厳密にやるならロールセクションを抽出してから検索すべきだが、保守的に全体検索でOK
    # （別ロールに同じ opp が出ても重複ペアにはならないため）
    return opp_id in content


def existing_queue_pairs(suffix: str) -> set[tuple[str, str]]:
    """missing-subrole-{suffix}.txt の既存ペアを (a_id, b_id) のセットで返す。"""
    target = SCRIPTS_DIR / f"missing-subrole-{suffix}.txt"
    if not target.exists():
        return set()
    pairs = set()
    with open(target, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("|")
            if len(parts) >= 4:
                pairs.add((parts[0], parts[2]))
    return pairs


def build_role_to_champs(targets: dict) -> dict[str, list[dict]]:
    """subrole-targets.json から「ロール R に居る全チャンプ」を集める。
    main または sub に R を含む全員を集める（重複は1人にまとめる）。
    返り値: {role: [{id, ja, en}, ...]}（id 順でソート）
    """
    champions = targets.get("champions", {})
    role_map: dict[str, dict[str, dict]] = {}  # role -> {id: entry}

    for champ_id, entry in champions.items():
        roles = list(entry.get("main", [])) + list(entry.get("sub", []))
        for r in roles:
            role_map.setdefault(r, {})[champ_id] = {
                "id": champ_id,
                "ja": entry.get("ja", ""),
                "en": entry.get("en", ""),
            }
    return {r: sorted(d.values(), key=lambda x: x["id"]) for r, d in role_map.items()}


def build_pairs(
    new_subs: dict[str, list[str]],
    targets: dict,
) -> dict[str, list[str]]:
    """new_subs から、ロール別の追加キュー行を生成。
    返り値: {role: [queue_line, ...]}
    """
    champions = targets.get("champions", {})
    role_to_champs = build_role_to_champs(targets)

    queue: dict[str, list[str]] = {}

    for champ_id, sub_roles in new_subs.items():
        champ_entry = champions.get(champ_id, {})
        ja_a = champ_entry.get("ja") or champ_id
        for role in sub_roles:
            opponents = role_to_champs.get(role, [])
            if not opponents:
                log(f"WARN: ロール '{role}' に居るチャンプが見つからない、{champ_id} スキップ")
                continue
            lines = []
            for opp in opponents:
                opp_id = opp.get("id", "")
                if not opp_id or opp_id == champ_id:
                    continue
                if already_in_matchups_sub(champ_id, opp_id, role):
                    continue
                line = f"{champ_id}|{ja_a}|{opp_id}|{opp.get('ja', '')}|{opp.get('en', '')}||"
                lines.append(line)
            if lines:
                queue.setdefault(role, []).extend(lines)

    return queue


def write_queue(queue: dict[str, list[str]], mode: str, dry_run: bool) -> None:
    """mode: 'append' or 'overwrite'"""
    if not queue:
        log("INFO: キュー追加対象なし")
        return

    for role, lines in queue.items():
        suffix = ROLE_TO_FILE_SUFFIX.get(role)
        if not suffix:
            log(f"WARN: 未知のロール '{role}'、スキップ")
            continue
        target = SCRIPTS_DIR / f"missing-subrole-{suffix}.txt"

        if mode == "append":
            existing = existing_queue_pairs(suffix)
            new_lines = []
            for ln in lines:
                parts = ln.split("|")
                if len(parts) >= 4 and (parts[0], parts[2]) not in existing:
                    new_lines.append(ln)
            if not new_lines:
                log(f"  → {target.name}: 追加なし（既存と重複）")
                continue
            if dry_run:
                log(f"  → DRY-RUN: {target.name} に {len(new_lines)} 行追加")
                for ln in new_lines[:3]:
                    log(f"      {ln}")
                continue
            with open(target, "a", encoding="utf-8") as f:
                for ln in new_lines:
                    f.write(ln + "\n")
            log(f"  → {target.name}: {len(new_lines)} 行追加")

        elif mode == "overwrite":
            if dry_run:
                log(f"  → DRY-RUN: {target.name} を {len(lines)} 行で上書き")
                for ln in lines[:3]:
                    log(f"      {ln}")
                continue
            with open(target, "w", encoding="utf-8") as f:
                for ln in lines:
                    f.write(ln + "\n")
            log(f"  → {target.name}: {len(lines)} 行で上書き")


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--full", action="store_true", help="全 sub エントリを処理して missing-subrole-{role}.txt を再生成")
    group.add_argument("--from-stdin", action="store_true", help="stdin から差分 JSON を受け取って追記")
    parser.add_argument("--dry-run", action="store_true", help="ファイル変更なし")
    args = parser.parse_args()

    log("===== gen-subrole-queue 開始 =====")

    targets = load_targets()

    if args.full:
        # 全 sub エントリを new_subs として扱う
        new_subs = {
            champ_id: entry.get("sub", [])
            for champ_id, entry in targets.get("champions", {}).items()
            if entry.get("sub")
        }
        log(f"INFO: --full モード、対象チャンプ {len(new_subs)} 体")
        queue = build_pairs(new_subs, targets)
        write_queue(queue, mode="overwrite", dry_run=args.dry_run)

    elif args.from_stdin:
        payload = json.load(sys.stdin)
        new_subs = payload.get("new_subs", {})
        if not new_subs:
            log("INFO: new_subs が空。終了")
            return 0
        log(f"INFO: --from-stdin モード、対象チャンプ {len(new_subs)} 体")
        queue = build_pairs(new_subs, targets)
        write_queue(queue, mode="append", dry_run=args.dry_run)

    log("===== gen-subrole-queue 完了 =====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
