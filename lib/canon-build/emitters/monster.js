/**
 * Monster emitter (D5: monster.schema.json).
 *
 * Caption: trigger + " style, a " + species_tag + " creature, " + signature_features[0..2]
 * Prompt positive: visual cue + anatomy + lineage hint + scale; human_element suppressed unless species_tag="hybrid"
 * Prompt negative: forbidden_inputs + synthetic human-guard when human_element is null
 * Context sections: Identity, Anatomy, Combat intent, Forbidden, Sources
 */

import { contextFrontmatter, renderKeyValueSection, renderSection, renderNegativeBase } from './base.js';

const SCHEMA_KIND = 'monster';

export function emitMonster(entry, ctx) {
  const fm = entry.frontmatter;
  return {
    schemaKind: SCHEMA_KIND,
    caption: buildCaption(fm, ctx),
    prompt: buildPromptTemplate(fm),
    context: buildContext(entry, ctx),
  };
}

function buildCaption(fm, ctx) {
  const segments = [];
  if (ctx.trigger) segments.push(`${ctx.trigger} style`);

  const species = fm.species_tag || 'creature';
  segments.push(`a ${species} creature`);

  const features = Array.isArray(fm.signature_features) ? fm.signature_features.slice(0, 2) : [];
  if (features.length) {
    segments.push(features.join(', '));
  }

  const notable = fm.anatomy_descriptor?.notable;
  if (Array.isArray(notable) && notable.length) {
    segments.push(notable[0]);
  }

  return segments.join(', ');
}

function buildPromptTemplate(fm) {
  const lines = [];
  lines.push(`{# auto-generated canon-build prompt template — do not hand-edit #}`);
  lines.push(`{{ trigger }} style, a ${fm.species_tag || 'creature'}, ${formatFeatures(fm.signature_features)}.`);

  const anatomy = formatAnatomy(fm.anatomy_descriptor);
  if (anatomy) lines.push(anatomy);

  if (fm.lineage_reference && fm.lineage_reference !== 'none') {
    lines.push(`{# lineage #} ${fm.lineage_reference} descent`);
  }
  if (fm.scale_indicator) {
    lines.push(`{# scale #} ${fm.scale_indicator}`);
  }

  // Human-element handling — suppression is a hard guard against contamination.
  if (fm.species_tag === 'hybrid' && fm.human_element) {
    lines.push(`{# hybrid override #} human portion: ${fm.human_element.scope}`);
  }

  lines.push('---');
  lines.push(`{{ negative_base }}`);
  if (!fm.human_element) {
    lines.push(', human features, human face, human torso');
  }
  return lines.join('\n') + '\n';
}

function buildContext(entry, ctx) {
  const fm = entry.frontmatter;
  const out = [];
  out.push(contextFrontmatter({
    entityId: fm.id,
    schemaKind: SCHEMA_KIND,
    generatedFrom: ctx.generatedFrom,
    entryHash: ctx.entryHash,
  }));

  out.push(`# ${titleFromId(fm.id)}\n`);

  out.push(renderKeyValueSection('Identity', [
    ['species_tag', fm.species_tag],
    ['lineage_reference', fm.lineage_reference],
    ['lineage_detail', fm.lineage_detail],
    ['scale_indicator', fm.scale_indicator],
  ]));

  out.push(renderSection('Anatomy', fm.anatomy_descriptor || null));

  if (fm.human_element) {
    out.push(renderSection('Human element', fm.human_element));
  }

  out.push(renderSection('Combat intent', fm.signature_features || null));
  out.push(renderSection('Forbidden', fm.forbidden_inputs || null));
  out.push(renderSection('Sources', fm.sources || null));

  // Canon prose body feeds context exclusively.
  if (entry.body && entry.body.trim()) {
    out.push(`## Notes\n${entry.body.trim()}\n`);
  }

  return out.join('');
}

function formatFeatures(features) {
  if (!Array.isArray(features) || features.length === 0) return 'creature silhouette';
  return features.join(', ');
}

function formatAnatomy(desc) {
  if (!desc || typeof desc !== 'object') return '';
  const parts = [];
  if (typeof desc.heads === 'number') parts.push(`${desc.heads} head${desc.heads === 1 ? '' : 's'}`);
  if (typeof desc.limbs === 'number') parts.push(`${desc.limbs} limb${desc.limbs === 1 ? '' : 's'}`);
  if (typeof desc.wings === 'number' && desc.wings > 0) parts.push(`${desc.wings} wing${desc.wings === 1 ? '' : 's'}`);
  if (typeof desc.tails === 'number' && desc.tails > 0) parts.push(`${desc.tails} tail${desc.tails === 1 ? '' : 's'}`);
  if (Array.isArray(desc.notable) && desc.notable.length) parts.push(...desc.notable);
  if (!parts.length) return '';
  return `{# anatomy #} ${parts.join(', ')}`;
}

function titleFromId(id) {
  if (!id) return 'Untitled';
  return id.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

export { buildCaption as _buildCaption, buildPromptTemplate as _buildPromptTemplate, buildContext as _buildContext };
