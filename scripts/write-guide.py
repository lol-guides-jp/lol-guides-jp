#!/usr/bin/env python3
"""write-guide.py

gen-guide コマンドの JSON 出力（stdin）を受け取り、
champions/<slug>/guide.md を書き込む。判定された role を stdout に返す。

使い方:
  echo "$gen_result" | python3 scripts/write-guide.py <slug>

成功時: guide.md を書き込み、role を1行 stdout に出力して exit 0
失敗時: 理由を stderr に出して exit 1（status=error / JSON 不正 / 必須欠落）

責務はファイル書き込みのみ。ddragon-keys 登録・キュー投入は呼び出し側が行う。
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

PROJECT_DIR = Path("/home/ojita/lol-guides-jp")
VALID_ROLES = {"トップレーン", "ジャングル", "ミッドレーン", "ADC", "サポート"}


def main() -> int:
    if len(sys.argv) < 2:
        print("ERROR: slug を引数で渡す", file=sys.stderr)
        return 1
    slug = sys.argv[1]

    raw = sys.stdin.read().strip()
    # 保険: コードフェンスで囲まれていれば除去（dispatch_ops と同根の対策）
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: gen-guide 出力が JSON として不正: {e}", file=sys.stderr)
        return 1

    if data.get("status") != "success":
        print(f"ERROR: gen-guide status={data.get('status')} reason={data.get('reason', '?')}",
              file=sys.stderr)
        return 1

    role = data.get("role", "").strip()
    guide_md = data.get("guide_md", "")

    if role not in VALID_ROLES:
        print(f"ERROR: role が不正（{role!r}）。許可値: {sorted(VALID_ROLES)}", file=sys.stderr)
        return 1
    if not guide_md or "## 一言まとめ" not in guide_md:
        print("ERROR: guide_md が空または必須セクション（一言まとめ）を欠く", file=sys.stderr)
        return 1

    out_dir = PROJECT_DIR / "champions" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    guide_path = out_dir / "guide.md"
    # 末尾に改行を1つ保証
    if not guide_md.endswith("\n"):
        guide_md += "\n"
    guide_path.write_text(guide_md, encoding="utf-8")

    print(f"ガイド書き込み: {guide_path}（role={role}）", file=sys.stderr)
    print(role)  # stdout は role のみ（呼び出し側が変数で受ける）
    return 0


if __name__ == "__main__":
    sys.exit(main())
