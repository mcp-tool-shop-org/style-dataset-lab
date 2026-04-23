/**
 * Caption building — shared between training adapters.
 *
 * Research-backed strategies for producing LoRA-training captions from
 * approved canon records. Previously, both adapters carried near-duplicate
 * buildCaption stubs that spliced `provenance.prompt` into the caption —
 * a prompt-bleed antipattern that bakes generation-time style vocabulary
 * (e.g. "oil painting, semi-realistic painterly, muted dusty palette...")
 * back into the trigger token and corrupts downstream training.
 *
 * This module centralizes caption construction and adds a
 * `structured-metadata` strategy that uses only clean, canon-anchored
 * fields (judgment explanation, faction, lane, group) and never the raw
 * generation prompt.
 *
 * Strategies (from `profile.caption_strategy`):
 *   - 'legacy' (default when unset): preserves prior behavior exactly —
 *      trigger, group, lane, provenance.prompt[0..200]. Kept so existing
 *      training manifests reproduce bit-identical.
 *   - 'structured-metadata': trigger, faction, group, lane,
 *      judgment.explanation. No generation prompt. Research-backed for
 *      style LoRAs where the trigger should absorb the style and
 *      captions describe scene content, not style vocabulary.
 *
 * References (in research docs accompanying this change):
 *   - Apatero LoRA Best Practices 2025 — trigger-first tag ordering
 *   - alvdansen HF blog — caption format variety
 *   - Ye et al. 2025 (arXiv 2510.09475) — multi-token DreamBooth+LoRA
 *   - Pelayo Arbues — Flux caption template (NL + scene variations)
 */

/**
 * Derive the style trigger token from a profile id.
 * `character-style-lora` → `character_style_lora`
 *
 * @param {{profile_id?: string}} profile
 * @returns {string|null}
 */
export function deriveStyleTrigger(profile) {
  if (!profile?.profile_id) return null;
  return profile.profile_id.replace(/-/g, '_');
}

/**
 * Build a training caption from a record + context + profile.
 *
 * @param {Object} record    — approved canon record (see schema in projects/**)
 * @param {string|null} lane — partition lane (costume, equipment, ...)
 * @param {string|null} group — partition group (faction, region, ...)
 * @param {Object} profile   — loaded training profile JSON
 * @returns {string}
 */
export function buildCaption(record, lane, group, profile) {
  const strategy = profile?.caption_strategy || 'legacy';

  switch (strategy) {
    case 'structured-metadata':
      return buildStructuredMetadataCaption(record, lane, group, profile);

    case 'legacy':
    default:
      return buildLegacyCaption(record, lane, group, profile);
  }
}

/**
 * Legacy caption — preserved verbatim from pre-refactor adapters so existing
 * training manifests remain reproducible.
 *
 * Shape: `<trigger>, <group>, <lane>, <provenance.prompt sliced to 200>`
 *
 * WARNING: This strategy splices the raw generation prompt into the caption,
 * which causes prompt bleed during training. Kept for backward compatibility
 * only. New profiles should use `structured-metadata`.
 */
function buildLegacyCaption(record, lane, group, profile) {
  const parts = [];

  if (profile?.prompt_strategy === 'trigger-word' && profile?.profile_id) {
    parts.push(profile.profile_id.replace(/-/g, '_'));
  }

  if (group) parts.push(group);
  if (lane) parts.push(lane);

  const prompt = record?.provenance?.prompt;
  if (prompt) {
    parts.push(prompt.slice(0, 200));
  } else if (record?.id) {
    parts.push(record.id.replace(/_/g, ' '));
  }

  return parts.join(', ');
}

/**
 * Structured-metadata caption.
 *
 * Builds captions from clean, canon-anchored fields only. Never touches
 * `provenance.prompt` (which contains style vocabulary that causes bleed).
 *
 * Order follows the research rule that earlier tokens are weighted higher:
 *   1. Style trigger (profile-derived)    — absorbs the house style
 *   2. Faction / group (canon-derived)    — primary discriminator
 *   3. Lane                                — category context
 *   4. Scene description from judgment    — short human scene notes
 *
 * Dedupes faction vs group when they're the same value. Trims empty
 * segments. No segment exceeds a reasonable bound individually; full
 * caption is expected to stay well under the 75-token practical cap.
 */
function buildStructuredMetadataCaption(record, lane, group, profile) {
  const parts = [];

  const trigger = deriveStyleTrigger(profile);
  if (trigger) parts.push(trigger);

  const faction = record?.canon?.faction;
  if (faction) parts.push(`${faction} faction`);

  if (group && group !== faction) parts.push(group);

  if (lane) parts.push(lane);

  const scene = record?.judgment?.explanation;
  if (scene) parts.push(scene.trim());

  return parts.join(', ');
}
