/**
 * Location emitter (D5: location.schema.json).
 *
 * Caption: trigger + " style, a " + location_type + " in " + region + ", " + silhouette_cue + ", " + lighting_mood
 * Prompt positive: silhouette_cue + signature_props + lighting_mood + scale_logic + material_language + era_markers + flora_fauna + palette + signature_features
 * Prompt negative: forbidden_inputs (era-anachronism-heavy)
 * Context sections: Identity, Role & Significance, Mythic Events, Associations, Ritual, Forbidden, Sources
 */

import { contextFrontmatter, renderKeyValueSection, renderSection } from './base.js';

const SCHEMA_KIND = 'location';

export function emitLocation(entry, ctx) {
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

  const typeClause = [];
  if (fm.location_type) typeClause.push(`a ${fm.location_type}`);
  if (fm.region) typeClause.push(`in ${fm.region}`);
  if (typeClause.length) segments.push(typeClause.join(' '));

  if (v.silhouette_cue) segments.push(v.silhouette_cue);
  if (v.lighting_mood) segments.push(v.lighting_mood);

  return segments.join(', ');
}

function buildPromptTemplate(fm) {
  const v = fm.visual || {};
  const lines = [];
  lines.push(`{# auto-generated canon-build prompt template — do not hand-edit #}`);
  lines.push(`{{ trigger }} style, a ${fm.location_type || 'place'} in ${fm.region || 'greek lands'}, ${v.silhouette_cue || ''}.`);

  if (Array.isArray(v.signature_props) && v.signature_props.length) {
    lines.push(`{# props #} ${v.signature_props.join(', ')}`);
  }
  if (v.lighting_mood) lines.push(`{# light #} ${v.lighting_mood}`);
  if (v.scale_logic) lines.push(`{# scale #} ${v.scale_logic}`);
  if (v.material_language) lines.push(`{# materials #} ${v.material_language}`);
  if (Array.isArray(v.era_markers) && v.era_markers.length) {
    lines.push(`{# era markers #} ${v.era_markers.join(', ')}`);
  }
  if (Array.isArray(v.flora_fauna) && v.flora_fauna.length) {
    lines.push(`{# flora/fauna #} ${v.flora_fauna.join(', ')}`);
  }
  if (Array.isArray(v.palette) && v.palette.length) {
    lines.push(`{# palette #} ${v.palette.join(' ')}`);
  }
  if (Array.isArray(fm.signature_features) && fm.signature_features.length) {
    lines.push(`{# signature #} ${fm.signature_features.join(', ')}`);
  }

  lines.push('---');
  lines.push(`{{ negative_base }}`);
  return lines.join('\n') + '\n';
}

function buildContext(entry, ctx) {
  const fm = entry.frontmatter;
  const n = fm.narrative || {};
  const out = [];

  out.push(contextFrontmatter({
    entityId: fm.id,
    schemaKind: SCHEMA_KIND,
    generatedFrom: ctx.generatedFrom,
    entryHash: ctx.entryHash,
  }));
  out.push(`# ${titleFromId(fm.id)}\n`);

  out.push(renderKeyValueSection('Identity', [
    ['location_type', fm.location_type],
    ['region', fm.region],
    ['era_logic', fm.era_logic],
  ]));

  out.push(renderKeyValueSection('Role & Significance', [
    ['role', n.role],
    ['cultural_weight', n.cultural_weight],
    ['mortal_access', n.mortal_access],
  ]));

  if (Array.isArray(fm.mythic_events) && fm.mythic_events.length) {
    const bullets = fm.mythic_events.map((ev) => {
      const participants = Array.isArray(ev.participants) && ev.participants.length
        ? `, participants: ${ev.participants.join(', ')}`
        : '';
      return `${ev.event} (${ev.era}, ${ev.source}${participants})`;
    });
    out.push(renderSection('Mythic Events', bullets));
  }

  out.push(renderKeyValueSection('Associations', [
    ['associated_deities', fm.associated_deities],
    ['associated_monsters', fm.associated_monsters],
  ]));

  out.push(renderSection('Ritual', n.forbidden_acts || null));

  out.push(renderSection('Forbidden', fm.forbidden_inputs || null));
  out.push(renderSection('Sources', fm.sources || null));

  if (entry.body && entry.body.trim()) {
    out.push(`## Notes\n${entry.body.trim()}\n`);
  }

  return out.join('');
}

function titleFromId(id) {
  if (!id) return 'Untitled';
  return id.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

export { buildCaption as _buildCaption, buildPromptTemplate as _buildPromptTemplate, buildContext as _buildContext };
