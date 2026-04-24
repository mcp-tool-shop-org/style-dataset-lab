/**
 * `sdlab canon build` — CLI entry point for the three-projection build.
 *
 * Delegates orchestration to lib/canon-build/build.js. Parses flags, prints
 * a summary, exits with codes per the errors.js inputError/runtimeError
 * model (1 = user error, 2 = runtime error).
 */

import { parseArgs } from 'node:util';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { runBuild } from '../lib/canon-build/build.js';
import { inputError } from '../lib/errors.js';

export async function run(argv) {
  const parsed = parseArgs({
    args: argv,
    options: {
      project:  { type: 'string' },
      game:     { type: 'string' },           // deprecated alias
      full:     { type: 'boolean', default: false },
      'no-cache': { type: 'boolean', default: false },
      'dry-run':  { type: 'boolean', default: false },
      only:     { type: 'string' },
      json:     { type: 'boolean', default: false },
      quiet:    { type: 'boolean', default: false },
    },
    allowPositionals: true,
    strict: false,
  });

  const projectName = parsed.values.project || parsed.values.game;
  if (!projectName) {
    throw inputError(
      'INPUT_MISSING_FLAG',
      'sdlab canon build requires --project <name>',
      'Example: sdlab canon build --project greek-rpg',
    );
  }

  const projectRoot = join(process.cwd(), 'projects', projectName);
  if (!existsSync(projectRoot)) {
    throw inputError(
      'INPUT_PROJECT_NOT_FOUND',
      `Project directory not found: ${projectRoot}`,
      `Run from the style-dataset-lab repo root, or scaffold the project with "sdlab init ${projectName}".`,
    );
  }

  const only = parsed.values.only
    ? parsed.values.only.split(',').map((s) => s.trim()).filter(Boolean)
    : null;

  const result = await runBuild({
    projectRoot,
    full: parsed.values.full,
    noCache: parsed.values['no-cache'],
    dryRun: parsed.values['dry-run'],
    only,
  });

  if (parsed.values.json) {
    console.log(JSON.stringify(result, null, 2));
    return;
  }

  if (!parsed.values.quiet) {
    if (result.dryRun) {
      console.log(`[dry-run] canon build would process ${result.entities_total} entities (${result.entities_cached} cached, ${result.entities_rebuilt} would rebuild) → ${result.rows} dataset rows.`);
      console.log(`[dry-run] output would land at: ${result.output_dir}`);
    } else {
      console.log(`canon build complete: ${result.entities_total} entities (${result.entities_cached} cached, ${result.entities_rebuilt} rebuilt), ${result.rows} dataset rows.`);
      console.log(`output: ${result.output_dir}`);
      console.log(`generated_from: ${result.generated_from}`);
      if (result.frozen_entries > 0) {
        console.log(`frozen entries: ${result.frozen_entries} stamped with witness hashes`);
      }
      if (Array.isArray(result.drift) && result.drift.length > 0) {
        console.log('');
        console.log(`drift detected on ${result.drift.length} frozen entr${result.drift.length === 1 ? 'y' : 'ies'} since the previous build:`);
        for (const d of result.drift) {
          console.log(`  ${d.schema_kind}:${d.entity_id} (${d.status})`);
        }
        console.log('Run `sdlab canon drift` for the full report.');
      }
    }
  }
}
