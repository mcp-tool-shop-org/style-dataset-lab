/**
 * `sdlab canon freeze <entity_id> --reason "<text>"` — stamp a freeze block
 * on a canon entry (D7 command).
 *
 * Validates the entry exists, that a canon-build output exists to witness
 * against (so the `locked_at_build` field has a real value — D1), rewrites
 * the entry's frontmatter with the new `freeze` block, and appends a
 * `freeze` event to freeze-events.jsonl (D4).
 */

import { parseArgs } from 'node:util';
import { readFile, writeFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { parse as parseYaml, stringify as stringifyYaml } from 'yaml';
import { loadBuildConfig } from '../lib/canon-build/load-config.js';
import { loadCanonEntriesInDir, entryId } from '../lib/canon-build/load-entry.js';
import { buildFreezeBlock, FREEZE_STATUSES, resolveWatchFields } from '../lib/freeze-stamp.js';
import { appendEvent } from '../lib/freeze-events.js';
import { inputError } from '../lib/errors.js';

export async function run(argv) {
  const parsed = parseArgs({
    args: argv,
    options: {
      project: { type: 'string' },
      game:    { type: 'string' },
      reason:  { type: 'string' },
      status:  { type: 'string', default: 'frozen' },
      watch:   { type: 'string' },
      build:   { type: 'string' },
      by:      { type: 'string', default: 'mike' },
      json:    { type: 'boolean', default: false },
    },
    allowPositionals: true,
    strict: false,
  });

  const positional = parsed.positionals || [];
  const entityIdArg = positional[0];
  if (!entityIdArg) {
    throw inputError(
      'INPUT_MISSING_ARG',
      'sdlab canon freeze requires an entity id as the first positional argument.',
      'Example: sdlab canon freeze heracles --reason "Labor III reference plate approved"',
    );
  }

  const projectName = parsed.values.project || parsed.values.game;
  if (!projectName) {
    throw inputError('INPUT_MISSING_FLAG', 'sdlab canon freeze requires --project <name>', 'Example: --project greek-rpg');
  }

  if (!parsed.values.reason) {
    throw inputError(
      'FREEZE_REASON_REQUIRED',
      'sdlab canon freeze requires --reason "<short text>".',
      'The reason lands in both the entry frontmatter and canon-build/freeze-events.jsonl as the audit record. Future you (and the LLM crew) need it to understand why.',
    );
  }

  if (!FREEZE_STATUSES.includes(parsed.values.status)) {
    throw inputError(
      'INPUT_INVALID_VALUE',
      `--status must be one of ${FREEZE_STATUSES.join(', ')} (got "${parsed.values.status}")`,
    );
  }
  if (parsed.values.status === 'auto') {
    throw inputError(
      'INPUT_INVALID_VALUE',
      '--status auto means "no freeze" — use `sdlab canon unfreeze` instead of freezing with status=auto.',
    );
  }

  const projectRoot = join(process.cwd(), 'projects', projectName);
  const configPath = join(projectRoot, 'canon-build', 'config.json');
  const config = await loadBuildConfig(configPath, projectRoot);

  // Find the entry file
  const resolved = await findEntryFile(config, entityIdArg);
  if (!resolved) {
    throw inputError(
      'CANON_ENTRY_NOT_FOUND',
      `No canon entry with id "${entityIdArg}" found under ${config.canon_root}.`,
      `Check the entry filename matches the id field, and that the schema-subdirectory mapping in canon-build/config.json covers this entity type.`,
    );
  }

  // Resolve the witness build hash
  const lockedAtBuild = parsed.values.build || await findLatestBuildHash(projectRoot);
  if (!lockedAtBuild) {
    throw inputError(
      'FREEZE_NO_BUILD_WITNESS',
      'No canon-build output exists to witness this freeze against.',
      'Run `sdlab canon build` first to produce a build artifact, then retry the freeze. The witness chain (D1) requires a real build hash to stamp.',
    );
  }

  // Resolve watch-fields: --watch override > entry override > config default
  const watchFields = resolveEffectiveWatchFields({
    entry: resolved.entry,
    schemaName: resolved.schemaName,
    buildConfig: config,
    cliOverride: parsed.values.watch,
  });

  // Build the new freeze block, preserving existing overrides[] if any
  const existing = resolved.entry.frontmatter.freeze || {};
  const priorStatus = existing.status || 'auto';
  const newBlock = buildFreezeBlock({
    status: parsed.values.status,
    lockedAtBuild,
    frozenBy: parsed.values.by,
    frozenReason: parsed.values.reason,
    watchFields,
    overrides: existing.overrides,
  });

  // Rewrite the entry file
  const updatedFm = { ...resolved.entry.frontmatter, freeze: newBlock };
  await rewriteEntryFrontmatter(resolved.filePath, updatedFm, resolved.entry.body);

  // Append audit event
  const event = await appendEvent(projectRoot, {
    type: 'freeze',
    entity_id: entityIdArg,
    schema_kind: resolved.schemaName.replace('.schema.json', ''),
    by: parsed.values.by,
    reason: parsed.values.reason,
    prior_status: priorStatus,
    new_status: parsed.values.status,
    watch_fields: watchFields,
    build_hash: lockedAtBuild,
  });

  const result = {
    ok: true,
    entity_id: entityIdArg,
    status: parsed.values.status,
    locked_at_build: lockedAtBuild,
    watch_fields: watchFields,
    event_at: event.at,
  };

  if (parsed.values.json) {
    console.log(JSON.stringify(result, null, 2));
    return;
  }

  console.log(`froze "${entityIdArg}" (${parsed.values.status}) witnessed at ${lockedAtBuild}`);
  console.log(`  watching: ${watchFields.length ? watchFields.join(', ') : '(no fields — build-config has no default for this schema and no --watch was passed)'}`);
  console.log(`  reason:   ${parsed.values.reason}`);
}

// ─── Helpers ──────────────────────────────────────────────────────────

async function findEntryFile(config, entityId) {
  for (const [schemaName, subdir] of Object.entries(config.entity_dirs)) {
    const dir = join(config.canon_root, subdir);
    const entries = await loadCanonEntriesInDir(dir);
    for (const entry of entries) {
      const id = entry.frontmatter?.id;
      if (id === entityId) {
        return { entry, schemaName, filePath: entry.filePath };
      }
    }
  }
  return null;
}

async function findLatestBuildHash(projectRoot) {
  const canonBuildDir = join(projectRoot, 'canon-build');
  if (!existsSync(canonBuildDir)) return null;
  const entries = await readdir(canonBuildDir, { withFileTypes: true });
  const buildDirs = entries
    .filter((e) => e.isDirectory() && !e.name.startsWith('.') && !e.name.endsWith('.tmp') && !e.name.includes('.tmp-'))
    .map((e) => e.name);
  if (buildDirs.length === 0) return null;

  // Pick the most recent by mtime of its manifest.json
  let latest = null;
  let latestMtime = 0;
  for (const name of buildDirs) {
    const manifestPath = join(canonBuildDir, name, 'manifest.json');
    if (!existsSync(manifestPath)) continue;
    try {
      const manifest = JSON.parse(await readFile(manifestPath, 'utf-8'));
      const built = new Date(manifest.built_at || 0).getTime();
      if (built > latestMtime) {
        latestMtime = built;
        latest = manifest.generated_from || name;
      }
    } catch {
      continue;
    }
  }
  return latest;
}

function resolveEffectiveWatchFields({ entry, schemaName, buildConfig, cliOverride }) {
  if (cliOverride) {
    return cliOverride.split(',').map((s) => s.trim()).filter(Boolean);
  }
  return resolveWatchFields(entry.frontmatter, schemaName, buildConfig);
}

async function rewriteEntryFrontmatter(filePath, frontmatter, body) {
  const yaml = stringifyYaml(frontmatter).trimEnd();
  const content = `---\n${yaml}\n---\n${body}`;
  await writeFile(filePath, content, 'utf-8');
}
