/**
 * `sdlab canon unfreeze <entity_id> --reason "<text>"` — lift a freeze (D7).
 *
 * Writes the entry's `freeze.status` to `auto`, appends an `unfreeze` event
 * with the prior state captured. Preserves the `overrides[]` history on the
 * entry (append-only) so re-freeze later shows the full lifecycle.
 *
 * --reason is REQUIRED — unfreezes are where shipping studios (Sabotage,
 * Supergiant, Pentiment) most often wished they had captured intent.
 */

import { parseArgs } from 'node:util';
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { stringify as stringifyYaml } from 'yaml';
import { loadBuildConfig } from '../lib/canon-build/load-config.js';
import { loadCanonEntriesInDir } from '../lib/canon-build/load-entry.js';
import { appendOverrideToFreezeBlock, readFreezeStatus } from '../lib/freeze-stamp.js';
import { appendEvent } from '../lib/freeze-events.js';
import { inputError } from '../lib/errors.js';

export async function run(argv) {
  const parsed = parseArgs({
    args: argv,
    options: {
      project: { type: 'string' },
      game:    { type: 'string' },
      reason:  { type: 'string' },
      by:      { type: 'string', default: 'mike' },
      build:   { type: 'string' },
      json:    { type: 'boolean', default: false },
    },
    allowPositionals: true,
    strict: false,
  });

  const entityIdArg = (parsed.positionals || [])[0];
  if (!entityIdArg) {
    throw inputError('INPUT_MISSING_ARG', 'sdlab canon unfreeze requires an entity id.');
  }
  const projectName = parsed.values.project || parsed.values.game;
  if (!projectName) throw inputError('INPUT_MISSING_FLAG', '--project required');
  if (!parsed.values.reason) {
    throw inputError(
      'FREEZE_REASON_REQUIRED',
      'sdlab canon unfreeze requires --reason "<text>".',
      'Unfreezes are where shipping studios most often regret not capturing intent. The reason lands in canon-build/freeze-events.jsonl and in the entry frontmatter\'s overrides[] append-only log.',
    );
  }

  const projectRoot = join(process.cwd(), 'projects', projectName);
  const config = await loadBuildConfig(join(projectRoot, 'canon-build', 'config.json'), projectRoot);
  const resolved = await findEntryFile(config, entityIdArg);
  if (!resolved) {
    throw inputError('CANON_ENTRY_NOT_FOUND', `No canon entry with id "${entityIdArg}".`);
  }

  const fm = resolved.entry.frontmatter;
  const priorStatus = readFreezeStatus(fm);
  if (priorStatus === 'auto') {
    throw inputError(
      'FREEZE_ALREADY_AUTO',
      `Canon entry "${entityIdArg}" is already at status=auto; nothing to unfreeze.`,
    );
  }

  const priorFreeze = fm.freeze || {};
  const buildHash = parsed.values.build || priorFreeze.locked_at_build || null;

  // Append override record to the entry's overrides[] log
  const overrideRecord = {
    at: buildHash || new Date().toISOString(),
    by: parsed.values.by,
    reason: parsed.values.reason,
    prior_status: priorStatus,
    prior_build_hash: priorFreeze.locked_at_build || null,
  };
  const updatedBlock = appendOverrideToFreezeBlock(
    { ...priorFreeze, status: 'auto' },
    overrideRecord,
  );
  // Drop fields that only make sense on an active freeze
  delete updatedBlock.locked_at_build;
  delete updatedBlock.locked_at_canon_version;
  delete updatedBlock.frozen_by;
  delete updatedBlock.frozen_reason;
  delete updatedBlock.watch_fields;

  const updatedFm = { ...fm, freeze: updatedBlock };
  await rewriteEntryFrontmatter(resolved.filePath, updatedFm, resolved.entry.body);

  const event = await appendEvent(projectRoot, {
    type: 'unfreeze',
    entity_id: entityIdArg,
    schema_kind: resolved.schemaName.replace('.schema.json', ''),
    by: parsed.values.by,
    reason: parsed.values.reason,
    prior_status: priorStatus,
    new_status: 'auto',
    prior_build_hash: priorFreeze.locked_at_build || null,
    build_hash: buildHash,
  });

  const result = {
    ok: true,
    entity_id: entityIdArg,
    prior_status: priorStatus,
    new_status: 'auto',
    event_at: event.at,
  };

  if (parsed.values.json) {
    console.log(JSON.stringify(result, null, 2));
    return;
  }
  console.log(`unfroze "${entityIdArg}" (was ${priorStatus})`);
  console.log(`  reason: ${parsed.values.reason}`);
  console.log(`  overrides[] history preserved with ${updatedBlock.overrides.length} entries`);
}

async function findEntryFile(config, entityId) {
  for (const [schemaName, subdir] of Object.entries(config.entity_dirs)) {
    const dir = join(config.canon_root, subdir);
    const entries = await loadCanonEntriesInDir(dir);
    for (const entry of entries) {
      if (entry.frontmatter?.id === entityId) {
        return { entry, schemaName, filePath: entry.filePath };
      }
    }
  }
  return null;
}

async function rewriteEntryFrontmatter(filePath, frontmatter, body) {
  const yaml = stringifyYaml(frontmatter).trimEnd();
  await writeFile(filePath, `---\n${yaml}\n---\n${body}`, 'utf-8');
}
