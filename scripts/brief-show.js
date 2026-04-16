#!/usr/bin/env node

/**
 * brief-show.js — Show a compiled brief.
 *
 * Usage:
 *   sdlab brief show brief_2026-04-15_001 --project star-freight
 *   sdlab brief show brief_2026-04-15_001 --json
 *   sdlab brief show brief_2026-04-15_001 --md
 */

import { parseArgs } from '../lib/args.js';
import { getProjectRoot } from '../lib/paths.js';
import { loadCompiledBrief } from '../lib/brief-compiler.js';
import { renderBriefText, renderBriefMarkdown } from '../lib/brief-render.js';

export async function run(argv = process.argv.slice(2)) {
  const { flags, positionals } = parseArgs(argv, {
    flags: {
      project: { type: 'string', default: 'star-freight' },
      json: { type: 'boolean' },
      md: { type: 'boolean' },
    },
    positionals: ['briefId'],
    deprecated: { game: 'project' },
  });

  const briefId = positionals[0];
  if (!briefId) {
    console.log('Usage: sdlab brief show <brief-id> [--project <name>] [--json] [--md]');
    return;
  }

  const projectRoot = getProjectRoot(flags.project);
  const brief = await loadCompiledBrief(projectRoot, briefId);

  if (flags.json) {
    console.log(JSON.stringify(brief, null, 2));
    return;
  }

  if (flags.md) {
    console.log(renderBriefMarkdown(brief));
    return;
  }

  console.log(renderBriefText(brief));
}

if (process.argv[1] && (process.argv[1].endsWith('brief-show.js') || process.argv[1].endsWith('brief-show'))) {
  run().catch((err) => { console.error(err.message || err); process.exit(1); });
}
