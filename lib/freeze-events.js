/**
 * Append-only event log for freeze transitions (D4).
 *
 * Lives at `<project>/canon-build/freeze-events.jsonl`. One line per event,
 * JSON, stable key order. The jsonl is the audit source of truth; the
 * `freeze.overrides[]` denormalization on the entry is a glance cache.
 *
 * Atomic append: we write the new event as a line-append operation at the
 * OS level. Node's `appendFile` is atomic per-line on POSIX but not
 * guaranteed on Windows when two processes race. For single-operator
 * workflow this is fine; for a paranoid hardening pass later we can add
 * a lockfile. Documented as a known hazard.
 */

import { readFile, appendFile, mkdir } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { existsSync } from 'node:fs';

export const FREEZE_EVENT_TYPES = Object.freeze(['freeze', 'unfreeze', 'override', 'bypass']);

export function eventsPath(projectRoot) {
  return join(projectRoot, 'canon-build', 'freeze-events.jsonl');
}

/**
 * Append one event to the log. Creates the parent dir + file on first write.
 *
 * @param {string} projectRoot — absolute path to the sdlab project root
 * @param {Object} event — at minimum: {type, entity_id, by, reason}
 */
export async function appendEvent(projectRoot, event) {
  if (!FREEZE_EVENT_TYPES.includes(event.type)) {
    throw new Error(`appendEvent: unknown event type "${event.type}" (allowed: ${FREEZE_EVENT_TYPES.join(', ')})`);
  }
  if (!event.entity_id) throw new Error('appendEvent: entity_id required');
  if (!event.by) throw new Error('appendEvent: by required');
  if (!event.reason) throw new Error('appendEvent: reason required');

  const path = eventsPath(projectRoot);
  await mkdir(dirname(path), { recursive: true });

  // Serialize with a stable key order so `diff`-style reading stays readable.
  const ordered = {
    at: event.at || new Date().toISOString(),
    build_hash: event.build_hash ?? null,
    type: event.type,
    entity_id: event.entity_id,
    schema_kind: event.schema_kind ?? null,
    by: event.by,
    reason: event.reason,
    prior_status: event.prior_status ?? null,
    new_status: event.new_status ?? null,
    watch_fields: event.watch_fields ?? null,
    prior_build_hash: event.prior_build_hash ?? null,
  };

  await appendFile(path, JSON.stringify(ordered) + '\n', 'utf-8');
  return ordered;
}

/**
 * Read all events from the log, in append order.
 */
export async function readEvents(projectRoot) {
  const path = eventsPath(projectRoot);
  if (!existsSync(path)) return [];
  const text = await readFile(path, 'utf-8');
  const events = [];
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    try {
      events.push(JSON.parse(line));
    } catch (err) {
      throw new Error(`readEvents: line ${i + 1} of ${path} is not valid JSON (${err.message})`);
    }
  }
  return events;
}

/**
 * Return events for a specific entity, in append order.
 */
export async function readEventsFor(projectRoot, entityId) {
  const all = await readEvents(projectRoot);
  return all.filter((e) => e.entity_id === entityId);
}

/**
 * Return events newer than a given build_hash. Used by `sdlab canon drift`
 * to compute "overrides since last build."
 *
 * Semantics: events are "since X" when their `build_hash` field differs
 * from X. Since the log is append-only, that approximates temporal ordering.
 */
export async function readEventsSince(projectRoot, buildHash) {
  if (!buildHash) return readEvents(projectRoot);
  const all = await readEvents(projectRoot);
  // Find last event with matching build_hash; return everything after it.
  let cutoff = -1;
  for (let i = all.length - 1; i >= 0; i--) {
    if (all[i].build_hash === buildHash) {
      cutoff = i;
      break;
    }
  }
  return cutoff < 0 ? all : all.slice(cutoff + 1);
}
