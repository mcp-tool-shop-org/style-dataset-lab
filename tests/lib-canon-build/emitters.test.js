/**
 * Per-schema emitter tests — asserts each emitter produces the three
 * projections (caption, prompt, context) with the right shape + invariants.
 *
 * Invariants across all schemas:
 *   - caption is frontmatter-only (body prose never splices in)
 *   - prompt template is frontmatter-only
 *   - context includes the provenance frontmatter + H2 sections
 *   - context is the ONLY projection allowed to splice body prose
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { emitMonster } from '../../lib/canon-build/emitters/monster.js';
import { emitCharacter } from '../../lib/canon-build/emitters/character.js';
import { emitDeity } from '../../lib/canon-build/emitters/deity.js';
import { emitLocation } from '../../lib/canon-build/emitters/location.js';
import { emitRelic } from '../../lib/canon-build/emitters/relic.js';

const CTX = { trigger: 'gr_style', lane: 'creature', generatedFrom: 'abc', entryHash: 'hash123' };

// --- Monster ---

test('monster emitter: caption uses species_tag + signature_features', () => {
  const entry = {
    frontmatter: {
      id: 'nemean-lion',
      species_tag: 'quadruped',
      signature_features: ['impenetrable golden hide', 'maned head'],
      anatomy_descriptor: { heads: 1, limbs: 4, notable: ['lion-of-prey build'] },
      forbidden_inputs: ['generic lion', 'cartoon stylization'],
      lineage_reference: 'typhon-echidna',
      scale_indicator: 'larger',
      sources: ['Apollodorus II.5.1'],
    },
    body: 'The Nemean Lion dwells on the slopes of Mount Tretos, sacred to Selene.',
  };
  const out = emitMonster(entry, CTX);
  assert.equal(out.schemaKind, 'monster');
  assert.ok(out.caption.startsWith('gr_style style'));
  assert.ok(out.caption.includes('quadruped'));
  assert.ok(out.caption.includes('impenetrable golden hide'));
  // Body prose MUST NOT leak into caption. The distinctive body vocabulary
  // ("Mount Tretos", "Selene") appears nowhere in the schema fields.
  assert.ok(!out.caption.includes('Mount Tretos'));
  assert.ok(!out.caption.includes('Selene'));
});

test('monster emitter: prompt template uses Jinja placeholder for trigger', () => {
  const entry = {
    frontmatter: {
      id: 'hydra',
      species_tag: 'serpentine',
      signature_features: ['nine heads', 'venomous breath'],
      anatomy_descriptor: { heads: 9, limbs: 0, notable: ['regenerating heads'] },
      forbidden_inputs: ['generic dragon'],
      lineage_reference: 'typhon-echidna',
      scale_indicator: 'larger',
      sources: ['Apollodorus II.5.2'],
    },
    body: '',
  };
  const out = emitMonster(entry, CTX);
  assert.ok(out.prompt.includes('{{ trigger }}'));
  assert.ok(out.prompt.includes('{{ negative_base }}'));
  // 9-head anatomy should land in the prompt, not the caption.
  assert.ok(out.prompt.includes('9 heads'));
});

test('monster emitter: suppresses human features when human_element is null', () => {
  const entry = {
    frontmatter: {
      id: 'hydra',
      species_tag: 'serpentine',
      signature_features: ['nine heads'],
      anatomy_descriptor: { heads: 9, limbs: 0, notable: [] },
      forbidden_inputs: [],
      lineage_reference: 'typhon-echidna',
      scale_indicator: 'larger',
      sources: ['X'],
    },
    body: '',
  };
  const out = emitMonster(entry, CTX);
  assert.ok(out.prompt.includes('human features'));
  assert.ok(out.prompt.includes('human face'));
});

test('monster emitter: allows human portion when species_tag=hybrid and human_element set', () => {
  const entry = {
    frontmatter: {
      id: 'minotaur',
      species_tag: 'hybrid',
      signature_features: ['bull head', 'human body'],
      anatomy_descriptor: { heads: 1, limbs: 4, notable: [] },
      human_element: { scope: 'torso and arms' },
      forbidden_inputs: [],
      lineage_reference: 'none',
      scale_indicator: 'larger',
      sources: ['X'],
    },
    body: '',
  };
  const out = emitMonster(entry, CTX);
  assert.ok(out.prompt.includes('torso and arms'));
  // Human-suppression negative should NOT apply when the creature legitimately has a human portion.
  assert.ok(!out.prompt.includes('human features'));
});

test('monster emitter: context.md carries provenance frontmatter and H2 sections', () => {
  const entry = {
    frontmatter: {
      id: 'hydra',
      species_tag: 'serpentine',
      signature_features: ['nine heads', 'venom'],
      anatomy_descriptor: { heads: 9, limbs: 0, notable: [] },
      forbidden_inputs: ['generic dragon'],
      lineage_reference: 'typhon-echidna',
      scale_indicator: 'larger',
      sources: ['Apollodorus'],
    },
    body: 'Hydra lives in Lerna swamp.',
  };
  const out = emitMonster(entry, CTX);
  assert.ok(out.context.includes('entity_id: hydra'));
  assert.ok(out.context.includes('generated_from: abc'));
  assert.ok(out.context.includes('## Identity'));
  assert.ok(out.context.includes('## Anatomy'));
  assert.ok(out.context.includes('## Combat intent'));
  assert.ok(out.context.includes('## Forbidden'));
  assert.ok(out.context.includes('## Sources'));
  // Body prose IS allowed to show up in context (Notes section).
  assert.ok(out.context.includes('Lerna swamp'));
});

// --- Character ---

test('character emitter: caption uses kind + attire + silhouette', () => {
  const entry = {
    frontmatter: {
      id: 'heracles',
      kind: 'hero',
      visual: {
        silhouette_cue: 'club-and-lion-hide',
        attire: 'lion-skin cloak over naked torso',
        build: 'heroic-muscular',
        hair: 'sun-streaked long hair',
        eyes: 'dark, brooding',
        age_band: 'young-adult',
        art_lane: 'full-body',
        palette: ['#c2a179', '#6b3a1a'],
      },
      narrative: { role: 'Protagonist', voice: ['blunt', 'wry'], motivation: 'Atonement', arc_beats: ['Birth', 'Labors', 'Apotheosis'] },
      sources: ['Apollodorus'],
    },
    body: '',
  };
  const out = emitCharacter(entry, { ...CTX, lane: 'full-body' });
  assert.ok(out.caption.includes('hero wearing lion-skin cloak'));
  assert.ok(out.caption.includes('club-and-lion-hide'));
  assert.ok(out.caption.includes('heroic-muscular'));
});

test('character emitter: mortal kind adds divine-radiance suppression to negative', () => {
  const entry = {
    frontmatter: {
      id: 'perseus',
      kind: 'mortal',
      visual: { silhouette_cue: 'x', attire: 'x', build: 'athletic', hair: 'x', eyes: 'x', age_band: 'young-adult', art_lane: 'portrait', palette: ['#000000'] },
      narrative: { role: 'x', voice: ['x', 'y'], motivation: 'x', arc_beats: ['a', 'b', 'c'] },
      sources: ['x'],
    },
    body: '',
  };
  const out = emitCharacter(entry, CTX);
  assert.ok(out.prompt.includes('divine radiance'));
});

// --- Deity ---

test('deity emitter: caption + prompt carry generation + signature_attribute', () => {
  const entry = {
    frontmatter: {
      id: 'zeus',
      generation: 'olympian',
      domains: ['thunder', 'kingship'],
      visual: {
        silhouette_cue: 'bearded king with thunderbolt',
        palette: ['#d4af37'],
        attire: 'himation',
        divine_radiance: 'stormlight',
        signature_attribute: 'thunderbolt',
        age_band: 'mature',
        art_lane: 'throne',
      },
      narrative: { role: 'x', voice: ['x', 'y'], core_behavior: 'Judges and seduces; upholds xenia' },
      sources: ['Homeric Hymns'],
    },
    body: '',
  };
  const out = emitDeity(entry, CTX);
  assert.ok(out.caption.includes('olympian'));
  assert.ok(out.caption.includes('holding thunderbolt'));
  assert.ok(out.prompt.includes('thunderbolt'));
  // Olympian generation should suppress chthonic features in negative.
  assert.ok(out.prompt.includes('monstrous features'));
});

test('deity emitter: divine_radiance=none-on-earth injects suppression', () => {
  const entry = {
    frontmatter: {
      id: 'hades',
      generation: 'chthonic',
      domains: ['underworld'],
      visual: {
        silhouette_cue: 'x', palette: ['#000000'], attire: 'x',
        divine_radiance: 'none-on-earth',
        signature_attribute: 'bident', age_band: 'mature', art_lane: 'throne',
      },
      narrative: { role: 'x', voice: ['x', 'y'], core_behavior: 'Rules the dead' },
      sources: ['x'],
    },
    body: '',
  };
  const out = emitDeity(entry, CTX);
  assert.ok(out.prompt.includes('any visible radiance'));
});

// --- Location ---

test('location emitter: caption uses location_type + region + lighting', () => {
  const entry = {
    frontmatter: {
      id: 'delphi',
      location_type: 'oracle-site',
      region: 'attica',
      era_logic: 'heroic-age',
      mythic_events: [{ event: 'Pythia prophesies to Oedipus', era: 'heroic-age', source: 'Sophocles' }],
      visual: {
        silhouette_cue: 'cliff-flanked sanctuary with omphalos',
        palette: ['#d2b48c'],
        lighting_mood: 'oracle-vapor',
        material_language: 'sun-bleached marble',
        scale_logic: 'monumental',
        art_lane: 'ritual',
        signature_props: ['tripod', 'omphalos'],
      },
      narrative: { role: 'oracle hub', cultural_weight: 'panhellenic-sacred' },
      sources: ['Pausanias'],
    },
    body: '',
  };
  const out = emitLocation(entry, CTX);
  assert.ok(out.caption.includes('oracle-site in attica'));
  assert.ok(out.caption.includes('oracle-vapor'));
  assert.ok(out.prompt.includes('tripod'));
});

test('location emitter: mythic_events render as bullets in context', () => {
  const entry = {
    frontmatter: {
      id: 'nemea',
      location_type: 'mountain',
      region: 'peloponnese',
      era_logic: 'heroic-age',
      mythic_events: [
        { event: 'Heracles strangles the Nemean Lion', era: 'heroic-age', source: 'Apollodorus II.5.1', participants: ['heracles', 'nemean-lion'] },
      ],
      visual: {
        silhouette_cue: 'cave-lit-entrance', palette: ['#333333'], lighting_mood: 'cave-gloom',
        material_language: 'rough limestone', scale_logic: 'intimate', art_lane: 'liminal-approach',
      },
      narrative: { role: 'labor-site', cultural_weight: 'regional-sacred' },
      sources: ['x'],
    },
    body: '',
  };
  const out = emitLocation(entry, CTX);
  assert.ok(out.context.includes('## Mythic Events'));
  assert.ok(out.context.includes('Heracles strangles the Nemean Lion'));
  assert.ok(out.context.includes('participants: heracles, nemean-lion'));
});

// --- Relic ---

test('relic emitter: caption uses relic_type + silhouette + materials', () => {
  const entry = {
    frontmatter: {
      id: 'aegis',
      relic_type: 'shield',
      origin: 'crafted-by-hephaestus',
      materials: ['bronze', 'goat-hide', 'gorgoneion'],
      visual: {
        silhouette_cue: 'round bronze shield with Gorgon head',
        palette: ['#b08d57'], scale: 'armor-scale',
        signature_markings: ['serpent rim', 'Gorgoneion center'],
        art_lane: 'object-portrait',
      },
      narrative: { role: 'divine shield of Zeus, loaned to Athena', mythic_significance: 'cosmic-stake' },
      powers: [{ effect: 'strikes fear in mortals who see it' }],
      ownership_chain: [
        { owner_id: 'zeus', era: 'primordial', acquired_by: 'crafted' },
        { owner_id: 'athena', era: 'titanomachy', acquired_by: 'gift', acquired_from: 'zeus' },
      ],
      sources: ['Homer Iliad'],
    },
    body: '',
  };
  const out = emitRelic(entry, CTX);
  assert.ok(out.caption.includes('shield'));
  assert.ok(out.caption.includes('round bronze shield'));
  assert.ok(out.caption.includes('bronze and goat-hide and gorgoneion'));
  assert.ok(out.context.includes('## Powers'));
  assert.ok(out.context.includes('## Ownership Chain'));
  assert.ok(out.context.includes('athena via gift from zeus'));
});

// --- Cross-schema invariant: caption never contains body prose ---

test('all emitters: caption excludes body prose even when body is non-empty', () => {
  const bodyProse = 'This is body prose that must never leak into captions.';
  const fixtures = [
    {
      fn: emitMonster,
      entry: {
        frontmatter: {
          id: 'x', species_tag: 'serpentine', signature_features: ['a', 'b'],
          anatomy_descriptor: { heads: 1, limbs: 0, notable: [] },
          forbidden_inputs: [], lineage_reference: 'none', scale_indicator: 'larger', sources: ['y'],
        },
        body: bodyProse,
      },
    },
    {
      fn: emitCharacter,
      entry: {
        frontmatter: {
          id: 'x', kind: 'mortal',
          visual: { silhouette_cue: 'a', attire: 'b', build: 'lean', hair: 'c', eyes: 'd', age_band: 'youth', art_lane: 'portrait', palette: ['#ffffff'] },
          narrative: { role: 'r', voice: ['a', 'b'], motivation: 'x', arc_beats: ['a', 'b', 'c'] },
          sources: ['x'],
        },
        body: bodyProse,
      },
    },
    {
      fn: emitDeity,
      entry: {
        frontmatter: {
          id: 'x', generation: 'olympian', domains: ['a'],
          visual: { silhouette_cue: 'a', palette: ['#000000'], attire: 'b', divine_radiance: 'aureole', signature_attribute: 'c', age_band: 'mature', art_lane: 'throne' },
          narrative: { role: 'r', voice: ['a', 'b'], core_behavior: 'x' },
          sources: ['x'],
        },
        body: bodyProse,
      },
    },
    {
      fn: emitLocation,
      entry: {
        frontmatter: {
          id: 'x', location_type: 'city', region: 'attica', era_logic: 'heroic-age',
          mythic_events: [{ event: 'e', era: 'heroic-age', source: 's' }],
          visual: { silhouette_cue: 'a', palette: ['#000000'], lighting_mood: 'noon-sun', material_language: 'b', scale_logic: 'human-scale', art_lane: 'establishing' },
          narrative: { role: 'r', cultural_weight: 'regional-sacred' },
          sources: ['x'],
        },
        body: bodyProse,
      },
    },
    {
      fn: emitRelic,
      entry: {
        frontmatter: {
          id: 'x', relic_type: 'weapon', origin: 'hero-forged',
          visual: { silhouette_cue: 'a', palette: ['#000000'], signature_markings: ['m'], scale: 'weapon-scale', art_lane: 'object-portrait' },
          narrative: { role: 'r', mythic_significance: 'minor-aid' },
          powers: [{ effect: 'e' }],
          ownership_chain: [{ owner_id: 'x', era: 'heroic-age', acquired_by: 'found' }],
          sources: ['x'],
        },
        body: bodyProse,
      },
    },
  ];

  for (const { fn, entry } of fixtures) {
    const out = fn(entry, CTX);
    assert.ok(!out.caption.includes('body prose'),
      `${out.schemaKind} caption leaked body prose: ${out.caption}`);
    assert.ok(!out.prompt.includes('body prose'),
      `${out.schemaKind} prompt template leaked body prose: ${out.prompt}`);
    // Body prose IS expected to land in context.
    assert.ok(out.context.includes('body prose'),
      `${out.schemaKind} context dropped body prose (should appear in Notes section)`);
  }
});
