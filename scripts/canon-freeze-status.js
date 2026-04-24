/**
 * `sdlab canon freeze-status <entity_id>` — read-only glance at an entry's
 * freeze state. Human-readable by default; --json for machine consumption.
 */

import { parseArgs } from 'node:util';
import { join } from 'node:path';
import { loadBuildConfig } from '../lib/canon-build/load-config.js';
import { loadCanonEntriesInDir } from '../lib/canon-build/load-entry.js';
import { readFreezeStatus } from '../lib/freeze-stamp.js';
import { readEventsFor } from '../lib/freeze-events.js';
import { inputError } from '../lib/errors.js';

export async function run(argv) {
  const parsed = parseArgs({
    args: argv,
    options: {
      project: { type: 'string' },
      game:    { type: 'string' },
      json:    { type: 'boolean', default: false },
    },
    allowPositionals: true,
    strict: false,
  });

  const entityIdArg = (parsed.positionals || [])[0];
  if (!entityIdArg) throw inputError('INPUT_MISSING_ARG', 'sdlab canon freeze-status requires an entity id.');
  const projectName = parsed.values.project || parsed.values.game;
  if (!projectName) throw inputError('INPUT_MISSING_FLAG', '--project required');

  const projectRoot = join(process.cwd(), 'projects', projectName);
  const config = await loadBuildConfig(join(projectRoot, 'canon-build', 'config.json'), projectRoot);

  let resolved = null;
  for (const [schemaName, subdir] of Object.entries(config.entity_dirs)) {
    const dir = join(config.canon_root, subdir);
    const entries = await loadCanonEntriesInDir(dir);
    const hit = entries.find((e) => e.frontmatter?.id === entityIdArg);
    if (hit) { resolved = { entry: hit, schemaName }; break; }
  }
  if (!resolved) throw inputError('CANON_ENTRY_NOT_FOUND', `No canon entry "${entityIdArg}".`);

  const fm = resolved.entry.frontmatter;
  const status = readFreezeStatus(fm);
  const block = fm.freeze || {};
  const events = await readEventsFor(projectRoot, entityIdArg);

  const result = {
    entity_id: entityIdArg,
    schema_kind: resolved.schemaName.replace('.schema.json', ''),
    status,
    locked_at_build: block.locked_at_build || null,
    frozen_by: block.frozen_by || null,
    frozen_reason: block.frozen_reason || null,
    watch_fields: block.watch_fields || [],
    overrides_count: Array.isArray(block.overrides) ? block.overrides.length : 0,
    event_count: events.length,
  };

  if (parsed.values.json) {
    console.log(JSON.stringify(result, null, 2));
    return;
  }

  console.log(`${entityIdArg} (${result.schema_kind})`);
  console.log(`  status:          ${status}`);
  if (status !== 'auto') {
    console.log(`  locked_at_build: ${result.locked_at_build || '(unset)'}`);
    console.log(`  frozen_by:       ${result.frozen_by || '(unset)'}`);
    console.log(`  frozen_reason:   ${result.frozen_reason || '(unset)'}`);
    console.log(`  watch_fields:    ${result.watch_fields.length ? result.watch_fields.join(', ') : '(none)'}`);
  }
  console.log(`  overrides[]:     ${result.overrides_count} recorded on entry`);
  console.log(`  event log:       ${result.event_count} events total`);
}
