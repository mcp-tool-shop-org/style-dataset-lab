/**
 * Training adapter registry.
 *
 * Single source of truth for training-package adapters. Each adapter
 * lives in `lib/adapters/<id>.js` and exports `buildPackage(opts)`.
 *
 * To add a new adapter (e.g. `kohya-lora`, `onedtrainer`):
 *   1. Add `lib/adapters/<id>.js` exporting `buildPackage`.
 *   2. Add an entry to ADAPTER_REGISTRY below with a one-line description.
 *
 * Why explicit registration: the available adapter list shows up in error
 * messages, training-profile validation, and (eventually) CLI completion.
 * A static map keeps those views consistent and makes new adapters a
 * one-line surface change rather than a directory-listing side effect.
 */

import { inputError } from './errors.js';

export const ADAPTER_REGISTRY = Object.freeze({
  'generic-image-caption': {
    id: 'generic-image-caption',
    description: 'Image folders + caption JSONL — broadest trainer compatibility',
    module: './adapters/generic-image-caption.js',
  },
  'diffusers-lora': {
    id: 'diffusers-lora',
    description: 'Diffusers fine-tuning layout: image + caption .txt sidecars + per-partition JSONL',
    module: './adapters/diffusers-lora.js',
  },
});

/**
 * Names of all registered adapters.
 * @returns {string[]}
 */
export function listAdapters() {
  return Object.keys(ADAPTER_REGISTRY);
}

/**
 * Whether `id` names a registered adapter.
 * @param {string} id
 * @returns {boolean}
 */
export function isRegisteredAdapter(id) {
  return Object.prototype.hasOwnProperty.call(ADAPTER_REGISTRY, id);
}

/**
 * Resolve and dynamically import an adapter module.
 *
 * Throws `ADAPTER_NOT_REGISTERED` (input error, exit 1) for unknown ids
 * — distinct from `MODULE_LOAD_FAILED` (runtime, exit 2) for the rare
 * case where the file vanished after registration.
 *
 * @param {string} id
 * @returns {Promise<{ buildPackage: Function }>}
 */
export async function loadAdapter(id) {
  if (!isRegisteredAdapter(id)) {
    throw inputError(
      'ADAPTER_NOT_REGISTERED',
      `Adapter "${id}" is not registered. Available: ${listAdapters().join(', ')}`,
      'Pick one of the registered adapters or add a new one to lib/training-adapters.js.'
    );
  }
  const entry = ADAPTER_REGISTRY[id];
  try {
    return await import(entry.module);
  } catch (err) {
    // The registry says it should exist but import failed — surface the
    // underlying error so it doesn't get masked as a typo.
    throw inputError(
      'ADAPTER_MODULE_LOAD_FAILED',
      `Adapter "${id}" is registered but its module failed to load: ${err.message}`,
      `Check that ${entry.module} exists and exports buildPackage().`
    );
  }
}
