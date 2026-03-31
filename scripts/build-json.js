#!/usr/bin/env node
// build-json.js
// 全チャンピオンガイド(Markdown)をJSONに変換する
//
// 使い方: node scripts/build-json.js

const fs = require("fs");
const path = require("path");

const CHAMPIONS_DIR = path.join(__dirname, "..", "champions");
const OUTPUT_FILE = path.join(__dirname, "..", "docs", "data.json");

function parseGuide(markdown) {
  const sections = {};
  let currentSection = null;
  let currentContent = [];

  for (const line of markdown.split("\n")) {
    if (line.startsWith("## ")) {
      if (currentSection) {
        sections[currentSection] = currentContent.join("\n").trim();
      }
      currentSection = line.replace("## ", "").trim();
      currentContent = [];
    } else if (line.startsWith("# ")) {
      sections._title = line.replace("# ", "").trim();
    } else {
      currentContent.push(line);
    }
  }
  if (currentSection) {
    sections[currentSection] = currentContent.join("\n").trim();
  }
  return sections;
}

function parseMatchups(text) {
  if (!text) return [];
  return text
    .split("\n")
    .filter((l) => l.startsWith("- **"))
    .map((l) => {
      const match = l.match(/- \*\*(.+?)\*\*:\s*(.+)/);
      if (!match) return null;
      return { name: match[1], description: match[2] };
    })
    .filter(Boolean);
}

function parseTitleLine(title) {
  const match = title.match(/^(.+?)（(.+?)）(.+?)\s*パッチ(.+)$/);
  if (!match) return { en: title, ja: "", role: "", patch: "" };
  return {
    en: match[1].trim(),
    ja: match[2].trim(),
    role: match[3].trim(),
    patch: match[4].trim(),
  };
}

const champions = [];
const dirs = fs.readdirSync(CHAMPIONS_DIR).filter((d) => d !== "_template");

for (const dir of dirs) {
  const guidePath = path.join(CHAMPIONS_DIR, dir, "guide.md");
  if (!fs.existsSync(guidePath)) continue;

  const md = fs.readFileSync(guidePath, "utf-8");
  const sections = parseGuide(md);
  const info = parseTitleLine(sections._title || "");

  champions.push({
    id: dir,
    en: info.en,
    ja: info.ja,
    role: info.role,
    patch: info.patch,
    summary: sections["一言まとめ"] || "",
    skillOrder: sections["スキルオーダー"] || "",
    powerSpikes: sections["主要パワースパイク"] || "",
    gamePlan: sections["ゲームプラン"] || "",
    favorableMatchups: parseMatchups(sections["得意マッチアップ"]),
    unfavorableMatchups: parseMatchups(sections["苦手マッチアップ"]),
    counters: sections["対策（敵チームにアーリがいる場合）"]
      ? sections[
          Object.keys(sections).find((k) => k.startsWith("対策"))
        ]
      : sections[Object.keys(sections).find((k) => k.startsWith("対策"))] ||
        "",
  });
}

champions.sort((a, b) => a.ja.localeCompare(b.ja, "ja"));

fs.mkdirSync(path.dirname(OUTPUT_FILE), { recursive: true });
fs.writeFileSync(OUTPUT_FILE, JSON.stringify(champions, null, 2), "utf-8");
console.log(`${champions.length}体のデータを ${OUTPUT_FILE} に出力しました`);
