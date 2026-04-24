/**
 * Unit tests for lib/rows.js — the canonical adapter input shape (D6).
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  ROW_SCHEMA_VERSION,
  recordToRow,
  canonEntryToRow,
  readDatasetJsonl,
  groupRowsByPartition,
  filterRowsForProfile,
  serializeRow,
  hashRowInputs,
} from '../../lib/rows.js';

const styleProfile = {
  profile_id: 'character-style-lora',
  caption_strategy: 'structured-metadata',
  prompt_strategy: 'trigger-word',
};

// --- recordToRow ---

test('recordToRow produces a canonical row from a records-path record', () => {
  const record = {
    id: 'anchor_01',
    asset_path: 'outputs/approved/anchor_01.png',
    identity: { subject_name: 'Jace', kind: 'hero' },
    canon: { assertion_count: 10, pass_count: 8, faction: 'compact' },
    judgment: { status: 'approved', explanation: 'On-style.' },
  };
  const row = recordToRow(record, 'costume', 'compact', styleProfile, 'train');
  assert.equal(row.schema_version, ROW_SCHEMA_VERSION);
  assert.equal(row.entity_id, 'anchor_01');
  assert.equal(row.schema_kind, 'record');
  assert.equal(row.lane, 'costume');
  assert.equal(row.partition, 'train');
  assert.equal(row.asset_path, 'outputs/approved/anchor_01.png');
  assert.ok(row.caption.includes('character_style_lora'));
  assert.equal(row.trigger, 'character_style_lora');
  assert.equal(row.subject_filter_key, 'Jace');
  assert.equal(row.pass_ratio, 0.8);
});

test('recordToRow returns null for records without an asset_path', () => {
  const row = recordToRow({ id: 'x' }, 'costume', null, styleProfile, 'train');
  assert.equal(row, null);
});

test('recordToRow honors trigger_override via deriveStyleTrigger', () => {
  const profile = { ...styleProfile, trigger_override: 'sf_char' };
  const record = {
    id: 'anchor_02',
    asset_path: 'outputs/approved/anchor_02.png',
    identity: { subject_name: 'X' },
    canon: { assertion_count: 0, pass_count: 0 },
    judgment: { explanation: '' },
  };
  const row = recordToRow(record, 'costume', 'compact', profile, 'train');
  assert.equal(row.trigger, 'sf_char');
  assert.ok(row.caption.startsWith('sf_char'));
});

// --- canonEntryToRow ---

test('canonEntryToRow produces a row from a canon entity frontmatter', () => {
  const row = canonEntryToRow({
    entry: { id: 'heracles', kind: 'hero', forbidden_inputs: ['modern'] },
    schemaKind: 'character',
    assetPath: 'outputs/approved/heracles/anchor.png',
    lane: 'portrait',
    caption: 'g_style style, a hero with lion-skin cloak.',
    trigger: 'g_style',
    partition: 'train',
    entryHash: 'sha256:deadbeef',
    generatedFrom: 'abc123',
  });
  assert.equal(row.entity_id, 'heracles');
  assert.equal(row.schema_kind, 'character');
  assert.equal(row.entity_type, 'hero');
  assert.equal(row.lane, 'portrait');
  assert.equal(row.subject_filter_key, 'heracles');
  assert.equal(row.generated_from, 'abc123');
  assert.equal(row.entry_hash, 'sha256:deadbeef');
  assert.deepEqual(row.forbidden_tokens, ['modern']);
});

// --- readDatasetJsonl + serializeRow ---

test('readDatasetJsonl round-trips serializeRow output', async () => {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-rows-'));
  try {
    const rows = [
      canonEntryToRow({
        entry: { id: 'one', kind: 'mortal' },
        schemaKind: 'character',
        assetPath: 'a.png', lane: 'portrait', caption: 'x',
        trigger: 't', partition: 'train', entryHash: 'h', generatedFrom: 'g',
      }),
      canonEntryToRow({
        entry: { id: 'two', species_tag: 'serpentine' },
        schemaKind: 'monster',
        assetPath: 'b.png', lane: 'creature', caption: 'y',
        trigger: 't', partition: 'val', entryHash: 'h2', generatedFrom: 'g',
      }),
    ];
    const path = join(tmp, 'dataset.jsonl');
    await writeFile(path, rows.map(serializeRow).join('\n') + '\n');
    const loaded = await readDatasetJsonl(path);
    assert.equal(loaded.length, 2);
    assert.equal(loaded[0].entity_id, 'one');
    assert.equal(loaded[1].entity_id, 'two');
    assert.equal(loaded[0].lane, 'portrait');
    assert.equal(loaded[1].lane, 'creature');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('readDatasetJsonl rejects rows with a mismatched schema_version', async () => {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-rows-'));
  try {
    const path = join(tmp, 'bad.jsonl');
    await writeFile(path, JSON.stringify({ schema_version: 'old-1.0', entity_id: 'x' }) + '\n');
    await assert.rejects(() => readDatasetJsonl(path), /schema_version/);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('readDatasetJsonl ignores blank lines', async () => {
  const tmp = await mkdtemp(join(tmpdir(), 'sdlab-rows-'));
  try {
    const row = canonEntryToRow({
      entry: { id: 'one', kind: 'mortal' },
      schemaKind: 'character',
      assetPath: null, lane: 'portrait', caption: 'x',
      trigger: 't', partition: 'train', entryHash: 'h', generatedFrom: 'g',
    });
    const path = join(tmp, 'blanks.jsonl');
    await writeFile(path, `\n${serializeRow(row)}\n\n`);
    const loaded = await readDatasetJsonl(path);
    assert.equal(loaded.length, 1);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

// --- groupRowsByPartition ---

test('groupRowsByPartition groups rows by their partition field', () => {
  const mk = (id, partition) => canonEntryToRow({
    entry: { id, kind: 'mortal' },
    schemaKind: 'character',
    assetPath: null, lane: 'portrait', caption: 'x',
    trigger: 't', partition, entryHash: 'h', generatedFrom: 'g',
  });
  const rows = [mk('a', 'train'), mk('b', 'val'), mk('c', 'train')];
  const grouped = groupRowsByPartition(rows);
  assert.equal(grouped.train.length, 2);
  assert.equal(grouped.val.length, 1);
  assert.equal(grouped.test.length, 0);
});

// --- filterRowsForProfile ---

test('filterRowsForProfile keeps rows matching eligible_lanes', () => {
  const rows = [
    { lane: 'costume', entity_id: 'a', partition: 'train' },
    { lane: 'environment', entity_id: 'b', partition: 'train' },
  ];
  const out = filterRowsForProfile(rows, { eligible_lanes: ['costume'] });
  assert.equal(out.length, 1);
  assert.equal(out[0].entity_id, 'a');
});

test('filterRowsForProfile filters on entity_id_scope (D8 per-character LoRA)', () => {
  const rows = [
    { lane: 'portrait', entity_id: 'heracles', subject_filter_key: 'heracles', partition: 'train' },
    { lane: 'portrait', entity_id: 'perseus', subject_filter_key: 'perseus', partition: 'train' },
  ];
  const out = filterRowsForProfile(rows, { entity_id_scope: 'heracles' });
  assert.equal(out.length, 1);
  assert.equal(out[0].entity_id, 'heracles');
});

test('filterRowsForProfile composes eligible_lanes AND entity_id_scope', () => {
  const rows = [
    { lane: 'portrait', entity_id: 'heracles', subject_filter_key: 'heracles', partition: 'train' },
    { lane: 'creature', entity_id: 'heracles', subject_filter_key: 'heracles', partition: 'train' },
    { lane: 'portrait', entity_id: 'perseus',  subject_filter_key: 'perseus',  partition: 'train' },
  ];
  const out = filterRowsForProfile(rows, {
    eligible_lanes: ['portrait'],
    entity_id_scope: 'heracles',
  });
  assert.equal(out.length, 1);
  assert.equal(out[0].entity_id, 'heracles');
  assert.equal(out[0].lane, 'portrait');
});

test('filterRowsForProfile: empty or missing filters pass everything', () => {
  const rows = [
    { lane: 'x', entity_id: 'a', partition: 'train' },
    { lane: 'y', entity_id: 'b', partition: 'train' },
  ];
  assert.equal(filterRowsForProfile(rows, {}).length, 2);
  assert.equal(filterRowsForProfile(rows, { eligible_lanes: [] }).length, 2);
});

// --- hashRowInputs ---

test('hashRowInputs is deterministic and changes on any input change', () => {
  const base = {
    entryBody: 'a',
    schemaVersion: '1.0.0',
    buildConfigJson: '{}',
    projectFingerprint: 'f',
  };
  const h1 = hashRowInputs(base);
  const h2 = hashRowInputs(base);
  assert.equal(h1, h2);
  assert.notEqual(hashRowInputs({ ...base, entryBody: 'b' }), h1);
  assert.notEqual(hashRowInputs({ ...base, schemaVersion: '1.0.1' }), h1);
  assert.notEqual(hashRowInputs({ ...base, buildConfigJson: '{"k":1}' }), h1);
  assert.notEqual(hashRowInputs({ ...base, projectFingerprint: 'g' }), h1);
});
