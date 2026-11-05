/**
 * `sdlab canon draft <class_id> --endpoint <url> --brief "<text>" --out <path>`
 *
 * CLI wrapper for the Lane 2 canon and prompt authoring adapter (DESIGN-v3 §3.2,
 * §11, G10). Calls a loopback-only OpenAI-compatible server (e.g., llama-server
 * serving Muse-Glimmer-30B-A3B under Apache-2.0) and writes `prompts.jsonl`
 * (+ `prompts.jsonl.sha256`) with `status: "draft"` and `judgment: null`.
 */

import { parseArgs } from 'node:util';
import {
  draftCanonClassViaEndpoint,
  verifyGlimmerRuntime,
  writePromptsJsonl,
} from '../lib/canon-author.js';
import { inputError } from '../lib/errors.js';
import { assertKnownOptions } from './_shared-args.js';

export async function run(argv) {
  const options = {
    endpoint:    { type: 'string', default: 'http://127.0.0.1:8080/v1/chat/completions' },
    brief:       { type: 'string' },
    out:         { type: 'string' },
    build:       { type: 'string', default: 'b10353' },
    vision:      { type: 'boolean', default: false },
    mmproj:      { type: 'string' },
    'mmproj-sha': { type: 'string' },
    json:        { type: 'boolean', default: false },
  };
  const parsed = parseArgs({
    args: argv,
    options,
    allowPositionals: true,
    strict: false,
  });
  assertKnownOptions(parsed.values, options, { command: 'canon draft' });

  const classId = parsed.positionals?.[0];
  if (!classId) {
    throw inputError(
      'INPUT_MISSING_ARG',
      'sdlab canon draft requires a <class_id> positional argument.'
    );
  }
  if (!parsed.values.brief) {
    throw inputError(
      'INPUT_MISSING_FLAG',
      'sdlab canon draft requires --brief "<description>".'
    );
  }

  verifyGlimmerRuntime({
    llamaServerBuild: parsed.values.build,
    vision: Boolean(parsed.values.vision),
    mmprojPath: parsed.values.mmproj || null,
    mmprojSha256: parsed.values['mmproj-sha'] || null,
    verifyFiles: false,
  });

  const draft = await draftCanonClassViaEndpoint({
    endpoint: parsed.values.endpoint,
    classId,
    brief: parsed.values.brief,
  });

  let written = null;
  if (parsed.values.out) {
    written = writePromptsJsonl(parsed.values.out, [draft]);
  }

  if (parsed.values.json) {
    console.log(JSON.stringify({ ok: true, draft, written }, null, 2));
    return;
  }

  console.log(`drafted "${classId}" (status=${draft.status}, judgment=${draft.judgment})`);
  console.log(`  draft_sha256:    ${draft.draft_sha256}`);
  console.log(`  messages_sha256: ${draft.messages_sha256}`);
  if (written) {
    console.log(`  prompts.jsonl:   ${written.promptsPath} (${written.sha256})`);
  }
}
