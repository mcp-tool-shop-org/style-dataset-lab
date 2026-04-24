/**
 * Deity emitter (D5: deity.schema.json).
 *
 * Caption: trigger + " style, " + generation + " deity, " + silhouette_cue + ", holding " + signature_attribute
 * Prompt positive: silhouette_cue + signature_attribute + epithets + divine_radiance rendered as adjective + body + attire + palette + signature_features + behavior hint
 * Prompt negative: forbidden_inputs + generation-specific guards + radiance=none-on-earth suppression
 * Context sections: Identity, Epithets, Role & Voice, Relationships, Cult, Mechanical (optional), Forbidden, Sources
 */

import { contextFrontmatter, renderKeyValueSection, renderSection } from './base.js';

const SCHEMA_KIND = 'deity';

const RADIANCE_ADJECTIVES = {
  'subtle': 'with a subtle aura',
  'aureole': 'with a subtle golden halo',
  'golden-aura': 'bathed in golden aura',
  'stormlight': 'crackling with stormlight',
  'underworld-pallor': 'lit by cold underworld pallor',
  'blinding': 'radiant with blinding light',
  'none-on-earth': '',
};

export function emitDeity(entry, ctx) {
  const fm = entry.frontmatter;
  return {
    schemaKind: SCHEMA_KIND,
    caption: buildCaption(fm, ctx),
    prompt: buildPromptTemplate(fm),
    context: buildContext(entry, ctx),
  };
}

function buildCaption(fm, ctx) {
  const v = fm.visual || {};
  const segments = [];
  if (ctx.trigger) segments.push(`${ctx.trigger} style`);

  const generation = fm.generation || 'greek';
  const radiance = v.divine_radiance && v.divine_radiance !== 'none-on-earth'
    ? `${v.divine_radiance} `
    : '';
  segments.push(`${generation} ${radiance}deity`);

  if (v.silhouette_cue) segments.push(v.silhouette_cue);
  if (v.signature_attribute) segments.push(`holding ${v.signature_attribute}`);

  return segments.join(', ');
}

function buildPromptTemplate(fm) {
  const v = fm.visual || {};
  const n = fm.narrative || {};
  const lines = [];
  lines.push(`{# auto-generated canon-build prompt template — do not hand-edit #}`);
  lines.push(`{{ trigger }} style{% if character_trigger %}, {{ character_trigger }}{% endif %}, a ${fm.generation || 'greek'} deity, ${v.silhouette_cue || ''}.`);

  if (v.signature_attribute) lines.push(`{# attribute #} holding ${v.signature_attribute}`);
  if (Array.isArray(fm.epithets) && fm.epithets.length) {
    lines.push(`{# epithet #} ${fm.epithets.slice(0, 2).join(', ')}`);
  }
  const radiance = RADIANCE_ADJECTIVES[v.divine_radiance] || '';
  if (radiance) lines.push(`{# radiance #} ${radiance}`);

  const body = [];
  if (v.build) body.push(`${v.build} build`);
  if (v.hair) body.push(v.hair);
  if (v.age_band) body.push(`${v.age_band} age`);
  if (body.length) lines.push(`{# body #} ${body.join(', ')}`);

  if (v.attire) lines.push(`{# attire #} ${v.attire}`);
  if (Array.isArray(v.palette) && v.palette.length) {
    lines.push(`{# palette #} ${v.palette.join(' ')}`);
  }
  if (Array.isArray(fm.signature_features) && fm.signature_features.length) {
    lines.push(`{# signature #} ${fm.signature_features.join(', ')}`);
  }
  if (n.core_behavior) {
    lines.push(`{# behavior #} ${firstClause(n.core_behavior)}`);
  }

  lines.push('---');
  lines.push(`{{ negative_base }}`);
  if (fm.generation === 'olympian') {
    lines.push(', monstrous features, chthonic pallor');
  }
  if (v.divine_radiance === 'none-on-earth') {
    lines.push(', any visible radiance, aureole, glow');
  }
  return lines.join('\n') + '\n';
}

function buildContext(entry, ctx) {
  const fm = entry.frontmatter;
  const n = fm.narrative || {};
  const m = fm.mechanical;
  const out = [];

  out.push(contextFrontmatter({
    entityId: fm.id,
    schemaKind: SCHEMA_KIND,
    generatedFrom: ctx.generatedFrom,
    entryHash: ctx.entryHash,
  }));
  out.push(`# ${titleFromId(fm.id)}\n`);

  out.push(renderKeyValueSection('Identity', [
    ['generation', fm.generation],
    ['domains', fm.domains],
  ]));

  out.push(renderSection('Epithets', fm.epithets || null));

  out.push(renderKeyValueSection('Role & Voice', [
    ['role', n.role],
    ['voice', n.voice],
    ['core_behavior', n.core_behavior],
    ['alignment_to_hero', n.alignment_to_hero],
    ['speech_register', n.speech_register],
    ['vocabulary_forbidden', n.vocabulary_forbidden],
  ]));

  out.push(renderKeyValueSection('Relationships', [
    ['children', n.children],
    ['rivalries', n.rivalries],
    ['consorts', n.consorts],
    ['parents', fm.parentage?.parents],
  ]));

  out.push(renderKeyValueSection('Cult', [
    ['cult_sites', fm.cult_sites],
    ['sacred_animals', fm.sacred_animals],
    ['sacred_plants', fm.sacred_plants],
  ]));

  if (m && typeof m === 'object' && Object.values(m).some((v) => v != null)) {
    out.push(renderKeyValueSection('Mechanical', [
      ['favor_grants', m.favor_grants],
      ['wrath_triggers', m.wrath_triggers],
      ['encounter_class', m.encounter_class],
    ]));
  }

  out.push(renderSection('Forbidden', fm.forbidden_inputs || null));
  out.push(renderSection('Sources', fm.sources || null));

  if (entry.body && entry.body.trim()) {
    out.push(`## Notes\n${entry.body.trim()}\n`);
  }

  return out.join('');
}

function firstClause(s) {
  if (!s) return '';
  const idx = s.search(/[,;.]/);
  return idx < 0 ? s.trim() : s.slice(0, idx).trim();
}

function titleFromId(id) {
  if (!id) return 'Untitled';
  return id.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

export { buildCaption as _buildCaption, buildPromptTemplate as _buildPromptTemplate, buildContext as _buildContext };
