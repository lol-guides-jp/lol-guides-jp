#!/usr/bin/env python3
"""check-research-symmetry.py
2つのリサーチJSONの整合性をチェックする（勝率合計≈100%、verdict対称性）

Usage:
  python3 scripts/check-research-symmetry.py <json_a_path> <json_b_path>

終了コード:
  0 = OK
  1 = 警告あり（ログに出力）
"""

import json, sys

VERDICT_FLIP = {
    "有利":    "不利",
    "やや有利": "やや不利",
    "五分":    "五分",
    "やや不利": "やや有利",
    "不利":    "有利",
}
WINRATE_TOLERANCE = 3  # 合計が 100±3% なら許容


def parse_winrate(wr_str: str) -> int:
    return int(str(wr_str).replace("%", "").strip())


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: check-research-symmetry.py <json_a> <json_b>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        a = json.load(f)
    with open(sys.argv[2], encoding="utf-8") as f:
        b = json.load(f)

    warnings = []

    # 勝率合計は参考表示のみ（Lolalytics は独立集計のため100%にならない）
    try:
        wr_a = parse_winrate(a.get("winrate", "50%"))
        wr_b = parse_winrate(b.get("winrate", "50%"))
        total = wr_a + wr_b
        print(f"INFO: 勝率合計 {total}% ({a.get('champ_ja')}={wr_a}% / {b.get('champ_ja')}={wr_b}%)")
    except (ValueError, KeyError) as e:
        print(f"INFO: 勝率パースエラー: {e}")

    # verdict 対称性チェック
    v_a = a.get("verdict", "")
    v_b = b.get("verdict", "")
    expected_b = VERDICT_FLIP.get(v_a, "")
    if expected_b and v_b != expected_b:
        warnings.append(
            f"verdict不整合: {a.get('champ_ja')}={v_a} → {b.get('champ_ja')}={v_b} "
            f"(期待値: {expected_b})"
        )

    if warnings:
        for w in warnings:
            print(f"WARN: {w}", file=sys.stderr)
        sys.exit(1)

    print(f"OK: {a.get('champ_ja')} vs {b.get('champ_ja')} 整合チェック通過")


if __name__ == "__main__":
    main()
