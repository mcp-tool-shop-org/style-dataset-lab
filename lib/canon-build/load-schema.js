/**
 * Schema loader for canon-build.
 *
 * Reads a JSON Schema file and returns { schema, version }.
 *
 * `version` resolution (per post-research D7):
 *   1. If the schema's top-level `version` field is a string, use it.
 *   2. Otherwise fall back to SHA-256 of the schema file contents, prefixed
 *      with `content-sha:`. Any textual change (including whitespace)
 *      invalidates the fallback. Documented as a defensive bridge for
 *      projects whose schemas haven't been version-stamped yet.
 */

import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { inputError } from '../errors.js';

/**
 * Load and resolve a single schema file.
 *
 * @param {string} schemaPath — absolute path to <name>.schema.json
 * @returns {Promise<{ schema: Object, version: string, fileBytes: Buffer }>}
 */
export async function loadSchema(schemaPath) {
  const buf = await readFile(schemaPath);
  let schema;
  try {
    schema = JSON.parse(buf.toString('utf-8'));
  } catch (err) {
    throw inputError(
      'CANON_SCHEMA_INVALID_JSON',
      `Schema file is not valid JSON: ${schemaPath} (${err.message})`,
      'Validate the schema file with a JSON linter; malformed schemas cannot be used to validate canon entries.',
    );
  }

  let version;
  if (typeof schema.version === 'string' && schema.version.length > 0) {
    version = schema.version;
  } else {
    const hash = createHash('sha256').update(buf).digest('hex');
    version = `content-sha:${hash}`;
  }

  return { schema, version, fileBytes: buf };
}
