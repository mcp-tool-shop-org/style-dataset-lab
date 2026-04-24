/**
 * Unit tests for lib/freeze-events.js — the append-only audit log (D4).
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  FREEZE_EVENT_TYPES,
  eventsPath,
  appendEvent,
  readEvents,
  readEventsFor,
  readEventsSince,
} from '../../lib/freeze-events.js';

test('eventsPath: always under canon-build/freeze-events.jsonl', () => {
  const path = eventsPath('/some/project/root');
  assert.ok(path.replace(/\\/g, '/').endsWith('canon-build/freeze-events.jsonl'));
});

test('appendEvent: creates the parent dir + file on first write', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-fe-'));
  try {
    await appendEvent(dir, {
      type: 'freeze',
      entity_id: 'heracles',
      by: 'mike',
      reason: 'Labor III locked',
    });
    const text = await readFile(eventsPath(dir), 'utf-8');
    const parsed = JSON.parse(text.trim());
    assert.equal(parsed.type, 'freeze');
    assert.equal(parsed.entity_id, 'heracles');
    assert.equal(parsed.by, 'mike');
    assert.ok(parsed.at);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('appendEvent: refuses unknown event types', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-fe-'));
  try {
    await assert.rejects(
      () => appendEvent(dir, { type: 'mystery', entity_id: 'x', by: 'y', reason: 'z' }),
      /unknown event type/,
    );
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('appendEvent: requires entity_id, by, reason', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-fe-'));
  try {
    await assert.rejects(() => appendEvent(dir, { type: 'freeze', by: 'x', reason: 'z' }), /entity_id/);
    await assert.rejects(() => appendEvent(dir, { type: 'freeze', entity_id: 'x', reason: 'z' }), /by/);
    await assert.rejects(() => appendEvent(dir, { type: 'freeze', entity_id: 'x', by: 'y' }), /reason/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('readEvents: preserves append order', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-fe-'));
  try {
    await appendEvent(dir, { type: 'freeze', entity_id: 'a', by: 'mike', reason: 'r1' });
    await appendEvent(dir, { type: 'freeze', entity_id: 'b', by: 'mike', reason: 'r2' });
    await appendEvent(dir, { type: 'unfreeze', entity_id: 'a', by: 'mike', reason: 'r3' });
    const events = await readEvents(dir);
    assert.equal(events.length, 3);
    assert.equal(events[0].entity_id, 'a');
    assert.equal(events[1].entity_id, 'b');
    assert.equal(events[2].type, 'unfreeze');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('readEvents: returns [] for a project with no event log yet', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-fe-'));
  try {
    const events = await readEvents(dir);
    assert.deepEqual(events, []);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('readEventsFor: filters by entity_id', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-fe-'));
  try {
    await appendEvent(dir, { type: 'freeze', entity_id: 'heracles', by: 'mike', reason: 'r1' });
    await appendEvent(dir, { type: 'freeze', entity_id: 'perseus', by: 'mike', reason: 'r2' });
    await appendEvent(dir, { type: 'override', entity_id: 'heracles', by: 'mike', reason: 'r3' });
    const events = await readEventsFor(dir, 'heracles');
    assert.equal(events.length, 2);
    assert.ok(events.every((e) => e.entity_id === 'heracles'));
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('readEventsSince: returns events appended after a given build_hash', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-fe-'));
  try {
    await appendEvent(dir, { type: 'freeze', entity_id: 'a', by: 'mike', reason: 'r1', build_hash: 'sha-1' });
    await appendEvent(dir, { type: 'freeze', entity_id: 'b', by: 'mike', reason: 'r2', build_hash: 'sha-2' });
    await appendEvent(dir, { type: 'unfreeze', entity_id: 'a', by: 'mike', reason: 'r3', build_hash: 'sha-3' });
    const since = await readEventsSince(dir, 'sha-2');
    assert.equal(since.length, 1);
    assert.equal(since[0].entity_id, 'a');
    assert.equal(since[0].type, 'unfreeze');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('readEventsSince: returns all events when build_hash is null', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'sdlab-fe-'));
  try {
    await appendEvent(dir, { type: 'freeze', entity_id: 'a', by: 'mike', reason: 'r' });
    const since = await readEventsSince(dir, null);
    assert.equal(since.length, 1);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('FREEZE_EVENT_TYPES is immutable', () => {
  assert.ok(Object.isFrozen(FREEZE_EVENT_TYPES));
  assert.deepEqual([...FREEZE_EVENT_TYPES].sort(), ['bypass', 'freeze', 'override', 'unfreeze']);
});
