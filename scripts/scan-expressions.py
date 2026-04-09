#!/usr/bin/env python3
# scan-expressions.py
# ガイド記事の表現パターンをスキャンして要確認リストを生成 (L1)
#
# 使い方:
#   python3 scripts/scan-expressions.py
#   python3 scripts/scan-expressions.py --dry-run
#
# cron登録:
#   0 3 * * 0 cd /home/ojita/lol-guides-jp && python3 scripts/scan-expressions.py >> scripts/scan.log 2>&1

import argparse
import json
import re
from datetime import date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
CHAMP_DIR = PROJECT_DIR / "champions"
RULES_FILE = Path(__file__).resolve().parent / "expression-rules.json"
REVIEW_DIR = Path(__file__).resolve().parent / "review"
CLAUDE_LOCAL = Path("/home/ojita/CLAUDE.local.md")
LOG_PREFIX = f"[{date.today()}]"


def load_patterns():
    rules = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    patterns = []
    for p in rules["patterns"]:
        patterns.append({
            "id": p["id"],
            "category": p["category"],
            "description": p["description"],
            "regex": re.compile(p["regex"]),
        })
    return patterns


def scan_file(filepath, patterns):
    findings = []
    try:
        lines = filepath.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        findings.append({
            "line_no": 0,
            "line": "(ファイル読み込みエラー)",
            "pattern_id": "mojibake",
            "category": "文字化け",
            "description": "ファイルのエンコーディングエラー",
        })
        return findings

    for i, line in enumerate(lines, 1):
        # ヘッダ行・メタ行はスキップ
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith(">") or stripped.startswith("---") or stripped.startswith("*パッチ"):
            continue
        for p in patterns:
            if p["regex"].search(stripped):
                findings.append({
                    "line_no": i,
                    "line": stripped,
                    "pattern_id": p["id"],
                    "category": p["category"],
                    "description": p["description"],
                })
    return findings


def generate_findings_md(all_findings, output_path):
    today = date.today().isoformat()
    sections = []
    sections.append(f"# 品質スキャン {today}\n")
    sections.append(
        "判定欄に `ok` または `ng` を記入してください。\n"
        "NG の場合は修正案を記入すると learn.py が自動適用します（任意）。\n"
        "未判定の項目は次回スキャンまで残ります。\n"
    )
    sections.append("---\n")

    n = 0
    for rel_path, file_findings in all_findings:
        for f in file_findings:
            n += 1
            block = [
                f"<!-- FINDING id={n} file={rel_path} line={f['line_no']} pattern={f['pattern_id']} -->",
                f"## 要確認 {n} | {f['category']} | {rel_path}:{f['line_no']}",
                f"> {f['description']}",
                "```",
                f['line'],
                "```",
                "判定: ",
                "修正案: （任意）",
                "",
                "---\n",
            ]
            sections.append("\n".join(block))

    output_path.write_text("\n".join(sections), encoding="utf-8")
    return n


def notify(count, findings_path):
    line = f"- {LOG_PREFIX} lol-guides-jp: 品質スキャン {count}件の要確認 → {findings_path}\n"
    try:
        with open(CLAUDE_LOCAL, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError as e:
        print(f"WARN: CLAUDE.local.md 書き込み失敗: {e}")


def main():
    parser = argparse.ArgumentParser(description="ガイド記事の表現パターンをスキャン")
    parser.add_argument("--dry-run", action="store_true", help="findings.md を生成せず結果のみ表示")
    args = parser.parse_args()

    REVIEW_DIR.mkdir(exist_ok=True)
    patterns = load_patterns()
    print(f"{LOG_PREFIX} INFO: {len(patterns)}パターンでスキャン開始")

    all_findings = []
    for champ_dir in sorted(CHAMP_DIR.iterdir()):
        if champ_dir.name == "_template" or not champ_dir.is_dir():
            continue
        for filename in ["guide.md", "matchups.md"]:
            filepath = champ_dir / filename
            if not filepath.exists():
                continue
            rel_path = f"champions/{champ_dir.name}/{filename}"
            findings = scan_file(filepath, patterns)
            if findings:
                all_findings.append((rel_path, findings))

    total = sum(len(f) for _, f in all_findings)
    print(f"{LOG_PREFIX} INFO: スキャン完了 {total}件の要確認事項")

    if args.dry_run:
        for rel_path, findings in all_findings[:10]:
            for f in findings:
                print(f"  {rel_path}:{f['line_no']} [{f['category']}] {f['line'][:80]}")
        return

    if total == 0:
        print(f"{LOG_PREFIX} INFO: 要確認事項なし")
        return

    today = date.today().isoformat()
    output_path = REVIEW_DIR / f"{today}-findings.md"
    count = generate_findings_md(all_findings, output_path)
    notify(count, output_path)
    print(f"{LOG_PREFIX} INFO: 保存完了 {output_path} ({count}件)")


if __name__ == "__main__":
    main()
