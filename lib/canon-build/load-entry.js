/**
 * Canon entry loader.
 *
 * Reads a canon MD file, splits frontmatter from body, returns a normalized
 * entry object. Validation against the schema happens later in the
 * orchestrator (after the schema has been loaded).
 */

import { readFile, readdir } from 'node:fs/promises';
import { join, extname, basename } from 'node:path';
import { existsSync } from 'node:fs';
import { parseFrontmatter } from './frontmatter.js';

/**
 * Load a single canon entry file.
 *
 * @param {string} filePath — absolute path to a .md file
 * @returns {Promise<{ frontmatter: Object, body: string, rawYaml: string, rawText: string, filePath: string }>}
 */
export async function loadCanonEntry(filePath) {
  const text = await readFile(filePath, 'utf-8');
  const parsed = parseFrontmatter(text, filePath);
  return {
    frontmatter: parsed.frontmatter,
    body: parsed.body,
    rawYaml: parsed.rawYaml,
    rawText: text,
    filePath,
  };
}

/**
 * Load all canon entries in a directory.
 *
 * Non-.md files are skipped; .md files that fail to parse throw with the
 * filename included so the operator can fix the offending entry.
 *
 * @param {string} dir — absolute path to a canon-type directory
 * @returns {Promise<Array<{frontmatter, body, rawYaml, rawText, filePath}>>}
 */
export async function loadCanonEntriesInDir(dir) {
  if (!existsSync(dir)) return [];
  const files = await readdir(dir);
  const entries = [];
  for (const file of files.sort()) {
    if (extname(file) !== '.md') continue;
    const filePath = join(dir, file);
    const entry = await loadCanonEntry(filePath);
    entries.push(entry);
  }
  return entries;
}

/**
 * Derive an entity id from a canon entry.
 * Prefers frontmatter.id; falls back to filename stem for entries that
 * haven't added the id field yet (validation will reject those downstream).
 */
export function entryId(entry) {
  if (entry.frontmatter?.id) return entry.frontmatter.id;
  return basename(entry.filePath, '.md');
}
