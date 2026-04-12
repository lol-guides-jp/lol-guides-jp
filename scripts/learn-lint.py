#!/usr/bin/env python3
"""learn-lint.py — Sonnet レビューの修正差分から lint-rules.json にルールを追加する

改善サイクル:
  1. Gemini が生成 → lint-matchup.py --fix → Sonnet レビュー → 修正済みエントリ
  2. Gemini 原文と Sonnet 修正後を比較し、繰り返し現れる修正パターンを抽出
  3. このスクリプトで lint-rules.json に追加 → 次回から lint が自動修正

使い方:
  # banned_word ルールを追加（自動置換あり）
  python3 scripts/learn-lint.py add 'メカ形態' --replacement 'メガナー' --reason 'ナーの正式な形態名'

  # banned_word ルールを追加（フラグのみ、置換なし）
  python3 scripts/learn-lint.py add 'フルキット' --reason '禁止表現'

  # polite_ending ルールを追加
  python3 scripts/learn-lint.py add-polite 'であります' --reason '軍隊調は不要'

  # 現在のルール一覧を表示
  python3 scripts/learn-lint.py list

  # Sonnet修正前後のdiffからルール候補を提案（--dry-run）
  python3 scripts/learn-lint.py diff before.txt after.txt
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(SCRIPT_DIR, "lint-rules.json")


def load_rules() -> dict:
    with open(RULES_PATH) as f:
        return json.load(f)


def save_rules(rules: dict) -> None:
    with open(RULES_PATH, "w") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    print(f"OK: {RULES_PATH} updated", file=sys.stderr)


def cmd_add(args: list[str]) -> None:
    """banned_word ルールを追加。"""
    if not args:
        print("Usage: learn-lint.py add 'pattern' [--replacement 'text'] --reason 'text'", file=sys.stderr)
        sys.exit(1)

    pattern = args[0]
    replacement = ""
    reason = ""
    i = 1
    while i < len(args):
        if args[i] == "--replacement" and i + 1 < len(args):
            replacement = args[i + 1]
            i += 2
        elif args[i] == "--reason" and i + 1 < len(args):
            reason = args[i + 1]
            i += 2
        else:
            i += 1

    if not reason:
        print("ERROR: --reason is required", file=sys.stderr)
        sys.exit(1)

    rules = load_rules()

    # 重複チェック
    existing = [r["pattern"] for r in rules.get("banned_words", [])]
    if pattern in existing:
        print(f"SKIP: '{pattern}' already exists in banned_words", file=sys.stderr)
        return

    rules.setdefault("banned_words", []).append({
        "pattern": pattern,
        "replacement": replacement,
        "reason": reason,
    })
    save_rules(rules)
    print(f"Added banned_word: '{pattern}' → '{replacement}' ({reason})")


def cmd_add_polite(args: list[str]) -> None:
    """polite_ending ルールを追加。"""
    if not args:
        print("Usage: learn-lint.py add-polite 'pattern' --reason 'text'", file=sys.stderr)
        sys.exit(1)

    pattern = args[0]
    reason = ""
    i = 1
    while i < len(args):
        if args[i] == "--reason" and i + 1 < len(args):
            reason = args[i + 1]
            i += 2
        else:
            i += 1

    if not reason:
        print("ERROR: --reason is required", file=sys.stderr)
        sys.exit(1)

    rules = load_rules()

    existing = [r["pattern"] for r in rules.get("polite_endings", [])]
    if pattern in existing:
        print(f"SKIP: '{pattern}' already exists in polite_endings", file=sys.stderr)
        return

    rules.setdefault("polite_endings", []).append({
        "pattern": pattern,
        "reason": reason,
    })
    save_rules(rules)
    print(f"Added polite_ending: '{pattern}' ({reason})")


def cmd_list() -> None:
    """現在のルール一覧を表示。"""
    rules = load_rules()

    print("=== banned_words ===")
    for r in rules.get("banned_words", []):
        fix = f" → '{r['replacement']}'" if r.get("replacement") else " (flag only)"
        print(f"  '{r['pattern']}'{fix} — {r['reason']}")

    print("\n=== polite_endings ===")
    for r in rules.get("polite_endings", []):
        print(f"  '{r['pattern']}' — {r['reason']}")

    print(f"\n=== max_sentences_per_section: {rules.get('max_sentences_per_section', '?')} ===")

    print(f"\n=== form_skill_map: {len(rules.get('form_skill_map', {}))} champions ===")
    for champ, forms in rules.get("form_skill_map", {}).items():
        print(f"  {champ}: {', '.join(forms.keys())}")


def cmd_diff(args: list[str]) -> None:
    """Sonnet 修正前後のテキストを比較し、lint ルール候補を提案。"""
    if len(args) != 2:
        print("Usage: learn-lint.py diff before.txt after.txt", file=sys.stderr)
        sys.exit(1)

    with open(args[0]) as f:
        before = f.read()
    with open(args[1]) as f:
        after = f.read()

    rules = load_rules()
    existing_patterns = {r["pattern"] for r in rules.get("banned_words", [])}

    # 単純な単語レベルの差分を抽出
    before_words = set(before.split())
    after_words = set(after.split())

    removed = before_words - after_words
    added = after_words - before_words

    if not removed:
        print("No word-level removals detected.")
        return

    print("=== Sonnet が除去した単語 ===")
    for word in sorted(removed):
        if word in existing_patterns:
            continue
        # 対応する追加ワードがあれば置換候補
        print(f"  removed: '{word}'")

    print("\n=== Sonnet が追加した単語 ===")
    for word in sorted(added):
        print(f"  added: '{word}'")

    print("\nヒント: 繰り返し現れるパターンは以下で追加:")
    print("  python3 scripts/learn-lint.py add 'パターン' --replacement '置換先' --reason '理由'")


def main():
    if len(sys.argv) < 2:
        print("Usage: learn-lint.py <add|add-polite|list|diff> [args...]", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "add":
        cmd_add(args)
    elif cmd == "add-polite":
        cmd_add_polite(args)
    elif cmd == "list":
        cmd_list()
    elif cmd == "diff":
        cmd_diff(args)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
