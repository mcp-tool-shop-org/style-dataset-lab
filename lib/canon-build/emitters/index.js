/**
 * Emitter dispatch — schema filename → per-schema emit function.
 *
 * The build orchestrator consults this map to pick the right emitter for an
 * entry. Adding a new canon schema means adding its emitter here; the rest
 * of the build step is schema-agnostic.
 */

import { emitMonster } from './monster.js';
import { emitCharacter } from './character.js';
import { emitDeity } from './deity.js';
import { emitLocation } from './location.js';
import { emitRelic } from './relic.js';

export const EMITTERS = {
  'monster.schema.json': emitMonster,
  'character.schema.json': emitCharacter,
  'deity.schema.json': emitDeity,
  'location.schema.json': emitLocation,
  'relic.schema.json': emitRelic,
};

/**
 * Get the emitter for a given schema filename.
 * Returns null when no emitter is registered — orchestrator uses this to
 * surface a structured error rather than silently dropping entries.
 */
export function getEmitter(schemaName) {
  return EMITTERS[schemaName] || null;
}

export { emitMonster, emitCharacter, emitDeity, emitLocation, emitRelic };
