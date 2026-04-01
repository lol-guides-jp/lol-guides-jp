#!/usr/bin/env node
// build-json.js
// 全チャンピオンガイド(Markdown)をJSONに変換する
//
// 使い方: node scripts/build-json.js

const fs = require("fs");
const path = require("path");

const CHAMPIONS_DIR = path.join(__dirname, "..", "champions");
const OUTPUT_FILE = path.join(__dirname, "..", "docs", "data.json");
const DDRAGON_KEYS = JSON.parse(
  fs.readFileSync(path.join(__dirname, "ddragon-keys.json"), "utf-8")
);
const BEGINNER_PICKS = JSON.parse(
  fs.readFileSync(path.join(__dirname, "beginner-picks.json"), "utf-8")
);

const DDRAGON_VERSION = "16.7.1";

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

function parseMatchupsList(text) {
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

// matchups.md パーサー
function parseMatchupsFile(markdown, nameToId) {
  const matchups = [];
  const blocks = markdown.split(/^## /m).slice(1);

  for (const block of blocks) {
    const lines = block.split("\n");
    const headerLine = lines[0].trim();

    // ヘッダパース: "vs Syndra（シンドラ）" or "vs ガレン（Garen）"
    const headerMatch = headerLine.match(
      /^vs\s+(.+?)（(.+?)）/
    );
    if (!headerMatch) continue;

    const name1 = headerMatch[1].trim();
    const name2 = headerMatch[2].trim();

    // opponentId解決: 英名→ID or 日名→ID
    const opponentId =
      nameToId[name1] || nameToId[name2] || name1.toLowerCase();

    // 難易度行パース（最初のbullet）
    let difficulty = "";
    let winrate = null;
    const bullets = [];

    for (const line of lines.slice(1)) {
      const bulletMatch = line.match(/^- \*\*(.+?)\*\*:\s*(.+)/);
      if (!bulletMatch) continue;

      const label = bulletMatch[1];
      const text = bulletMatch[2];

      // 最初のbulletは難易度行
      if (!difficulty) {
        const diffMatch = label.match(/^(.+?)（勝率[約]?(\d+\.?\d*)%）$/);
        if (diffMatch) {
          difficulty = diffMatch[1];
          winrate = parseFloat(diffMatch[2]);
        } else {
          difficulty = label;
        }
        bullets.push({ label: "概要", text });
      } else {
        bullets.push({ label, text });
      }
    }

    matchups.push({
      opponentId,
      difficulty,
      winrate,
      bullets,
    });
  }
  return matchups;
}

// 名前→IDの逆引きマップ構築
function buildNameToIdMap(champions) {
  const map = {};
  for (const c of champions) {
    if (c.en) map[c.en] = c.id;
    if (c.ja) map[c.ja] = c.id;
    // 日本語名のバリエーション（「リー・シン」→「lee-sin」など）
    if (c.ja) map[c.ja.replace(/・/g, "")] = c.id;
  }
  return map;
}

// --- メイン処理 ---
const champions = [];
const dirs = fs.readdirSync(CHAMPIONS_DIR).filter((d) => d !== "_template");

// Phase 1: guide.md を全て読み込み
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
    ddragonKey: DDRAGON_KEYS[dir] || dir,
    role: info.role,
    patch: info.patch,
    beginnerRating: BEGINNER_PICKS[dir] || 3,
    summary: sections["一言まとめ"] || "",
    skillOrder: sections["スキルオーダー"] || "",
    powerSpikes: sections["主要パワースパイク"] || "",
    gamePlan: sections["ゲームプラン"] || "",
    teamfight: sections["集団戦の立ち回り"] || "",
    favorableMatchups: parseMatchupsList(sections["得意マッチアップ"]),
    unfavorableMatchups: parseMatchupsList(sections["苦手マッチアップ"]),
    counters:
      sections[Object.keys(sections).find((k) => k.startsWith("対策"))] || "",
    matchups: [],
  });
}

// Phase 2: 名前→IDマップ構築後、matchups.md をパース
const nameToId = buildNameToIdMap(champions);

for (const champ of champions) {
  const matchupsPath = path.join(CHAMPIONS_DIR, champ.id, "matchups.md");
  if (!fs.existsSync(matchupsPath)) continue;

  const md = fs.readFileSync(matchupsPath, "utf-8");
  champ.matchups = parseMatchupsFile(md, nameToId);
}

champions.sort((a, b) => a.ja.localeCompare(b.ja, "ja"));

const output = {
  meta: {
    ddragonVersion: DDRAGON_VERSION,
    buildDate: new Date().toISOString().split("T")[0],
    championCount: champions.length,
    matchupCount: champions.filter((c) => c.matchups.length > 0).length,
  },
  champions,
};

fs.mkdirSync(path.dirname(OUTPUT_FILE), { recursive: true });
fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output, null, 2), "utf-8");
console.log(
  `${output.meta.championCount}体のデータ（matchups: ${output.meta.matchupCount}体）を ${OUTPUT_FILE} に出力しました`
);
