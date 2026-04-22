#!/usr/bin/env node

/**
 * compare.js — Record a pairwise A-vs-B style comparison.
 *
 * Usage:
 *   node scripts/compare.js <asset_a_id> <asset_b_id> <winner: a|b|tie> <reasoning>
 *   sdlab compare iron_sword_base iron_sword_icon_mid a "Better silhouette" --project star-freight
 */

import { writeFile, readdir, mkdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { parseArgs, getProjectName } from "../lib/args.js";
import { REPO_ROOT } from "../lib/paths.js";
import { readJsonFile } from "../lib/config.js";
import { inputError, handleCliError } from "../lib/errors.js";

export async function run(argv = process.argv.slice(2)) {
  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      scores: { type: 'string' },
    },
    deprecated: { game: 'project' },
  });

  const projectName = flags.project || getProjectName(argv);
  const GAME_ROOT = join(REPO_ROOT, 'projects', projectName);

  const [assetAId, assetBId, winner, ...reasonParts] = positionals;

  if (!assetAId || !assetBId || !winner) {
    throw inputError(
      'INPUT_MISSING_ARGS',
      'Usage: sdlab compare <asset_a_id> <asset_b_id> <a|b|tie> <reasoning>'
    );
  }

  if (!["a", "b", "tie"].includes(winner)) {
    throw inputError(
      'INPUT_BAD_WINNER',
      `Invalid winner: ${winner}. Must be a, b, or tie.`
    );
  }

  const reasoning = reasonParts.join(" ") || null;

  // Load records to get paths
  const recordA = await loadRecord(GAME_ROOT, assetAId);
  const recordB = await loadRecord(GAME_ROOT, assetBId);

  if (!recordA || !recordB) {
    throw inputError('INPUT_UNKNOWN_RECORD', 'Could not load one or both records.');
  }

  // Parse optional scores
  const scoresStr = flags.scores;
  const criteria_scores = {};
  if (scoresStr) {
    for (const pair of scoresStr.split(",")) {
      const [k, v] = pair.split(":");
      // Format: "silhouette:0.9/0.6" → { silhouette: { a: 0.9, b: 0.6 } }
      if (k && v) {
        const [aStr, bStr] = v.split("/");
        const aScore = parseFloat(aStr);
        const bScore = parseFloat(bStr);
        if (!Number.isFinite(aScore) || !Number.isFinite(bScore)) {
          throw inputError(
            'INPUT_BAD_SCORE',
            `Score for "${k.trim()}" is not numeric: "${v}"`,
            'Use the form --scores silhouette:0.9/0.6,palette:0.8/0.7'
          );
        }
        criteria_scores[k.trim()] = { a: aScore, b: bScore };
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
    return await readJsonFile(path);
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
  run().catch(handleCliError);
}
