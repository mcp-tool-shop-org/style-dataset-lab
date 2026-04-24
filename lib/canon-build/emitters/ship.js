/**
 * Ship emitter (Star Freight D5).
 *
 * silhouette_cue is the heaviest trainable leverage for ships — the player
 * sees them at multiple scales (nav chart, exterior establishing, dock
 * approach, interior cockpit). The emitter lifts it to the caption and
 * foregrounds it in the prompt template.
 *
 * Caption: trigger + " style, a " + ship_class + " ship, " +
 *          silhouette_cue + ", " + material_dominant
 * Prompt positive: silhouette_cue + tonnage_class + hull_repair_history +
 *                  symmetry + material_dominant + hull_markings +
 *                  scale_cue_object + cockpit_style + engine_signature +
 *                  palette + signature_features
 * Prompt negative: forbidden_inputs
 */

import { contextFrontmatter, renderKeyValueSection, renderSection } from './base.js';

const SCHEMA_KIND = 'ship';

export function emitShip(entry, ctx) {
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

  const cls = fm.ship_class || 'ship';
  segments.push(`a ${cls} ship`);

  if (v.silhouette_cue) segments.push(v.silhouette_cue);
  if (v.material_dominant) segments.push(v.material_dominant);

  return segments.join(', ');
}

function buildPromptTemplate(fm) {
  const v = fm.visual || {};
  const lines = [];
  lines.push(`{# auto-generated canon-build prompt template — do not hand-edit #}`);
  lines.push(`{{ trigger }} style, a ${fm.ship_class || 'ship'}, ${v.silhouette_cue || ''}.`);

  if (fm.tonnage_class) lines.push(`{# tonnage #} ${fm.tonnage_class}`);
  if (v.hull_repair_history) lines.push(`{# hull #} ${v.hull_repair_history}`);
  if (v.symmetry) lines.push(`{# symmetry #} ${v.symmetry}`);
  if (v.material_dominant) lines.push(`{# material #} ${v.material_dominant}`);
  if (Array.isArray(v.hull_markings) && v.hull_markings.length) {
    lines.push(`{# markings #} ${v.hull_markings.join(', ')}`);
  }
  if (v.scale_cue_object) lines.push(`{# scale #} ${v.scale_cue_object}`);
  if (v.cockpit_style) lines.push(`{# cockpit #} ${v.cockpit_style}`);
  if (v.engine_signature) lines.push(`{# engine #} ${v.engine_signature}`);
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
    ['ship_class', fm.ship_class],
    ['tonnage_class', fm.tonnage_class],
    ['faction_of_origin', fm.faction_of_origin],
    ['current_operator', fm.current_operator],
  ]));

  out.push(renderKeyValueSection('Visual', [
    ['silhouette_cue', v.silhouette_cue],
    ['palette', v.palette],
    ['hull_markings', v.hull_markings],
    ['hull_repair_history', v.hull_repair_history],
    ['symmetry', v.symmetry],
    ['material_dominant', v.material_dominant],
    ['scale_cue_object', v.scale_cue_object],
    ['interior_architecture', v.interior_architecture],
    ['cockpit_style', v.cockpit_style],
    ['engine_signature', v.engine_signature],
  ]));

  out.push(renderKeyValueSection('Narrative', [
    ['role', n.role],
    ['current_status', n.current_status],
    ['trade_capacity', n.trade_capacity],
    ['named_crew', n.named_crew],
    ['named_passengers', n.named_passengers],
  ]));

  out.push(renderSection('History beats', n.history_beats || null));

  if (Array.isArray(n.relationships) && n.relationships.length) {
    const relBullets = n.relationships.map((r) => {
      const note = r.note ? ` — ${r.note}` : '';
      return `${r.edge_type} ${r.target_id}${note}`;
    });
    out.push(renderSection('Relationships', relBullets));
  }

  if (m && typeof m === 'object' && Object.values(m).some((vv) => vv != null)) {
    out.push(renderKeyValueSection('Mechanical', [
      ['hull_integrity_starting', m.hull_integrity_starting],
      ['fuel_capacity_starting', m.fuel_capacity_starting],
      ['cargo_slots', m.cargo_slots],
      ['modification_slots', m.modification_slots],
      ['crew_capacity', m.crew_capacity],
      ['combat_capability', m.combat_capability],
    ]));
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
