/**
 * Relic emitter (D5: relic.schema.json).
 *
 * Caption: trigger + " style, a " + relic_type + ", " + silhouette_cue + ", " + materials.join(" and ")
 * Prompt positive: silhouette_cue + signature_markings + materials + scale + wear_level + attachment_to_wearer + palette + signature_features
 * Prompt negative: forbidden_inputs
 * Context sections: Identity, Role & Significance, Powers, Ownership Chain, Associations, Mechanical (optional), Forbidden, Sources
 */

import { contextFrontmatter, renderKeyValueSection, renderSection } from './base.js';

const SCHEMA_KIND = 'relic';

export function emitRelic(entry, ctx) {
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

  const head = fm.relic_type ? `a ${fm.relic_type}` : 'a relic';
  segments.push(head);

  if (v.silhouette_cue) segments.push(v.silhouette_cue);

  if (Array.isArray(fm.materials) && fm.materials.length) {
    segments.push(fm.materials.join(' and '));
  }

  return segments.join(', ');
}

function buildPromptTemplate(fm) {
  const v = fm.visual || {};
  const lines = [];
  lines.push(`{# auto-generated canon-build prompt template — do not hand-edit #}`);
  lines.push(`{{ trigger }} style, a ${fm.relic_type || 'relic'}, ${v.silhouette_cue || ''}.`);

  if (Array.isArray(v.signature_markings) && v.signature_markings.length) {
    lines.push(`{# markings #} ${v.signature_markings.join(', ')}`);
  }
  if (Array.isArray(fm.materials) && fm.materials.length) {
    lines.push(`{# materials #} ${fm.materials.join(', ')}`);
  }
  if (v.scale) lines.push(`{# scale #} ${v.scale}`);
  if (v.wear_level) lines.push(`{# wear #} ${v.wear_level}`);
  if (v.attachment_to_wearer) {
    lines.push(`{# attachment #} {% if character_trigger %}${v.attachment_to_wearer}{% endif %}`);
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
    ['relic_type', fm.relic_type],
    ['origin', fm.origin],
    ['current_status', fm.current_status],
  ]));

  out.push(renderKeyValueSection('Role & Significance', [
    ['role', n.role],
    ['mythic_significance', n.mythic_significance],
  ]));

  if (Array.isArray(fm.powers) && fm.powers.length) {
    const bullets = fm.powers.map((p) => {
      const conditions = p.conditions ? ` — ${p.conditions}` : '';
      const limits = p.limits ? ` — limits: ${p.limits}` : '';
      return `${p.effect}${conditions}${limits}`;
    });
    out.push(renderSection('Powers', bullets));
  }

  if (Array.isArray(fm.ownership_chain) && fm.ownership_chain.length) {
    const bullets = fm.ownership_chain.map((o) => {
      const from = o.acquired_from ? ` from ${o.acquired_from}` : '';
      const note = o.note ? ` (${o.note})` : '';
      return `${o.era}: ${o.owner_id} via ${o.acquired_by}${from}${note}`;
    });
    out.push(renderSection('Ownership Chain', bullets));
  }

  out.push(renderKeyValueSection('Associations', [
    ['associated_myths', n.associated_myths],
    ['counterparts', n.counterparts],
  ]));

  if (m && typeof m === 'object' && Object.values(m).some((v) => v != null)) {
    out.push(renderKeyValueSection('Mechanical', [
      ['unlock_trigger', m.unlock_trigger],
      ['grants', m.grants],
      ['drawbacks', m.drawbacks],
      ['slot', m.slot],
    ]));
  }

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
