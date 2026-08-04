#!/usr/bin/env node

/**
 * curate.js — Move a candidate to approved/rejected/borderline and record judgment.
 *
 * Usage:
 *   node scripts/curate.js <asset_id> approved "Clean silhouette, correct palette" --scores silhouette:0.9,palette:0.8
 *   node scripts/curate.js <asset_id> rejected "3D render look, alpha halo" --failures alpha_halo,3d_render_look
 *   node scripts/curate.js --list  (show uncurated candidates)
 *   sdlab curate <asset_id> approved "explanation" --project star-freight [--dry-run]
 */

import { writeFile, rename, readdir, mkdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { parseArgs, getProjectName } from "../lib/args.js";
import { getProjectRoot } from "../lib/paths.js";
import { readJsonFile } from "../lib/config.js";
import { inputError, runtimeError, handleCliError } from "../lib/errors.js";
import { result } from "../lib/log.js";
import { assertNotFrozenByAssetPath } from "../lib/freeze-gate.js";
import { deriveGeneratorModel, warnIfSelfVerification, HUMAN_JUDGE } from "../lib/verifier.js";

export async function run(argv = process.argv.slice(2)) {
  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      scores: { type: 'string' },
      failures: { type: 'string' },
      notes: { type: 'string' },
      list: { type: 'boolean', default: false },
      'dry-run': { type: 'boolean', default: false },
      'i-know': { type: 'boolean', default: false },
    },
    deprecated: { game: 'project' },
  });

  const projectName = flags.project || getProjectName(argv);
  const GAME_ROOT = getProjectRoot(projectName);
  const dryRun = flags['dry-run'] || flags.dryRun;

  if (flags.list) {
    return listUncurated(GAME_ROOT);
  }

  const [assetId, status, explanation] = positionals;

  if (!assetId || !status || !explanation) {
    throw inputError(
      'INPUT_MISSING_ARGS',
      'Usage: sdlab curate <asset_id> <approved|rejected|borderline> <explanation> [--scores k:v,...] [--failures f1,f2] [--dry-run]'
    );
  }

  if (!["approved", "rejected", "borderline"].includes(status)) {
    throw inputError(
      'INPUT_BAD_STATUS',
      `Invalid status: ${status}. Must be approved, rejected, or borderline.`
    );
  }

  const scoresStr = flags.scores;
  const failuresStr = flags.failures;
  const notesStr = flags.notes;

  const criteria_scores = {};
  if (scoresStr) {
    for (const pair of scoresStr.split(",")) {
      const [k, v] = pair.split(":");
      if (k && v) {
        const score = parseFloat(v);
        if (!Number.isFinite(score)) {
          throw inputError(
            'INPUT_BAD_SCORE',
            `Score value for "${k.trim()}" is not a number: "${v}"`,
            'Use the form --scores silhouette:0.9,palette:0.8'
          );
        }
        criteria_scores[k.trim()] = score;
      }
    }
  }

  const failure_modes = failuresStr ? failuresStr.split(",").map((s) => s.trim()) : [];

  // Load existing record
  const recordPath = join(GAME_ROOT, `records/${assetId}.json`);
  let record;
  try {
    record = await readJsonFile(recordPath);
  } catch (err) {
    if (err && err.code === 'INPUT_FILE_NOT_FOUND') {
      throw inputError('INPUT_UNKNOWN_RECORD', `Record not found: ${recordPath}`);
    }
    throw err;
  }

  const originalAssetPath = record.asset_path;
  const oldPath = join(GAME_ROOT, originalAssetPath);
  const newDir = `outputs/${status}`;
  const newPath = `${newDir}/${assetId}.png`;
  const newFullPath = join(GAME_ROOT, newPath);

  if (dryRun) {
    console.log(`\x1b[33m(dry-run)\x1b[0m ${assetId}`);
    console.log(`  status: ${status}`);
    console.log(`  move:   ${originalAssetPath} -> ${newPath}`);
    console.log(`  note:   ${explanation}`);
    if (failure_modes.length) console.log(`  failures: ${failure_modes.join(", ")}`);
    return;
  }

  // Freeze gate: refuse to recurate to a path that a frozen canon entry owns.
  // No-op when the project has no canon-build config. The explanation doubles
  // as the bypass reason when the target entry is soft-advisory.
  await assertNotFrozenByAssetPath(GAME_ROOT, newPath, {
    action: 'curate',
    allowSoftAdvisoryBypass: flags['i-know'],
    bypassReason: explanation,
    by: 'mike',
  });

  await mkdir(join(GAME_ROOT, newDir), { recursive: true });

  // Move image FIRST — if the rename fails we still have a clean record.
  try {
    await rename(oldPath, newFullPath);
  } catch (err) {
    throw runtimeError(
      'RUNTIME_MOVE_FAILED',
      `Could not move ${oldPath} to ${newPath}: ${err.message}`,
      'Check that the source image exists and the destination is writable.',
      err
    );
  }

  // EXTERNAL_VERIFIER: record WHO judged (human) and WHAT generated the artifact,
  // and warn if they ever coincide (they never do for human curation — the field
  // + warning install the muscle for when an LLM judge enters the loop).
  const generator_model = deriveGeneratorModel(record.provenance);
  warnIfSelfVerification(HUMAN_JUDGE, generator_model, assetId);

  // Now safely update the record. If writing fails, try to restore the image.
  record.asset_path = newPath;
  record.judgment = {
    status,
    reviewer: "human:mike",
    judged_by_model: HUMAN_JUDGE,
    generator_model,
    reviewed_at: new Date().toISOString(),
    explanation,
    criteria_scores,
    failure_modes,
    improvement_notes: notesStr || null,
    confidence: 0.9,
  };

  try {
    await writeFile(recordPath, JSON.stringify(record, null, 2));
  } catch (err) {
    // Attempt rollback: put the image back.
    try { await rename(newFullPath, oldPath); } catch {}
    throw runtimeError(
      'RUNTIME_WRITE_FAILED',
      `Could not write record ${recordPath}: ${err.message}`,
      null,
      err
    );
  }

  // Final artifact path — always shown, even under --quiet.
  result('curate', `${assetId} → ${status}`);
  result(`  image: ${newPath}`);
  result(`  record: records/${assetId}.json`);
  console.log(`  ${explanation}`);
  if (failure_modes.length) console.log(`  Failures: ${failure_modes.join(", ")}`);

  // UNCERTAINTY_GATED_HUMANS: contrastive advisory on borderline (Horvitz CHI
  // 1999). State the default (HOLD — borderline is not training-eligible) and
  // what a later promotion must justify, so the promoter argues against a stated
  // default rather than nudging a status upward unexamined.
  if (status === 'borderline') {
    const drift = failure_modes.length ? failure_modes.join(', ') : 'the drift you noted';
    console.log(
      `  \x1b[2mDefault: HOLD — 'borderline' is not training-eligible. ` +
      `To later promote to 'approved', justify why ${drift} is acceptable for canon (re-run curate approved with that reason).\x1b[0m`,
    );
  }
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
  run().catch(handleCliError);
}
