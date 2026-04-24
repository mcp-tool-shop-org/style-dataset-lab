/**
 * Frontmatter parser for canon entry Markdown files.
 *
 * Canon entry shape:
 *   ---
 *   <YAML frontmatter>
 *   ---
 *   <Markdown body prose>
 *
 * The YAML block is the schema-validated object (fed to emitters' caption
 * + prompt tracks). The body is free prose (fed to emitters' context track
 * only, per the captions-are-load-bearing invariant — prose must never
 * splice into captions).
 */

import { parse as parseYaml } from 'yaml';

const FENCE = '---';

/**
 * Split a file into { frontmatter, body }.
 *
 * Returns { frontmatter: Object, body: string } on success.
 * Throws with a structured message on malformed input.
 *
 * Leading/trailing whitespace before/after the fences is tolerated; a file
 * without a closing fence throws rather than guessing where the body starts.
 *
 * @param {string} text — full file contents
 * @param {string} filename — for error messages only
 */
export function parseFrontmatter(text, filename = '<input>') {
  const normalized = text.replace(/\r\n/g, '\n');

  // Must start with --- (optionally preceded by BOM / whitespace)
  const stripped = normalized.replace(/^\uFEFF/, '').trimStart();
  if (!stripped.startsWith(FENCE)) {
    throw new Error(`parseFrontmatter: ${filename} does not begin with a "---" frontmatter fence`);
  }

  // Find the closing fence. It must be on its own line.
  const afterOpen = stripped.slice(FENCE.length);
  // Skip the newline after the opening fence.
  const newlineIdx = afterOpen.indexOf('\n');
  if (newlineIdx < 0) {
    throw new Error(`parseFrontmatter: ${filename} has no newline after the opening fence`);
  }

  const rest = afterOpen.slice(newlineIdx + 1);
  // Look for "\n---\n" or "\n---" at the end of rest.
  const closeMatch = rest.match(/\n---(\r?\n|$)/);
  if (!closeMatch) {
    throw new Error(`parseFrontmatter: ${filename} has no closing "---" fence`);
  }
  const closeIdx = closeMatch.index;

  const yamlSource = rest.slice(0, closeIdx);
  const body = rest.slice(closeIdx + closeMatch[0].length);

  let frontmatter;
  try {
    frontmatter = parseYaml(yamlSource);
  } catch (err) {
    throw new Error(`parseFrontmatter: ${filename} frontmatter is not valid YAML (${err.message})`);
  }

  if (frontmatter === null || typeof frontmatter !== 'object' || Array.isArray(frontmatter)) {
    throw new Error(`parseFrontmatter: ${filename} frontmatter must be a YAML object (got ${typeof frontmatter})`);
  }

  return {
    frontmatter,
    body: body.replace(/^\n+/, ''),       // trim leading newlines before body
    rawYaml: yamlSource,
  };
}
