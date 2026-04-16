#!/usr/bin/env python3
"""lint-matchup.py — Gemini 生成エントリの L1 品質チェック + 自動修正

使い方:
  echo "## vs ..." | python3 scripts/lint-matchup.py --check
  echo "## vs ..." | python3 scripts/lint-matchup.py --fix
  python3 scripts/lint-matchup.py --fix < entry.txt

--check: 問題を報告するだけ（exit 0=OK, exit 1=問題あり）
--fix:   自動修正できるものは修正して stdout に出力。修正不可のものは stderr に報告。

改善サイクル:
  Sonnet レビューで繰り返し指摘されるパターンは learn-lint.py で lint-rules.json に追加する。
"""

import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(SCRIPT_DIR, "lint-rules.json")


def load_rules() -> dict:
    with open(RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def check_banned_words(text: str, rules: dict) -> list[dict]:
    """禁止ワードを検出。auto_fix=True のものは置換可能。"""
    issues = []
    for rule in rules.get("banned_words", []):
        pattern = rule["pattern"]
        if pattern in text:
            issues.append({
                "type": "banned_word",
                "pattern": pattern,
                "replacement": rule.get("replacement", ""),
                "reason": rule["reason"],
                "auto_fix": bool(rule.get("replacement")),
            })
    return issues


def check_polite_endings(text: str, rules: dict) -> list[dict]:
    """敬語・丁寧体を検出。replacement があるものは自動修正可能。"""
    issues = []
    for rule in rules.get("polite_endings", []):
        pattern = rule["pattern"]
        if pattern in text:
            count = text.count(pattern)
            has_replacement = bool(rule.get("replacement"))
            issues.append({
                "type": "polite_ending",
                "pattern": pattern,
                "replacement": rule.get("replacement", ""),
                "count": count,
                "reason": rule["reason"],
                "auto_fix": has_replacement,
            })
    return issues


def check_verbosity(text: str, rules: dict) -> list[dict]:
    """セクションごとの文数をチェック。"""
    max_sentences = rules.get("max_sentences_per_section", 2)
    issues = []
    # - **Lv1〜2**: ... のようなセクションを抽出
    sections = re.findall(r'- \*\*(.+?)\*\*: (.+?)(?=\n- \*\*|\n$|$)', text, re.DOTALL)
    for label, body in sections:
        # 句点でカウント（。の数 + 末尾に句点がない場合は +1）
        sentence_count = body.count("。")
        if not body.rstrip().endswith("。"):
            sentence_count += 1
        if sentence_count > max_sentences:
            issues.append({
                "type": "verbose",
                "section": label,
                "sentence_count": sentence_count,
                "max": max_sentences,
                "reason": f"セクション「{label}」が{sentence_count}文（上限{max_sentences}文）",
                "auto_fix": False,
            })
    return issues


def check_form_skill_mismatch(text: str, rules: dict) -> list[dict]:
    """形態変化チャンプのスキル名と形態名の不一致を検出。"""
    form_map = rules.get("form_skill_map", {})
    issues = []

    for champ_id, forms in form_map.items():
        # 全形態のスキル名を逆引き（スキル名 → 正しい形態名）
        skill_to_form = {}
        for form_name, skills in forms.items():
            for key, skill_name in skills.items():
                skill_to_form[skill_name] = (form_name, key)

        # テキスト中で「〇〇モードQ（スキル名）」のようなパターンを検索
        for skill_name, (correct_form, key) in skill_to_form.items():
            if skill_name not in text:
                continue
            # 「間違った形態名 + このスキル名」の組み合わせを検出
            for other_form in forms:
                if other_form == correct_form:
                    continue
                # 「ハンマーモードQ（ショックブラスト）」のような誤り
                pattern = re.compile(
                    rf'{re.escape(other_form)}.*?{re.escape(key)}.*?（{re.escape(skill_name)}）'
                )
                if pattern.search(text):
                    issues.append({
                        "type": "form_skill_mismatch",
                        "pattern": f"{other_form} + {key}（{skill_name}）",
                        "reason": f"「{skill_name}」は{correct_form}の{key}。{other_form}ではない",
                        "auto_fix": False,
                    })
    return issues


def check_opp_skill_prefix(text: str, opp_skills_str: str) -> list[dict]:
    """対戦相手スキルがスロット記号（Q（）等）なしで出現していないか検出。
    opp_skills_str: "Q(スキル名), W(スキル名), ..." 形式（add-matchups.sh の OPP_SKILLS 環境変数）
    """
    if not opp_skills_str:
        return []
    # パース: Q(スキル名) → {スキル名: key}
    skill_map: dict[str, str] = {}
    for m in re.finditer(r'([QWER])\(([^)]+)\)', opp_skills_str):
        key, name = m.group(1), m.group(2)
        # 形態変化チャンプ: "スキルA/スキルB" は "/" で分割
        for part in name.split("/"):
            part = part.strip()
            if len(part) >= 3:  # 短すぎる名前は誤検知リスクが高いためスキップ
                skill_map[part] = key

    issues = []
    for skill_name, key in skill_map.items():
        # (?<!（) で「（スキル名）」形式はスキップ（= 既にフォーマット済み）
        pattern = r'(?<!（)' + re.escape(skill_name)
        if re.search(pattern, text):
            issues.append({
                "type": "opp_skill_no_prefix",
                "pattern": pattern,
                "replacement": f"{key}（{skill_name}）",
                "reason": f"対戦相手スキル「{skill_name}」にスロット記号なし（正: {key}（{skill_name}））",
                "auto_fix": True,
                "is_regex": True,
            })
    return issues


def apply_fixes(text: str, issues: list[dict]) -> str:
    """auto_fix=True の issue を適用して修正済みテキストを返す。"""
    for issue in issues:
        if not issue.get("auto_fix"):
            continue
        if issue.get("is_regex"):
            text = re.sub(issue["pattern"], issue["replacement"], text)
        elif issue.get("replacement") is not None:
            text = text.replace(issue["pattern"], issue["replacement"])
    return text


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("--check", "--fix"):
        print(f"Usage: {sys.argv[0]} --check|--fix < entry.txt", file=sys.stderr)
        sys.exit(1)

    mode = sys.argv[1]
    text = sys.stdin.read()

    if not text.strip():
        print("ERROR: empty input", file=sys.stderr)
        sys.exit(1)

    rules = load_rules()
    opp_skills_str = os.environ.get("OPP_SKILLS", "")

    all_issues = []
    all_issues.extend(check_banned_words(text, rules))
    all_issues.extend(check_polite_endings(text, rules))
    all_issues.extend(check_verbosity(text, rules))
    all_issues.extend(check_form_skill_mismatch(text, rules))
    all_issues.extend(check_opp_skill_prefix(text, opp_skills_str))

    if mode == "--check":
        if not all_issues:
            print("OK: no issues found", file=sys.stderr)
            sys.exit(0)
        for issue in all_issues:
            fix_label = "[auto-fix]" if issue.get("auto_fix") else "[manual]"
            print(f"  {fix_label} {issue['type']}: {issue['reason']}", file=sys.stderr)
        sys.exit(1)

    elif mode == "--fix":
        fixed = apply_fixes(text, all_issues)

        # 自動修正できなかった問題を stderr に報告
        manual_issues = [i for i in all_issues if not i.get("auto_fix")]
        if manual_issues:
            print(f"WARN: {len(manual_issues)} issues require manual/Sonnet fix:", file=sys.stderr)
            for issue in manual_issues:
                print(f"  {issue['type']}: {issue['reason']}", file=sys.stderr)

        print(fixed, end="")


if __name__ == "__main__":
    main()
