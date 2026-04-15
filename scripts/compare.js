#!/usr/bin/env node

/**
 * compare.js — Record a pairwise A-vs-B style comparison.
 *
 * Usage:
 *   node scripts/compare.js <asset_a_id> <asset_b_id> <winner: a|b|tie> <reasoning>
 *   sdlab compare iron_sword_base iron_sword_icon_mid a "Better silhouette" --project star-freight
 */

import { readFile, writeFile, readdir, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { getProjectName } from "../lib/args.js";
import { REPO_ROOT } from "../lib/paths.js";

function getFlagValue(args, flag) {
  const prefix = `--${flag}=`;
  for (const a of args) {
    if (a.startsWith(prefix)) return a.slice(prefix.length);
  }
  const idx = args.indexOf(`--${flag}`);
  if (idx !== -1 && idx + 1 < args.length) return args[idx + 1];
  return undefined;
}

export async function run(argv = process.argv.slice(2)) {
  const projectName = getProjectName(argv);
  const GAME_ROOT = join(REPO_ROOT, 'projects', projectName);

  // Strip --project/--game and their values from positional parsing
  const args = argv.filter((a, i) => {
    if (a === '--project' || a === '--game') return false;
    if (i > 0 && (argv[i - 1] === '--project' || argv[i - 1] === '--game')) return false;
    return true;
  });

  const [assetAId, assetBId, winner, ...reasonParts] = args;

  if (!assetAId || !assetBId || !winner) {
    throw new Error("Usage: sdlab compare <asset_a_id> <asset_b_id> <a|b|tie> <reasoning>");
  }

  if (!["a", "b", "tie"].includes(winner)) {
    throw new Error(`Invalid winner: ${winner}. Must be a, b, or tie.`);
  }

  const reasoning = reasonParts.filter(r => !r.startsWith('--')).join(" ") || null;

  // Load records to get paths
  const recordA = await loadRecord(GAME_ROOT, assetAId);
  const recordB = await loadRecord(GAME_ROOT, assetBId);

  if (!recordA || !recordB) {
    throw new Error("Could not load one or both records.");
  }

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
  const existingComps = await countComparisons(GAME_ROOT);
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

async function loadRecord(GAME_ROOT, id) {
  try {
    const path = join(GAME_ROOT, `records/${id}.json`);
    return JSON.parse(await readFile(path, "utf-8"));
  } catch {
    console.error(`Record not found: records/${id}.json`);
    return null;
  }
}

async function countComparisons(GAME_ROOT) {
  try {
    const files = await readdir(join(GAME_ROOT, "comparisons"));
    return files.filter((f) => f.endsWith(".json")).length;
  } catch {
    return 0;
  }
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('compare.js') || process.argv[1].endsWith('compare'))) {
  run().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}
