#!/usr/bin/env node

/**
 * compare.js — Record a pairwise A-vs-B style comparison.
 *
 * Usage:
 *   node scripts/compare.js <asset_a_id> <asset_b_id> <winner: a|b|tie> <reasoning>
 *   node scripts/compare.js iron_sword_base iron_sword_icon_mid a "Better silhouette, painterly execution"
 */

import { readFile, writeFile, readdir, mkdir } from "node:fs/promises";
import { join } from "node:path";

const REPO_ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const GAME = process.argv.find((a, i) => process.argv[i - 1] === '--game') || 'star-freight';
const GAME_ROOT = join(REPO_ROOT, 'games', GAME);

async function main() {
  const args = process.argv.slice(2);
  const [assetAId, assetBId, winner, ...reasonParts] = args;

  if (!assetAId || !assetBId || !winner) {
    console.log("Usage: node scripts/compare.js <asset_a_id> <asset_b_id> <a|b|tie> <reasoning>");
    process.exit(1);
  }

  if (!["a", "b", "tie"].includes(winner)) {
    console.error(`Invalid winner: ${winner}. Must be a, b, or tie.`);
    process.exit(1);
  }

  const reasoning = reasonParts.join(" ") || null;

  // Load records to get paths
  const recordA = await loadRecord(assetAId);
  const recordB = await loadRecord(assetBId);

  if (!recordA || !recordB) process.exit(1);

  // Parse optional scores
  const scoresStr = getFlagValue(args, "scores");
  const criteria_scores = {};
  if (scoresStr) {
    for (const pair of scoresStr.split(",")) {
      const [k, v] = pair.split(":");
      // Format: "silhouette:0.9/0.6" → { silhouette: { a: 0.9, b: 0.6 } }
      if (k && v) {
        const [aScore, bScore] = v.split("/");
        criteria_scores[k.trim()] = { a: parseFloat(aScore), b: parseFloat(bScore) };
      }
    }
  }

  // Build comparison ID
  const existingComps = await countComparisons();
  const cmpId = `cmp_${String(existingComps + 1).padStart(3, "0")}`;

  const comparison = {
    id: cmpId,
    asset_a_id: assetAId,
    asset_b_id: assetBId,
    asset_a_path: recordA.asset_path,
    asset_b_path: recordB.asset_path,
    chosen: winner,
    source: "human",
    reasoning,
    criteria_scores,
    rubric_citations: [],
    reviewer: "human:mike",
    reviewed_at: new Date().toISOString(),
  };

  await mkdir(join(GAME_ROOT, "comparisons"), { recursive: true });
  await writeFile(
    join(GAME_ROOT, `comparisons/${cmpId}.json`),
    JSON.stringify(comparison, null, 2),
  );

  const winnerLabel = winner === "tie" ? "TIE" : winner === "a" ? assetAId : assetBId;
  console.log(`\x1b[32m✓\x1b[0m ${cmpId}: ${assetAId} vs ${assetBId} → ${winnerLabel}`);
  if (reasoning) console.log(`  ${reasoning}`);
}

async function loadRecord(id) {
  try {
    const path = join(GAME_ROOT, `records/${id}.json`);
    return JSON.parse(await readFile(path, "utf-8"));
  } catch {
    console.error(`Record not found: records/${id}.json`);
    return null;
  }
}

async function countComparisons() {
  try {
    const files = await readdir(join(GAME_ROOT, "comparisons"));
    return files.filter((f) => f.endsWith(".json")).length;
  } catch {
    return 0;
  }
}

function getFlagValue(args, flag) {
  const prefix = `--${flag}=`;
  for (const a of args) {
    if (a.startsWith(prefix)) return a.slice(prefix.length);
  }
  const idx = args.indexOf(`--${flag}`);
  if (idx !== -1 && idx + 1 < args.length) return args[idx + 1];
  return undefined;
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
