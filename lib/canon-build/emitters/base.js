/**
 * Shared helpers for per-schema emitters.
 *
 * Emitters produce three outputs per canon entry:
 *   - caption: the dataset.jsonl caption string (reads frontmatter fields ONLY)
 *   - prompt:  the prompts/<id>.j2 template source (reads frontmatter ONLY)
 *   - context: the context/<id>.md body (reads frontmatter + body — body is the
 *              one place canon prose is allowed to land)
 *
 * The strict separation between caption/prompt (frontmatter-only) and context
 * (frontmatter + body) enforces the captions-are-load-bearing invariant: MD
 * body prose can never splice into a training caption. See
 * memory/feedback_captions_are_load_bearing.md.
 */

/**
 * Default per-schema context length cap (lines).
 */
export const DEFAULT_CONTEXT_MAX_LINES = 300;

/**
 * Resolve the max_lines cap for a schema.
 * Looks up context_limits[schemaKind].max_lines, falling back to default.
 */
export function resolveContextMaxLines(schemaKind, contextLimits) {
  const specific = contextLimits?.[schemaKind]?.max_lines;
  if (typeof specific === 'number' && specific > 0) return specific;
  const def = contextLimits?.default?.max_lines;
  if (typeof def === 'number' && def > 0) return def;
  return DEFAULT_CONTEXT_MAX_LINES;
}

/**
 * Build the frontmatter block for a context/<id>.md file.
 *
 * Stamps provenance for audit: entity_id, schema_kind, generated_from, entry_hash.
 */
export function contextFrontmatter({ entityId, schemaKind, generatedFrom, entryHash }) {
  const lines = [
    '---',
    `entity_id: ${entityId}`,
    `schema_kind: ${schemaKind}`,
    `generated_from: ${generatedFrom}`,
    `entry_hash: ${entryHash}`,
    '---',
    '',
  ];
  return lines.join('\n');
}

/**
 * Render an H2 section with a heading + bullet items or free text.
 *
 * Skips rendering entirely when value is null/undefined/empty.
 */
export function renderSection(heading, content) {
  if (content == null) return '';
  if (Array.isArray(content)) {
    if (content.length === 0) return '';
    const bullets = content
      .map((item) => (typeof item === 'string' ? `- ${item}` : `- ${JSON.stringify(item)}`))
      .join('\n');
    return `## ${heading}\n${bullets}\n\n`;
  }
  if (typeof content === 'object') {
    const entries = Object.entries(content).filter(([, v]) => v != null && v !== '');
    if (entries.length === 0) return '';
    const bullets = entries
      .map(([k, v]) => `- ${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
      .join('\n');
    return `## ${heading}\n${bullets}\n\n`;
  }
  const s = String(content).trim();
  if (!s) return '';
  return `## ${heading}\n${s}\n\n`;
}

/**
 * Render an array of pairs as a key-value bullet list under an H2.
 * Skips the whole section if every value is empty.
 */
export function renderKeyValueSection(heading, pairs) {
  const kept = pairs.filter(([, v]) => v != null && v !== '' && !(Array.isArray(v) && v.length === 0));
  if (kept.length === 0) return '';
  const bullets = kept
    .map(([k, v]) => `- ${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
    .join('\n');
  return `## ${heading}\n${bullets}\n\n`;
}

/**
 * Compute the negative-prompt base string for an entry.
 *
 * Joins forbidden_inputs with ", " — the exact shape consumed by the Jinja
 * template at render time. Project-level negatives are injected at render
 * time by the ComfyUI adapter, not baked into the emitted template.
 */
export function renderNegativeBase(entry) {
  const tokens = Array.isArray(entry.forbidden_inputs) ? entry.forbidden_inputs : [];
  return tokens.join(', ');
}

/**
 * Enforce the context length cap. Throws a structured error if the rendered
 * body exceeds max_lines.
 *
 * The error is returned via a callback rather than thrown directly so the
 * orchestrator can batch all failures and surface them together instead of
 * failing on the first offender.
 */
export function checkContextLength(body, maxLines, entityId, schemaKind) {
  const lineCount = body.split('\n').length;
  if (lineCount > maxLines) {
    return {
      entityId,
      schemaKind,
      lineCount,
      maxLines,
    };
  }
  return null;
}
