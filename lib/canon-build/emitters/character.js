/**
 * Character emitter (D5: character.schema.json).
 *
 * Caption: trigger + " style, a " + kind + " wearing " + visual.attire + ", " + visual.silhouette_cue + ". " + visual.build + " build, " + visual.hair
 * Prompt positive: visual.* (silhouette_cue, signature_prop, distinguishing_marks, build, hair, eyes, age_band, attire, palette) + signature_features + pose hint from narrative.voice
 * Prompt negative: forbidden_inputs + divine-radiance suppression when kind="mortal"
 * Context sections: Identity, Role & Voice, Relationships, Canonical Events, Mechanical (optional), Forbidden, Sources
 */

import { contextFrontmatter, renderKeyValueSection, renderSection } from './base.js';

const SCHEMA_KIND = 'character';

export function emitCharacter(entry, ctx) {
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

  const kind = fm.kind || fm.role_class || 'figure';
  const attire = v.attire || '';
  const silhouette = v.silhouette_cue || '';
  const subjectClause = attire ? `a ${kind} wearing ${attire}` : `a ${kind}`;
  segments.push(silhouette ? `${subjectClause}, ${silhouette}` : subjectClause);

  const buildAndHair = [];
  if (v.build) buildAndHair.push(`${v.build} build`);
  if (v.hair) buildAndHair.push(v.hair);
  if (buildAndHair.length) segments.push(buildAndHair.join(', '));

  return segments.join(', ');
}

function buildPromptTemplate(fm) {
  const v = fm.visual || {};
  const lines = [];
  lines.push(`{# auto-generated canon-build prompt template — do not hand-edit #}`);
  lines.push(`{{ trigger }} style{% if character_trigger %}, {{ character_trigger }}{% endif %}, a ${fm.kind || fm.role_class || 'figure'}, ${v.silhouette_cue || ''}.`);

  const identity = [];
  if (v.signature_prop) identity.push(`signature prop: ${v.signature_prop}`);
  if (Array.isArray(v.distinguishing_marks) && v.distinguishing_marks.length) {
    identity.push(`marks: ${v.distinguishing_marks.join(', ')}`);
  }
  if (identity.length) lines.push(`{# identity #} ${identity.join('; ')}`);

  const body = [];
  if (v.build) body.push(`${v.build} build`);
  if (v.hair) body.push(v.hair);
  if (v.eyes) body.push(`${v.eyes} eyes`);
  if (v.age_band) body.push(`${v.age_band} age`);
  else if (v.age_description) body.push(v.age_description);
  if (body.length) lines.push(`{# body #} ${body.join(', ')}`);

  if (v.attire) lines.push(`{# attire #} ${v.attire}`);
  if (Array.isArray(v.palette) && v.palette.length) {
    lines.push(`{# palette #} ${v.palette.join(' ')}`);
  }
  if (Array.isArray(fm.signature_features) && fm.signature_features.length) {
    lines.push(`{# signature #} ${fm.signature_features.join(', ')}`);
  }
  if (v.posture_default) {
    lines.push(`{# pose #} ${v.posture_default}`);
  }

  lines.push('---');
  lines.push(`{{ negative_base }}`);
  if (fm.kind === 'mortal') {
    lines.push(', divine radiance, aureole, supernatural glow');
  }
  if (fm.canon_refs && !fm.sources) {
    // Canon-internal attestation (Star Freight path): callers still expect
    // `{{ negative_base }}` to land on its own line; no extra addition needed.
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
    ['kind', fm.kind],
    ['role_class', fm.role_class],
    ['species', fm.species],
    ['faction_primary', fm.faction_primary],
    ['faction_cover', fm.faction_cover],
    ['tech_literacy', fm.tech_literacy],
    ['combat_training', fm.combat_training],
    ['mortal_status', fm.mortal_status],
    ['age_band', fm.visual?.age_band],
    ['age_description', fm.visual?.age_description],
  ]));

  out.push(renderKeyValueSection('Role & Voice', [
    ['role', n.role],
    ['voice', n.voice],
    ['motivation', n.motivation],
    ['speech_register', n.speech_register],
    ['vocabulary_forbidden', n.vocabulary_forbidden],
  ]));

  if (fm.turncoat_arc && fm.turncoat_arc.status && fm.turncoat_arc.status !== 'none') {
    out.push(renderKeyValueSection('Turncoat arc', [
      ['status', fm.turncoat_arc.status],
      ['reveal_trigger', fm.turncoat_arc.reveal_trigger],
      ['defection_threshold', fm.turncoat_arc.defection_threshold],
      ['handler_faction', fm.turncoat_arc.handler_faction],
      ['canon_true_voice', fm.turncoat_arc.canon_true_voice],
      ['seeds', fm.turncoat_arc.seeds],
    ]));
  }

  if (Array.isArray(n.relationships) && n.relationships.length) {
    const relBullets = n.relationships.map((r) => {
      const note = r.note ? ` — ${r.note}` : '';
      return `${r.edge_type} ${r.target_id}${note}`;
    });
    out.push(renderSection('Relationships', relBullets));
  }

  out.push(renderSection('Canonical Events', n.arc_beats || null));

  if (m && typeof m === 'object' && Object.values(m).some((v) => v != null)) {
    out.push(renderKeyValueSection('Mechanical', [
      ['combat_role', m.combat_role],
      ['signature_abilities', m.signature_abilities],
      ['traits', m.traits],
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
