/**
 * EXTERNAL_VERIFIER support (Kambhampati arXiv:2402.01817; Huang / DeepMind
 * arXiv:2310.01798): a judgment records WHO judged it (`judged_by_model`) and
 * WHAT produced the artifact (`generator_model`), and we WARN when they are the
 * same — the self-verification failure mode a verifier must never fall into.
 *
 * Today the two judges are `human` (curate) and a rule-based engine
 * (critique-engine) — both a different artifact class from the image generator,
 * so the warning does not fire in practice and the standard's spirit is already
 * met. Recording the fields + wiring the warning installs the muscle: the moment
 * an LLM critique mode enters the loop sharing the generator's base, the WARN
 * fires, and the standard's remediation flips it from a warning to a hard gate.
 */

import { warn } from './log.js';

/** The rule-based critique engine's judge id. Bump vN when the rule set changes. */
export const RULE_BASED_JUDGE = 'rule-based:sdlab-critique-v1';

/** The human curator's judge id (curate.js reviewer is "human:mike"). */
export const HUMAN_JUDGE = 'human';

const MODEL_EXT_RE = /\.(safetensors|ckpt|pt|pth|bin|gguf)$/i;

/**
 * Derive a stable generator model id from a record `provenance` (or any object
 * carrying {base, unet|checkpoint}): `<base>:<model-basename-without-ext>`, e.g.
 * "qwen-image:qwen_image_fp8_e4m3fn" or "sdxl:dreamshaperXL". Returns null when
 * neither a base nor a model file is known (legacy/hand-migrated records).
 */
export function deriveGeneratorModel(provenance) {
  if (!provenance || typeof provenance !== 'object') return null;
  const base = provenance.base || null;
  const modelFile = provenance.unet || provenance.checkpoint || null;
  const stripped = modelFile ? String(modelFile).replace(MODEL_EXT_RE, '') : null;
  if (base && stripped) return `${base}:${stripped}`;
  return base || stripped || null;
}

/**
 * Derive the generator model id from a run manifest (comfyui-runner shape).
 * Prefers the pinning block's model identity, falling back to the top-level
 * checkpoint. Qwen manifests carry pinning.models.unet; SDXL carry checkpoint.
 */
export function generatorModelFromManifest(manifest) {
  if (!manifest || typeof manifest !== 'object') return null;
  const unet = manifest.pinning?.models?.unet?.name;
  const checkpoint = manifest.checkpoint || manifest.pinning?.models?.checkpoint?.name;
  const base = unet ? 'qwen-image' : (checkpoint ? 'sdxl' : null);
  return deriveGeneratorModel({ base, unet, checkpoint });
}

/**
 * Emit a WARN when the judge and the generator are the same model — the
 * self-verification failure mode. No-op when either is null or they differ.
 * Returns true when the warning fired, so callers/tests can assert on it without
 * capturing stderr.
 */
export function warnIfSelfVerification(judgedByModel, generatorModel, context = '') {
  if (!judgedByModel || !generatorModel) return false;
  if (judgedByModel !== generatorModel) return false;
  warn(
    `EXTERNAL_VERIFIER: judged_by_model === generator_model ("${judgedByModel}")${context ? ` for ${context}` : ''} — ` +
    'a model must not verify its own output. Use a different-family judge (ai-eyes-mcp or a cross-family LLM).',
  );
  return true;
}
