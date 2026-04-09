#!/usr/bin/env python3
# learn.py
# 人間レビュー済みの findings.md を処理して表現ルールを学習・適用する (L1)
#
# 使い方:
#   python3 scripts/learn.py scripts/review/2026-04-10-findings.md
#   python3 scripts/learn.py scripts/review/2026-04-10-findings.md --dry-run

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
CHAMP_DIR = PROJECT_DIR / "champions"
RULES_FILE = Path(__file__).resolve().parent / "expression-rules.json"
REVIEW_DIR = Path(__file__).resolve().parent / "review"
CANDIDATES_FILE = REVIEW_DIR / "writing-rules-candidates.md"
LOG_PREFIX = f"[{date.today()}]"

FINDING_META_RE = re.compile(
    r"<!-- FINDING id=(\d+) file=(.+?) line=(\d+) pattern=(.+?) -->"
)
VERDICT_RE = re.compile(r"^判定:\s*(.+)$", re.MULTILINE)
FIX_RE = re.compile(r"^修正案:\s*(?!（任意）)(.+)$", re.MULTILINE)


def parse_findings(findings_path):
    """findings.md を解析してFinding一覧を返す"""
    text = findings_path.read_text(encoding="utf-8")

    # セクションを「---」で分割
    sections = re.split(r"\n---\n", text)
    findings = []

    for section in sections:
        meta_m = FINDING_META_RE.search(section)
        if not meta_m:
            continue
        verdict_m = VERDICT_RE.search(section)
        fix_m = FIX_RE.search(section)

        verdict = verdict_m.group(1).strip().lower() if verdict_m else ""
        fix = fix_m.group(1).strip() if fix_m else ""

        # 元の行テキストを抽出（```の間）
        code_m = re.search(r"```\n(.+?)\n```", section, re.DOTALL)
        original_line = code_m.group(1).strip() if code_m else ""

        findings.append({
            "id": int(meta_m.group(1)),
            "file": meta_m.group(2),
            "line_no": int(meta_m.group(3)),
            "pattern_id": meta_m.group(4),
            "verdict": verdict,
            "fix": fix,
            "original_line": original_line,
            "section": section,
        })

    return findings


def apply_fix_to_file(filepath, line_no, original_line, fixed_line, dry_run):
    """ファイルの指定行を修正する"""
    lines = filepath.read_text(encoding="utf-8").splitlines(keepends=True)
    target_idx = line_no - 1
    if target_idx >= len(lines):
        print(f"  WARN: {filepath}:{line_no} が見つかりません")
        return False
    current = lines[target_idx].rstrip("\n")
    if original_line not in current:
        print(f"  WARN: {filepath}:{line_no} — 元のテキストが変わっています（スキップ）")
        return False
    new_line = current.replace(original_line, fixed_line, 1) + "\n"
    if dry_run:
        print(f"  [DRY-RUN] {filepath}:{line_no}")
        print(f"    before: {current}")
        print(f"    after:  {new_line.rstrip()}")
        return True
    lines[target_idx] = new_line
    filepath.write_text("".join(lines), encoding="utf-8")
    return True


def add_learned_replacement(literal, replacement, dry_run):
    """expression-rules.json の learned_replacements に追加する"""
    rules = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    existing = [r["literal"] for r in rules.get("learned_replacements", [])]
    if literal in existing:
        print(f"  SKIP: '{literal}' は既に学習済み")
        return
    entry = {
        "literal": literal,
        "replacement": replacement,
        "added": date.today().isoformat(),
    }
    if dry_run:
        print(f"  [DRY-RUN] learned_replacements に追加: {literal!r} → {replacement!r}")
        return
    rules.setdefault("learned_replacements", []).append(entry)
    RULES_FILE.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  学習: '{literal}' → '{replacement}'")


def update_pattern_counts(pattern_id, verdict, dry_run):
    rules = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    for p in rules["patterns"]:
        if p["id"] == pattern_id:
            if verdict == "ng":
                p["confirmed_ng"] = p.get("confirmed_ng", 0) + 1
            elif verdict == "ok":
                p["confirmed_ok"] = p.get("confirmed_ok", 0) + 1
            break
    if not dry_run:
        RULES_FILE.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")


