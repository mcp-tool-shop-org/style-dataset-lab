#!/usr/bin/env node

/**
 * curate.js — Move a candidate to approved/rejected/borderline and record judgment.
 *
 * Usage:
 *   node scripts/curate.js <asset_id> approved "Clean silhouette, correct palette" --scores silhouette:0.9,palette:0.8
 *   node scripts/curate.js <asset_id> rejected "3D render look, alpha halo" --failures alpha_halo,3d_render_look
 *   node scripts/curate.js --list  (show uncurated candidates)
 */

import { readFile, writeFile, rename, readdir, mkdir } from "node:fs/promises";
import { join } from "node:path";

const REPO_ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const GAME = process.argv.find((a, i) => process.argv[i - 1] === '--game') || 'star-freight';
const GAME_ROOT = join(REPO_ROOT, 'games', GAME);

async function main() {
  const args = process.argv.slice(2);

  if (args.includes("--list")) {
    return listUncurated();
  }

  const [assetId, status, explanation, ...rest] = args;

  if (!assetId || !status || !explanation) {
    console.log("Usage: node scripts/curate.js <asset_id> <approved|rejected|borderline> <explanation> [--scores k:v,...] [--failures f1,f2]");
    process.exit(1);
  }

  if (!["approved", "rejected", "borderline"].includes(status)) {
    console.error(`Invalid status: ${status}. Must be approved, rejected, or borderline.`);
    process.exit(1);
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
    console.error(`Record not found: ${recordPath}`);
    process.exit(1);
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
    console.error(`Could not move ${oldPath} to ${newPath}`);
    process.exit(1);
  }

  console.log(`\x1b[32m✓\x1b[0m ${assetId} → ${status}`);
  console.log(`  ${explanation}`);
  if (failure_modes.length) console.log(`  Failures: ${failure_modes.join(", ")}`);
}

async function listUncurated() {
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
