/**
 * Species emitter (Star Freight D6).
 *
 * Species-level forbidden_morphology_drift is the schema-level home for the
 * "alien needs `human` in negative" rule (feedback_alien_negative_prompt.md).
 * Every member character inherits it — species is the entry, not a per-character
 * redundancy.
 *
 * Caption: trigger + " style, a " + biology_class + " species, " +
 *          body_plan + ", " + signature_appendages
 * Prompt positive: body_plan + anatomy_descriptors +
 *                  involuntary_expression_channel + palette + signature_features
 * Prompt negative: forbidden_inputs + forbidden_morphology_drift (the species-
 *                  level alien guard)
 */

import { contextFrontmatter, renderKeyValueSection, renderSection } from './base.js';

const SCHEMA_KIND = 'species';

export function emitSpecies(entry, ctx) {
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

  const bio = fm.biology_class || 'species';
  segments.push(`a ${bio} species`);

  if (v.body_plan) segments.push(v.body_plan);
  const anatomy = v.anatomy_descriptors || {};
  if (anatomy.signature_appendages) segments.push(anatomy.signature_appendages);

  return segments.join(', ');
}

function buildPromptTemplate(fm) {
  const v = fm.visual || {};
  const anatomy = v.anatomy_descriptors || {};
  const lines = [];
  lines.push(`{# auto-generated canon-build prompt template — do not hand-edit #}`);
  lines.push(`{{ trigger }} style, a ${fm.biology_class || 'species'}, ${v.body_plan || ''}.`);

  if (typeof anatomy.arm_count === 'number') {
    lines.push(`{# arms #} ${anatomy.arm_count} arms`);
  }
  if (anatomy.locomotion) lines.push(`{# locomotion #} ${anatomy.locomotion}`);
  if (anatomy.sensory_organs) lines.push(`{# senses #} ${anatomy.sensory_organs}`);
  if (anatomy.skin_or_integument) lines.push(`{# integument #} ${anatomy.skin_or_integument}`);
  if (anatomy.signature_appendages) lines.push(`{# appendages #} ${anatomy.signature_appendages}`);
  if (v.involuntary_expression_channel) {
    lines.push(`{# expression #} ${v.involuntary_expression_channel}`);
  }
  if (Array.isArray(v.palette) && v.palette.length) {
    lines.push(`{# palette #} ${v.palette.join(' ')}`);
  }
  if (Array.isArray(fm.signature_features) && fm.signature_features.length) {
    lines.push(`{# signature #} ${fm.signature_features.join(', ')}`);
  }

  lines.push('---');
  lines.push(`{{ negative_base }}`);
  if (Array.isArray(v.forbidden_morphology_drift) && v.forbidden_morphology_drift.length) {
    lines.push(`, ${v.forbidden_morphology_drift.join(', ')}`);
  }
  return lines.join('\n') + '\n';
}

function buildContext(entry, ctx) {
  const fm = entry.frontmatter;
  const n = fm.narrative || {};
  const v = fm.visual || {};
  const comm = fm.communication_modality || {};
  const culture = fm.cultural_stance || {};
  const rel = fm.relation_to_humans || {};
  const out = [];

  out.push(contextFrontmatter({
    entityId: fm.id,
    schemaKind: SCHEMA_KIND,
    generatedFrom: ctx.generatedFrom,
    entryHash: ctx.entryHash,
  }));
  out.push(`# ${titleFromId(fm.id)}\n`);

  out.push(renderKeyValueSection('Identity', [
    ['biology_class', fm.biology_class],
    ['scaffold', fm.scaffold],
  ]));

  out.push(renderKeyValueSection('Communication', [
    ['primary_language', comm.primary_language],
    ['nonverbal_channel', comm.nonverbal_channel],
    ['can_lie', comm.can_lie],
    ['signal_incompatibility_with_humans', comm.signal_incompatibility_with_humans],
  ]));

  out.push(renderKeyValueSection('Cultural stance', [
    ['time_horizon', culture.time_horizon],
    ['core_value', culture.core_value],
    ['death_rite', culture.death_rite],
    ['trade_idiom', culture.trade_idiom],
    ['greeting_protocol', culture.greeting_protocol],
  ]));

  const anatomy = v.anatomy_descriptors || {};
  out.push(renderKeyValueSection('Visual', [
    ['body_plan', v.body_plan],
    ['locomotion', anatomy.locomotion],
    ['arm_count', anatomy.arm_count],
    ['sensory_organs', anatomy.sensory_organs],
    ['skin_or_integument', anatomy.skin_or_integument],
    ['signature_appendages', anatomy.signature_appendages],
    ['palette', v.palette],
    ['involuntary_expression_channel', v.involuntary_expression_channel],
    ['sexual_dimorphism', v.sexual_dimorphism],
  ]));

  out.push(renderSection('Forbidden morphology drift', v.forbidden_morphology_drift || null));

  out.push(renderKeyValueSection('Relation to humans', [
    ['baseline_stance', rel.baseline_stance],
    ['narrative_framing', rel.narrative_framing],
    ['gameplay_integration', rel.gameplay_integration],
  ]));

  out.push(renderKeyValueSection('Narrative', [
    ['role', n.role],
  ]));
  out.push(renderSection('Canonical practices', n.canonical_practices || null));

  if (Array.isArray(n.relationships) && n.relationships.length) {
    const relBullets = n.relationships.map((r) => {
      const note = r.note ? ` — ${r.note}` : '';
      return `${r.edge_type} ${r.target_id}${note}`;
    });
    out.push(renderSection('Relationships', relBullets));
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
