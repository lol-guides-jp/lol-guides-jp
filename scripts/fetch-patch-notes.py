#!/usr/bin/env python3
# fetch-patch-notes.py
# 公式LoLパッチノートを取得して patches/ に保存する (L1)
#
# 使い方:
#   python3 fetch-patch-notes.py 26.8
#   python3 fetch-patch-notes.py 26.8 --dry-run

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
PATCHES_DIR = PROJECT_DIR / "patches"
CLAUDE_LOCAL = Path("/home/ojita/CLAUDE.local.md")

MIN_CONTENT_LENGTH = 500  # これ以下なら取得失敗とみなす


def notify_failure(patch_version: str, reason: str) -> None:
    """セッション開始時に報告されるよう CLAUDE.local.md に追記する"""
    from datetime import date
    line = f"⚠️ {date.today()}: lol-guides-jp fetch-patch-notes.py 失敗（パッチ{patch_version}: {reason}）\n"
    try:
        with CLAUDE_LOCAL.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError as e:
        print(f"WARN: CLAUDE.local.md への書き込み失敗: {e}", file=sys.stderr)


def fetch_html(patch_version: str) -> str:
    slug = "league-of-legends-patch-" + patch_version.replace(".", "-") + "-notes"
    url = f"https://www.leagueoflegends.com/en-us/news/game-updates/{slug}/"
    print(f"INFO: フェッチ中: {url}")

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; patch-fetcher/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status != 200:
                raise OSError(f"HTTP {resp.status}")
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        raise RuntimeError(f"ページ取得失敗: {e}") from e


def extract_content(html: str, patch_version: str) -> str:
    """HTMLからパッチノート本文を抽出する"""

    # 試行1: Next.js の __NEXT_DATA__ JSON からコンテンツを取得
    nd_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if nd_match:
        try:
            data = json.loads(nd_match.group(1))
            # ネストしたJSONからarticlebody相当を探す
            text = _find_in_dict(data, ["body", "articleBody", "content", "description"])
            if text and len(text) >= MIN_CONTENT_LENGTH:
                return f"# パッチ {patch_version} ノート\n\n{text}"
        except (json.JSONDecodeError, KeyError):
            pass

    # 試行2: JSON-LD structured data
    ld_match = re.search(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if ld_match:
        try:
            data = json.loads(ld_match.group(1))
            if isinstance(data, dict):
                for key in ("articleBody", "description", "text"):
                    if key in data and len(data[key]) >= MIN_CONTENT_LENGTH:
                        return f"# パッチ {patch_version} ノート\n\n{data[key]}"
        except (json.JSONDecodeError, KeyError):
            pass

    # 試行3: article タグ内のテキストを抽出
    article_match = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
    if article_match:
        text = _strip_tags(article_match.group(1))
        if len(text) >= MIN_CONTENT_LENGTH:
            return f"# パッチ {patch_version} ノート\n\n{text[:15000]}"

    # 試行4: body全体からタグ除去（最終手段）
    text = _strip_tags(html)
    if len(text) >= MIN_CONTENT_LENGTH:
        return f"# パッチ {patch_version} ノート\n\n{text[:15000]}"

    return ""


def _find_in_dict(obj, keys: list, depth: int = 0) -> str:
    """再帰的にdictからキーを検索して文字列を返す（深さ制限あり）"""
    if depth > 8:
        return ""
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and isinstance(obj[key], str) and len(obj[key]) > 100:
                return obj[key]
        for v in obj.values():
            result = _find_in_dict(v, keys, depth + 1)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_in_dict(item, keys, depth + 1)
            if result:
                return result
    return ""


def _strip_tags(html: str) -> str:
    """HTMLタグを除去してテキストを返す"""
    clean = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '', html, flags=re.DOTALL)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = re.sub(r'[ \t]+', ' ', clean)
    clean = re.sub(r'\n{3,}', '\n\n', clean)
    return clean.strip()


def validate_content(content: str, patch_version: str) -> None:
    """取得したコンテンツが妥当か検証する"""
    if len(content) < MIN_CONTENT_LENGTH:
        raise ValueError(f"コンテンツが短すぎます（{len(content)}文字、最低{MIN_CONTENT_LENGTH}文字必要）")

    # パッチバージョンの文字列が含まれているか（最低限の整合性確認）
    major_minor = patch_version  # e.g. "26.8"
    version_alt = patch_version.replace(".", "")  # "268"
    if major_minor not in content and version_alt not in content:
        raise ValueError(f"取得したコンテンツにパッチバージョン {patch_version} が含まれていません")


def main() -> None:
    parser = argparse.ArgumentParser(description="LoLパッチノートを取得してpatches/に保存")
    parser.add_argument("patch_version", help="パッチバージョン (例: 26.8)")
    parser.add_argument("--dry-run", action="store_true", help="実際には保存しない")
    args = parser.parse_args()

    patch_version = args.patch_version
    output_path = PATCHES_DIR / f"{patch_version}.md"

    if args.dry_run:
        slug = "league-of-legends-patch-" + patch_version.replace(".", "-") + "-notes"
        url = f"https://www.leagueoflegends.com/en-us/news/game-updates/{slug}/"
        print(f"[DRY-RUN] フェッチ対象: {url}")
        print(f"[DRY-RUN] 保存先: {output_path}")
        return

    try:
        html = fetch_html(patch_version)
        content = extract_content(html, patch_version)
        validate_content(content, patch_version)
        output_path.write_text(content, encoding="utf-8")
        print(f"INFO: 保存完了: {output_path} ({len(content)}文字)")
    except Exception as e:
        reason = str(e)
        print(f"ERROR: {reason}", file=sys.stderr)
        notify_failure(patch_version, reason)
        sys.exit(1)


if __name__ == "__main__":
    main()
