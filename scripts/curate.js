#!/usr/bin/env node

/**
 * curate.js — Move a candidate to approved/rejected/borderline and record judgment.
 *
 * Usage:
 *   node scripts/curate.js <asset_id> approved "Clean silhouette, correct palette" --scores silhouette:0.9,palette:0.8
 *   node scripts/curate.js <asset_id> rejected "3D render look, alpha halo" --failures alpha_halo,3d_render_look
 *   node scripts/curate.js --list  (show uncurated candidates)
 *   sdlab curate <asset_id> approved "explanation" --project star-freight
 */

import { readFile, writeFile, rename, readdir, mkdir } from "node:fs/promises";
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
  const GAME_ROOT = join(REPO_ROOT, 'games', projectName);

  // Strip --project/--game and their values from positional parsing
  const args = argv.filter((a, i) => {
    if (a === '--project' || a === '--game') return false;
    if (i > 0 && (argv[i - 1] === '--project' || argv[i - 1] === '--game')) return false;
    return true;
  });

  if (args.includes("--list")) {
    return listUncurated(GAME_ROOT);
  }

  const [assetId, status, explanation, ...rest] = args;

  if (!assetId || !status || !explanation) {
    throw new Error("Usage: sdlab curate <asset_id> <approved|rejected|borderline> <explanation> [--scores k:v,...] [--failures f1,f2]");
  }

  if (!["approved", "rejected", "borderline"].includes(status)) {
    throw new Error(`Invalid status: ${status}. Must be approved, rejected, or borderline.`);
  }

  // Parse optional flags
  const scoresStr = getFlagValue(rest, "scores");
  const failuresStr = getFlagValue(rest, "failures");
  const notesStr = getFlagValue(rest, "notes");

  const criteria_scores = {};
  if (scoresStr) {
    for (const pair of scoresStr.split(",")) {
      const [k, v] = pair.split(":");
      if (k && v) criteria_scores[k.trim()] = parseFloat(v);
    }
  }

  const failure_modes = failuresStr ? failuresStr.split(",").map((s) => s.trim()) : [];

  // Load existing record
  const recordPath = join(GAME_ROOT, `records/${assetId}.json`);
  let record;
  try {
    record = JSON.parse(await readFile(recordPath, "utf-8"));
  } catch {
    throw new Error(`Record not found: ${recordPath}`);
  }

  // Update record first (write before move to avoid orphaned images)
  const oldPath = join(GAME_ROOT, record.asset_path);
  const newDir = `outputs/${status}`;
  const newPath = `${newDir}/${assetId}.png`;
  await mkdir(join(GAME_ROOT, newDir), { recursive: true });

  record.asset_path = newPath;
  record.judgment = {
    status,
    reviewer: "human:mike",
    reviewed_at: new Date().toISOString(),
    explanation,
    criteria_scores,
    failure_modes,
    improvement_notes: notesStr || null,
    confidence: 0.9,
  };

  await writeFile(recordPath, JSON.stringify(record, null, 2));

  // Move image file
  try {
    await rename(oldPath, join(GAME_ROOT, newPath));
  } catch {
    throw new Error(`Could not move ${oldPath} to ${newPath}`);
  }

  console.log(`\x1b[32m✓\x1b[0m ${assetId} → ${status}`);
  console.log(`  ${explanation}`);
  if (failure_modes.length) console.log(`  Failures: ${failure_modes.join(", ")}`);
}

async function listUncurated(GAME_ROOT) {
  const recordsDir = join(GAME_ROOT, "records");
  let files;
  try {
    files = await readdir(recordsDir);
  } catch {
    console.log("No records directory.");
    return;
  }

  let uncurated = 0;
  let curated = 0;

  for (const file of files) {
    if (!file.endsWith(".json")) continue;
    const record = JSON.parse(await readFile(join(recordsDir, file), "utf-8"));
    if (!record.judgment) {
      console.log(`  ${record.id}`);
      uncurated++;
    } else {
      curated++;
    }
  }

  console.log(`\n${uncurated} uncurated, ${curated} curated`);
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('curate.js') || process.argv[1].endsWith('curate'))) {
  run().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}