def append_candidates(ng_findings, dry_run):
    """NG件数が多いパターンを writing-rules-candidates.md に追記"""
    from collections import Counter
    pattern_counts = Counter(f["pattern_id"] for f in ng_findings)
    if not pattern_counts:
        return

    rules = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    pattern_map = {p["id"]: p for p in rules["patterns"]}

    lines = [f"\n## {date.today().isoformat()} レビュー結果からの提案\n"]
    for pattern_id, count in pattern_counts.most_common():
        p = pattern_map.get(pattern_id, {})
        lines.append(f"- **{p.get('category', pattern_id)}** ({count}件NG確定)")
        lines.append(f"  - パターン: `{p.get('regex', '')}`")
        lines.append(f"  - 説明: {p.get('description', '')}")
        lines.append(f"  - → writing-rules.md への追記を検討\n")

    content = "\n".join(lines)
    if dry_run:
        print(f"  [DRY-RUN] writing-rules-candidates.md に追記:")
        print(content)
        return

    REVIEW_DIR.mkdir(exist_ok=True)
    with open(CANDIDATES_FILE, "a", encoding="utf-8") as f:
        f.write(content)
    print(f"  writing-rules-candidates.md に提案を追記しました")


def cleanup_findings(findings_path, processed_ids, dry_run):
    """判定済みセクションを findings.md から削除する"""
    text = findings_path.read_text(encoding="utf-8")
    sections = re.split(r"(\n---\n)", text)

    new_parts = []
    i = 0
    while i < len(sections):
        section = sections[i]
        meta_m = FINDING_META_RE.search(section)
        if meta_m and int(meta_m.group(1)) in processed_ids:
            # 判定済み → 削除（後続の "---\n" も含めて）
            if i + 1 < len(sections) and sections[i + 1] == "\n---\n":
                i += 2
                continue
        new_parts.append(section)
        i += 1

    new_text = "".join(new_parts)

    # 残りの findings が0件なら削除
    remaining = len(FINDING_META_RE.findall(new_text))
    if dry_run:
        print(f"  [DRY-RUN] findings.md: {len(processed_ids)}件削除 → 残り{remaining}件")
        return

    if remaining == 0:
        findings_path.unlink()
        print(f"  findings.md をクリーンアップ（全件処理済み → 削除）")
    else:
        findings_path.write_text(new_text, encoding="utf-8")
        print(f"  findings.md をクリーンアップ（残り{remaining}件）")


def main():
    parser = argparse.ArgumentParser(description="レビュー済み findings.md を処理して学習する")
    parser.add_argument("findings", help="処理する findings.md のパス")
    parser.add_argument("--dry-run", action="store_true", help="実際には変更しない")
    args = parser.parse_args()

    findings_path = Path(args.findings)
    if not findings_path.exists():
        print(f"ERROR: {findings_path} が見つかりません", file=sys.stderr)
        sys.exit(1)

    findings = parse_findings(findings_path)
    judged = [f for f in findings if f["verdict"] in ("ok", "ng")]
    ng = [f for f in judged if f["verdict"] == "ng"]
    ok = [f for f in judged if f["verdict"] == "ok"]

    print(f"{LOG_PREFIX} INFO: 判定済み {len(judged)}件（NG:{len(ng)} OK:{len(ok)}）/ 未判定:{len(findings)-len(judged)}件")

    if not judged:
        print("判定済みの項目がありません")
        return

    # NG処理
    processed_ids = set()
    for f in ng:
        print(f"\n  NG: {f['file']}:{f['line_no']} [{f['pattern_id']}]")
        update_pattern_counts(f["pattern_id"], "ng", args.dry_run)

        if f["fix"]:
            # 修正案が提供されている場合: ファイルに適用 + 学習
            filepath = PROJECT_DIR / f["file"]
            applied = apply_fix_to_file(filepath, f["line_no"], f["original_line"], f["fix"], args.dry_run)
            if applied:
                # リテラルな差分を学習（同じパターンを将来自動修正）
                add_learned_replacement(f["original_line"], f["fix"], args.dry_run)
        processed_ids.add(f["id"])

    # OK処理（カウント更新のみ）
    for f in ok:
        update_pattern_counts(f["pattern_id"], "ok", args.dry_run)
        processed_ids.add(f["id"])

    # writing-rules-candidates.md への提案
    if ng:
        append_candidates(ng, args.dry_run)

    # findings.md クリーンアップ
    cleanup_findings(findings_path, processed_ids, args.dry_run)

    print(f"\n{LOG_PREFIX} INFO: 完了 — NG:{len(ng)}件処理 / OK:{len(ok)}件処理")


if __name__ == "__main__":
    main()
