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
 * Strategies (from `profile.caption_strategy`):
 *   - 'legacy' (default when unset): preserves prior behavior exactly —
 *      trigger, group, lane, provenance.prompt[0..200]. Kept so existing
 *      training manifests reproduce bit-identical.
 *   - 'structured-metadata': trigger, faction, group, lane,
 *      judgment.explanation. No generation prompt. Research-backed for
 *      SDXL-style LoRAs where the trigger should absorb the style and
 *      captions describe scene content as comma-separated tags.
 *   - 'flux-natural-language': trigger + subject noun phrase + scene as
 *      a natural-language description. Recommended when
 *      `profile.target_family === 'flux'` because Flux's T5 text encoder
 *      holds identity across natural-language prompts much better than
 *      SDXL's CLIP does on comma-separated tags. See research notes.
 *
 * References:
 *   - Apatero LoRA Best Practices 2025 — trigger-first tag ordering
 *   - alvdansen HF blog — caption format variety
 *   - Ye et al. 2025 (arXiv 2510.09475) — multi-token DreamBooth+LoRA
 *   - Pelayo Arbues — Flux caption template (NL + scene variations)
 *   - Civitai Flux Character Caption Diary (article 6868) — natural
 *     language outperforms booru-style tags on Flux
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

    case 'flux-natural-language':
      return buildFluxNaturalLanguageCaption(record, lane, group, profile);

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

/**
 * Flux natural-language caption.
 *
 * Flux's T5 text encoder holds identity across long, natural-language
 * prompts where SDXL's CLIP loses identity on comma-separated tag lists.
 * For Flux LoRAs the recommended caption shape is a full sentence:
 * trigger-style descriptor, then a subject noun phrase, then a short
 * scene sentence.
 *
 * Template (from the research): `[Trigger] style, a [Subject], [Scene].`
 *
 * Unlike structured-metadata, this strategy is prose-shaped — sentences
 * with articles ("a", "the") rather than bare comma-joined tags. But it
 * still uses only clean canon fields (faction, lane, judgment.explanation).
 * Never touches `provenance.prompt`.
 *
 * Example (anchor_03_officer_v3):
 *   "character_style_lora style, a compact faction costume, Steel-blue
 *    uniform, high collar, ship corridor. Clean and institutional."
 *
 * Richer captions (hair / eyes / clothing / pose breakouts) require
 * structured visual fields on the canon record that don't exist yet.
 * This strategy is the floor — on-contract Flux captions from the fields
 * we have. Expand the canon schema first, then enrich this strategy.
 */
function buildFluxNaturalLanguageCaption(record, lane, group, profile) {
  const segments = [];

  const trigger = deriveStyleTrigger(profile);
  if (trigger) segments.push(`${trigger} style`);

  const faction = record?.canon?.faction;
  const subjectParts = [];
  if (faction) subjectParts.push(`${faction} faction`);
  if (lane) {
    subjectParts.push(lane);
  } else if (group && group !== faction) {
    subjectParts.push(group);
  }

  if (subjectParts.length > 0) {
    segments.push(`a ${subjectParts.join(' ')}`);
  }

  const scene = record?.judgment?.explanation;
  if (scene) segments.push(scene.trim());

  return segments.join(', ');
}
