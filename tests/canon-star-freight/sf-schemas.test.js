/**
 * Star Freight canon schema + entity smoke tests.
 *
 * Asserts that:
 *   - All 5 SF schemas load as valid JSON at v1.0.0.
 *   - Shared _edge_types.json loads and carries the 44+ edge_type enum.
 *   - $ref references in each schema resolve against _edge_types.json.
 *   - Representative SF entries (one per schema) parse + carry the expected
 *     novel fields exercised by Session A's design (turncoat_arc, faction
 *     cover, forbidden_morphology_drift, etc.).
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { loadSchema } from '../../lib/canon-build/load-schema.js';
import { loadCanonEntry } from '../../lib/canon-build/load-entry.js';

const PROJECT_ROOT = join(process.cwd(), 'projects', 'star-freight');
const SCHEMA_DIR = join(PROJECT_ROOT, 'canon', 'schemas');
const CANON_ROOT = join(PROJECT_ROOT, 'canon');

const SCHEMAS = [
  'character.schema.json',
  'location.schema.json',
  'faction.schema.json',
  'ship.schema.json',
  'species.schema.json',
];

// ── schema smoke ───────────────────────────────────────────────────────

test('SF schemas: all five load and resolve to v1.0.0', async () => {
  for (const name of SCHEMAS) {
    const { schema, version } = await loadSchema(join(SCHEMA_DIR, name));
    assert.equal(version, '1.0.0', `${name} should be v1.0.0`);
    assert.ok(schema.$id.includes('/star-freight/'), `${name} $id should namespace under star-freight`);
    assert.equal(schema.type, 'object');
  }
});

test('_edge_types.json: loads and exposes the edge definition', async () => {
  const text = await readFile(join(SCHEMA_DIR, '_edge_types.json'), 'utf-8');
  const et = JSON.parse(text);
  assert.ok(et.definitions?.edge, '_edge_types.json must define #/definitions/edge');
  const enumVals = et.definitions.edge.properties.edge_type.enum;
  assert.ok(Array.isArray(enumVals));
  assert.ok(enumVals.length >= 40, `expected 40+ edge_types, got ${enumVals.length}`);
  // Sentinels from each of the 9 categories
  for (const needed of [
    'crew-of-ship',           // organizational
    'member-of-faction',      // factional
    'crew-trust-bond',        // personal
    'antagonist-personal',    // adversarial
    'informant-to',           // investigation
    'owes-debt-to',           // debt-economic
    'docked-at',              // ship-specific
    'grew-up-at',             // location-specific
    'species-member',         // species-character
  ]) {
    assert.ok(enumVals.includes(needed), `_edge_types enum missing ${needed}`);
  }
});

test('SF schemas: each references _edge_types.json via $ref', async () => {
  for (const name of SCHEMAS) {
    const text = await readFile(join(SCHEMA_DIR, name), 'utf-8');
    assert.ok(
      text.includes('_edge_types.json#/definitions/edge'),
      `${name} should $ref _edge_types.json`,
    );
  }
});

// ── entity smoke ───────────────────────────────────────────────────────

test('SF character: Jace carries the full turncoat_arc block with seeds[]', async () => {
  const entry = await loadCanonEntry(join(CANON_ROOT, 'characters', 'jace-delvari.md'));
  const fm = entry.frontmatter;
  assert.equal(fm.role_class, 'crew-recruitable');
  assert.equal(fm.species, 'terran');
  assert.ok(fm.turncoat_arc, 'Jace must carry a turncoat_arc block');
  assert.equal(fm.turncoat_arc.status, 'covert-intelligence');
  assert.equal(fm.turncoat_arc.handler_faction, 'terran-compact');
  assert.ok(Array.isArray(fm.turncoat_arc.seeds));
  assert.ok(fm.turncoat_arc.seeds.length >= 5, 'at least 5 re-readable seeds expected');
  assert.ok(Array.isArray(fm.turncoat_arc.canon_true_voice));
});

test('SF character: Risa carries reluctant-betrayer turncoat_arc with stand-down path', async () => {
  const entry = await loadCanonEntry(join(CANON_ROOT, 'characters', 'risa-kade.md'));
  const fm = entry.frontmatter;
  assert.equal(fm.turncoat_arc?.status, 'reluctant-betrayer');
  const edgeTypes = (fm.narrative?.relationships || []).map((r) => r.edge_type);
  assert.ok(edgeTypes.includes('potential-stand-down-of'), 'Risa should carry potential-stand-down-of edge');
});

test('SF character: Jace exercises faction_primary + faction_cover pair', async () => {
  const entry = await loadCanonEntry(join(CANON_ROOT, 'characters', 'jace-delvari.md'));
  const fm = entry.frontmatter;
  assert.equal(fm.faction_primary, 'terran-compact');
  assert.equal(typeof fm.faction_cover, 'string');
  assert.notEqual(fm.faction_cover, fm.faction_primary, 'cover must differ from primary');
});

test('SF species: Keth carries species-level forbidden_morphology_drift', async () => {
  const entry = await loadCanonEntry(join(CANON_ROOT, 'species', 'keth.md'));
  const fm = entry.frontmatter;
  assert.equal(fm.biology_class, 'arthropod-humanoid');
  assert.ok(Array.isArray(fm.visual?.forbidden_morphology_drift));
  assert.ok(fm.visual.forbidden_morphology_drift.length >= 3);
  const drift = fm.visual.forbidden_morphology_drift.join(' ').toLowerCase();
  assert.ok(drift.includes('insect') || drift.includes('bug'), 'Keth drift must forbid Earth-insect read');
  assert.ok(drift.includes('chibi') || drift.includes('anime'), 'Keth drift must forbid anime/chibi');
});

test('SF species: Orryn exercises communication_modality.can_lie=no-biological-tell', async () => {
  const entry = await loadCanonEntry(join(CANON_ROOT, 'species', 'orryn.md'));
  const fm = entry.frontmatter;
  assert.equal(fm.communication_modality?.can_lie, 'no-biological-tell');
  assert.equal(fm.scaffold, true, 'Orryn is a scaffold entry (full-game-only)');
});

test('SF species: Veshan is a scaffold entry', async () => {
  const entry = await loadCanonEntry(join(CANON_ROOT, 'species', 'veshan.md'));
  assert.equal(entry.frontmatter.scaffold, true);
  assert.equal(entry.frontmatter.biology_class, 'reptilian-humanoid');
});

test('SF location: TCS Ardent is frozen with the correct scale_context', async () => {
  const entry = await loadCanonEntry(join(CANON_ROOT, 'locations', 'tcs-ardent.md'));
  const fm = entry.frontmatter;
  assert.equal(fm.location_type, 'ship-interior');
  assert.equal(fm.freeze?.status, 'frozen');
  assert.equal(fm.scale_context?.parent_sector, 'Compact core worlds');
  assert.equal(fm.controlled_by_faction, 'terran-compact');
});

test('SF location: Communion Relay sub-locations reference the parent via scale_context', async () => {
  for (const id of ['communion-relay-nav-office', 'communion-relay-archive', 'communion-relay-trade-hall']) {
    const entry = await loadCanonEntry(join(CANON_ROOT, 'locations', `${id}.md`));
    assert.equal(entry.frontmatter.scale_context?.parent_station, 'communion-relay');
  }
});

test('SF faction: Terran Compact stance + faction_edges resolve', async () => {
  const entry = await loadCanonEntry(join(CANON_ROOT, 'factions', 'terran-compact.md'));
  const fm = entry.frontmatter;
  assert.equal(fm.faction_class, 'governmental');
  assert.equal(fm.stance?.toward_player_at_start, 'hostile-containment');
  assert.ok(Array.isArray(fm.stance?.faction_edges));
  assert.ok(fm.stance.faction_edges.length >= 1);
});

test('SF ship: the Corrigan exercises the three-generation-patched hull history', async () => {
  const entry = await loadCanonEntry(join(CANON_ROOT, 'ships', 'the-corrigan.md'));
  const fm = entry.frontmatter;
  assert.equal(fm.ship_class, 'cargo-hauler-small');
  assert.equal(fm.visual?.hull_repair_history, 'three-generation-patched');
  assert.equal(fm.visual?.symmetry, 'asymmetric-from-repair');
  assert.ok(fm.narrative?.named_crew?.includes('kael-maren'));
});

test('SF hero-5: all carry non-auto freeze status', async () => {
  const hero = ['kael-maren', 'renna-vasik', 'jace-delvari', 'risa-kade', 'aldric-solen'];
  for (const id of hero) {
    const entry = await loadCanonEntry(join(CANON_ROOT, 'characters', `${id}.md`));
    const status = entry.frontmatter.freeze?.status;
    assert.notEqual(status, undefined, `${id} must declare freeze.status`);
    assert.notEqual(status, 'auto', `hero-5 ${id} should be frozen or soft-advisory, not auto`);
  }
});

test('SF connective-tissue: all 10 default to auto freeze', async () => {
  const connective = [
    'naia-of-threesong', 'lysa-orin', 'petra-wynn', 'dak-torvo', 'hael-croft',
    'tessik', 'mika-shan', 'old-dren', 'goss', 'callum',
  ];
  for (const id of connective) {
    const entry = await loadCanonEntry(join(CANON_ROOT, 'characters', `${id}.md`));
    const status = entry.frontmatter.freeze?.status ?? 'auto';
    // Naia is a main-cast seed; Session B flagged her soft-advisory candidacy.
    // We accept auto OR soft-advisory for her; others strictly auto.
    if (id === 'naia-of-threesong') {
      assert.ok(['auto', 'soft-advisory'].includes(status));
    } else {
      assert.equal(status, 'auto', `${id} should default to auto (per D8 lean)`);
    }
  }
});

test('SF canon: no entry references deferred Syratha or Vynn', async () => {
  const ids = ['syratha', 'vynn', 'elder-syratha'];
  const dir = join(CANON_ROOT, 'characters');
  const files = await (await import('node:fs/promises')).readdir(dir);
  for (const f of files) {
    if (!f.endsWith('.md')) continue;
    const text = await readFile(join(dir, f), 'utf-8');
    for (const forbidden of ids) {
      assert.ok(
        !text.includes(`target_id: ${forbidden}`),
        `${f} must not reference deferred entity ${forbidden} (Session B triage: defer to full-game)`,
      );
    }
  }
});
