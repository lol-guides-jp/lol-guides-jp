#!/usr/bin/env python3
"""sub_matchup_io.py
matchups-sub.md（ロールセクション構造）への対面エントリ upsert / パースを担う L1 ヘルパー。

なぜ別構造か:
  メインロール対面（matchups.md）は「## vs X」のフラット構造で十分だが、
  サブロール対面は1チャンプが複数レーンで起用される（brand=MID/ADC 等）ため、
  同一ファイルにレーンごとの対面が同居する。レーンタグが無いと MID 対面と ADC 対面が
  区別不能になる（2026-06-04 構造改修）。そこで matchups-sub.md は:

    ## ミッドレーン
    ### vs アーリ（Ahri）
    - **やや不利（勝率約48%）**: ...
    ### vs アカリ（Akali）
    - ...
    ## ADC
    ### vs ...

  と「## {role}」でレーンを区切り、各対面を「### vs X」で持つ。

  メイン由来の対面は matchups.md に残し、build-json.js が
  matchupsByRole[role] = メイン由来 + サブ由来 をレーン基準でマージする。

CLI:
  echo "$entry" | python3 sub_matchup_io.py upsert <path> <role>
    - stdin の「## vs X（Y）...」ブロックを「### vs X（Y）」に降格し、
      <path> の「## {role}」セクション配下に upsert（同一相手があれば置換、無ければ追記）。
    - <path> が無ければ新規作成。セクションが無ければ末尾に追加。冪等。
"""
import os
import re
import sys

# subrole-targets.json / build-json.js と揃えたフルロール名（matchupsByRole のキーになる）。
ROLE_NAMES = ["トップレーン", "ジャングル", "ミッドレーン", "ADC", "サポート"]


def demote_entry(entry: str) -> str:
    """「## vs ...」で始まるブロックの先頭見出しを「### vs ...」に降格する。"""
    entry = entry.strip()
    if entry.startswith("## vs "):
        return "### vs " + entry[len("## vs "):]
    return entry


def opp_header(entry: str):
    """「### vs アーリ（Ahri）」から相手日本語名「アーリ」を取り出す。見つからなければ None。"""
    m = re.match(r"^#{2,3} vs (.+?)（", entry)
    return m.group(1).strip() if m else None


def parse_sections(content: str):
    """content を [[role, [entry_block, ...]], ...] に分解（出現順を保持）。

    「## {role}」（role は ROLE_NAMES のいずれか）でレーンセクションを区切る。
    「## vs ...」は role 見出しではないので無視される（移行前のフラットファイルを誤解釈しない防御）。
    """
    sections = []
    # role 見出しのみで分割（## vs ... は negative lookahead で除外）
    parts = re.split(r"(?m)^## (?!vs )(.+)$", content)
    # parts[0] は前文（無視）。以降 [role, body, role, body, ...]
    i = 1
    while i < len(parts):
        role = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        entries = [
            e.strip()
            for e in re.split(r"(?m)^(?=### vs )", body)
            if e.strip().startswith("### vs ")
        ]
        sections.append([role, entries])
        i += 2
    return sections


def serialize(sections) -> str:
    """[[role, [entry, ...]], ...] を matchups-sub.md テキストに直す。"""
    out = []
    for role, entries in sections:
        out.append(f"## {role}")
        for e in entries:
            out.append("")
            out.append(e.strip())
        out.append("")
    return "\n".join(out).strip() + "\n"


def upsert(path: str, role: str, entry_text: str) -> str:
    """entry_text（## vs ... ブロック）を path の ## {role} 配下に upsert する。"""
    entry = demote_entry(entry_text)
    opp = opp_header(entry)
    if opp is None:
        raise ValueError(f"対面見出しが解釈できません: {entry_text[:60]!r}")

    if os.path.isfile(path):
        sections = parse_sections(open(path, encoding="utf-8").read())
    else:
        sections = []

    for sec in sections:
        if sec[0] == role:
            for idx, e in enumerate(sec[1]):
                if opp_header(e) == opp:
                    sec[1][idx] = entry
                    break
            else:
                sec[1].append(entry)
            break
    else:
        sections.append([role, [entry]])

    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(serialize(sections))
    return f"upserted: {os.path.basename(os.path.dirname(path))}/matchups-sub.md  ## {role} / vs {opp}"


def _main(argv):
    if len(argv) < 2:
        print("usage: sub_matchup_io.py upsert <path> <role>", file=sys.stderr)
        return 2
    cmd = argv[0]
    if cmd == "upsert":
        path, role = argv[1], argv[2]
        if role not in ROLE_NAMES:
            print(f"ERROR: 未知のロール {role!r}（許可: {ROLE_NAMES}）", file=sys.stderr)
            return 1
        entry_text = sys.stdin.read()
        if not entry_text.strip():
            print("ERROR: stdin が空です", file=sys.stderr)
            return 1
        print(upsert(path, role, entry_text))
        return 0
    print(f"ERROR: 未知のコマンド {cmd!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
