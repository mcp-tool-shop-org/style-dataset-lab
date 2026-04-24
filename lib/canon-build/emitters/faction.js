/**
 * Faction emitter (Star Freight D4).
 *
 * Faction captions + prompts serve the World LoRA's faction-aesthetic signal.
 * The emitter lane for factions is constant "faction-aesthetic" (see
 * canon-build/config.json schema_to_lane).
 *
 * Caption: trigger + " style, " + faction_class + " faction aesthetic, " +
 *          architectural_style + ", " + aesthetic_markers[0..2]
 * Prompt positive: architectural_style + aesthetic_markers + palette +
 *                  uniform_or_attire_description + faction_prop_signatures +
 *                  typography_style + signature_features
 * Prompt negative: forbidden_inputs
 * Context sections: Identity, Visual, Narrative, Stance, Faction edges,
 *                   Mechanical (optional), Forbidden, Sources, Canon refs
 */

import { contextFrontmatter, renderKeyValueSection, renderSection } from './base.js';

const SCHEMA_KIND = 'faction';

export function emitFaction(entry, ctx) {
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

  const cls = fm.faction_class || 'faction';
  segments.push(`${cls} faction aesthetic`);

  if (v.architectural_style) segments.push(v.architectural_style);

  if (Array.isArray(v.aesthetic_markers) && v.aesthetic_markers.length) {
    segments.push(v.aesthetic_markers.slice(0, 2).join(', '));
  }

  return segments.join(', ');
}

function buildPromptTemplate(fm) {
  const v = fm.visual || {};
  const lines = [];
  lines.push(`{# auto-generated canon-build prompt template — do not hand-edit #}`);
  lines.push(`{{ trigger }} style, ${fm.faction_class || 'faction'} faction aesthetic, ${v.architectural_style || ''}.`);

  if (Array.isArray(v.aesthetic_markers) && v.aesthetic_markers.length) {
    lines.push(`{# aesthetic #} ${v.aesthetic_markers.join(', ')}`);
  }
  if (v.uniform_or_attire_description) {
    lines.push(`{# uniform #} ${v.uniform_or_attire_description}`);
  }
  if (v.silhouette_convention) {
    lines.push(`{# silhouette #} ${v.silhouette_convention}`);
  }
  if (v.typography_style) {
    lines.push(`{# typography #} ${v.typography_style}`);
  }
  if (Array.isArray(v.faction_prop_signatures) && v.faction_prop_signatures.length) {
    lines.push(`{# props #} ${v.faction_prop_signatures.join(', ')}`);
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
  const s = fm.stance || {};
  const m = fm.mechanical;
  const v = fm.visual || {};
  const out = [];

  out.push(contextFrontmatter({
    entityId: fm.id,
    schemaKind: SCHEMA_KIND,
    generatedFrom: ctx.generatedFrom,
    entryHash: ctx.entryHash,
  }));
  out.push(`# ${titleFromId(fm.id)}\n`);

  out.push(renderKeyValueSection('Identity', [
    ['faction_class', fm.faction_class],
  ]));

  out.push(renderKeyValueSection('Visual', [
    ['palette', v.palette],
    ['aesthetic_markers', v.aesthetic_markers],
    ['silhouette_convention', v.silhouette_convention],
    ['typography_style', v.typography_style],
    ['uniform_or_attire_description', v.uniform_or_attire_description],
    ['architectural_style', v.architectural_style],
    ['faction_prop_signatures', v.faction_prop_signatures],
  ]));

  out.push(renderKeyValueSection('Narrative', [
    ['voice', n.voice],
    ['values', n.values],
    ['taboos', n.taboos],
    ['speech_register', n.speech_register],
    ['vocabulary_forbidden', n.vocabulary_forbidden],
    ['internal_tensions', n.internal_tensions],
  ]));

  out.push(renderKeyValueSection('Stance', [
    ['toward_player_at_start', s.toward_player_at_start],
    ['toward_player_trajectory', s.toward_player_trajectory],
  ]));

  if (Array.isArray(s.faction_edges) && s.faction_edges.length) {
    const bullets = s.faction_edges.map((r) => {
      const note = r.note ? ` — ${r.note}` : '';
      return `${r.edge_type} ${r.target_id}${note}`;
    });
    out.push(renderSection('Faction edges', bullets));
  }

  if (m && typeof m === 'object' && Object.values(m).some((vv) => vv != null)) {
    out.push(renderKeyValueSection('Mechanical', [
      ['reputation_starting_value', m.reputation_starting_value],
      ['skill_bonuses_for_member', m.skill_bonuses_for_member],
    ]));
    if (Array.isArray(m.standing_deltas_by_action) && m.standing_deltas_by_action.length) {
      const bullets = m.standing_deltas_by_action.map((d) => `${d.action}: ${d.delta >= 0 ? '+' : ''}${d.delta}`);
      out.push(renderSection('Standing deltas', bullets));
    }
  }

  out.push(renderSection('Forbidden', fm.forbidden_inputs || null));
  out.push(renderSection('Sources', fm.sources || null));
  out.push(renderSection('Canon refs', fm.canon_refs || null));

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
