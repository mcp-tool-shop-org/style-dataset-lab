#!/usr/bin/env node

/**
 * measure.js — Attach deterministic pixel measurements to candidate records.
 *
 * Until now nothing in this tool ever opened an image. `lib/critique-engine.js`
 * builds its entire drift report from brief and workflow TEXT — keyword
 * matching against prompt strings — and stamps every candidate
 * `overall_fit: 'usable'` without looking at a single pixel. Every question
 * about what an image actually looks like was answered by eyeballing it.
 *
 * The instruments here are a port, not an invention. They come from the
 * measurement scripts written for the salt-road project
 * (`projects/salt-road/inputs/prompts/measure-palette.py`, `measure-texture.py`),
 * which were built and validated against real production waves and carry
 * their own written rationale for why simpler proxies were rejected.
 *
 * MEASUREMENT, NOT VERDICT. This command attaches numbers. It never sets
 * `judgment`, never sets `overall_fit`, never approves or rejects. That line
 * is deliberate and load-bearing: this repo deleted three scripts in its
 * Stage A health pass for minting judgments nobody made, and 948 of
 * star-freight's 1,182 records still carry that damage. Numbers inform a
 * human; they do not replace one.
 *
 * Usage:
 *   sdlab measure <dir-or-record-glob> --project <name>
 *   sdlab measure outputs/approved --project salt-road
 *   sdlab measure "styleset_p*" --project salt-road --anchors canon/anchors.json
 *   sdlab measure outputs/candidates --project salt-road --dry-run
 */

import { parseArgs, getProjectName } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { handleCliError } from '../lib/errors.js';
import { warn, result } from '../lib/log.js';
import {
  assertMeasurementPrereqs,
  resolveMeasureTargets,
  loadAnchors,
  runPythonMeasurement,
  applyMeasurements,
} from '../lib/measure.js';

const USAGE = `Usage: sdlab measure <dir-or-record-glob> --project <name> [--anchors <path>] [--dry-run] [--json]

Measure candidate images (palette conformance, texture character) and attach
the numbers to their records. Measurement only — never sets a judgment.

Positional:
  dir-or-record-glob   A directory of images, or a record-id glob
                       (quote globs so your shell does not expand them)

Flags:
  --project <name>     Project to operate on
  --anchors <path>     Palette anchor definitions, relative to the project
                       root. Without it, palette measures that need anchors
                       are skipped rather than guessed.
  --dry-run            Measure and report, write nothing
  --json               Emit the raw result as JSON

Requires Python 3.9+ with Pillow, numpy and scipy (see scripts/measure_image.py).
Set SDLAB_PYTHON to pin an explicit interpreter.`;

export async function run(argv = process.argv.slice(2)) {
  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string' },
      anchors: { type: 'string' },
      'dry-run': { type: 'boolean' },
      json: { type: 'boolean' },
      help: { type: 'boolean' },
    },
    deprecated: { game: 'project' },
    allowUnknown: true,
  });

  if (flags.help) {
    console.log(USAGE);
    return;
  }

  const projectName = flags.project || getProjectName(argv);
  const projectRoot = getProjectRoot(projectName);
  const dryRun = Boolean(flags['dry-run']);

  // Fail on a missing interpreter or package BEFORE resolving targets, so an
  // operator without the Python side gets one clear actionable error rather
  // than a successful scan followed by a confusing failure.
  const python = assertMeasurementPrereqs();

  const { targets, skipped } = resolveMeasureTargets(projectRoot, positionals[0]);

  console.log(`\x1b[1msdlab measure\x1b[0m — ${projectName}`);
  console.log(`  Target:  ${positionals[0]}`);
  console.log(`  Images:  ${targets.length}${dryRun ? '  (dry run — nothing will be written)' : ''}`);

  const anchorSpec = loadAnchors(flags.anchors, projectRoot);
  if (anchorSpec.source) {
    console.log(`  Anchors: ${anchorSpec.anchors.length} from ${flags.anchors}`);
  } else {
    // Say so plainly. A palette measure with no anchors is not a failed
    // measurement, but it is a narrower one, and silently returning fewer
    // fields than the operator expected is how a tool loses trust.
    console.log(`  Anchors: none — pass --anchors <path> for palette-conformance measures`);
  }
  console.log('');

  if (skipped.length > 0) {
    warn(`${skipped.length} target(s) skipped: ${skipped.slice(0, 3).map((s) => `${s.id} (${s.reason})`).join(', ')}${skipped.length > 3 ? ', …' : ''}`);
  }

  if (targets.length === 0) {
    console.log('  Nothing to measure.');
    return;
  }

  const pyResult = runPythonMeasurement(python, {
    images: targets.map((t) => ({ id: t.id, path: t.imagePath })),
    anchors: anchorSpec.anchors,
    hue_tolerance_deg: anchorSpec.hue_tolerance_deg,
    sat_min: anchorSpec.sat_min,
    val_min: anchorSpec.val_min,
  });

  const { applied, failed } = await applyMeasurements(targets, pyResult, {
    anchorsSource: anchorSpec.source,
    dryRun,
  });

  if (flags.json) {
    result(JSON.stringify({ applied, failed, skipped }, null, 2));
    return;
  }

  console.log(`  \x1b[32m✓\x1b[0m Measured: ${applied.length}`);
  if (failed.length > 0) {
    console.log(`  \x1b[31m✗\x1b[0m Failed:   ${failed.length}`);
    for (const f of failed.slice(0, 5)) {
      console.log(`      ${f.id}: ${f.error}`);
    }
    if (failed.length > 5) console.log(`      … and ${failed.length - 5} more`);
  }

  if (applied.length > 0) {
    // Show one real measurement rather than only a count — a number the
    // operator can sanity-check against the image in front of them is worth
    // more than a success tally.
    const sample = applied[0];
    const keys = Object.keys(sample.measurements || {}).filter((k) => !k.startsWith('_'));
    if (keys.length > 0) {
      console.log('');
      console.log(`  Sample (${sample.id}):`);
      for (const k of keys.slice(0, 6)) {
        const v = sample.measurements[k];
        const shown = typeof v === 'number' ? v.toFixed(4) : JSON.stringify(v);
        console.log(`    ${k.padEnd(28)} ${shown}`);
      }
    }
  }

  if (dryRun) {
    console.log('');
    console.log('  (dry run — no records were modified)');
  }
}

// Direct execution guard
if (process.argv[1] && (process.argv[1].endsWith('measure.js') || process.argv[1].endsWith('measure'))) {
  run().catch(handleCliError);
}
