/**
 * C2 Colab launcher guards (DESIGN-v3 §9.2 item 6 — lessons v4k, v4p, v4q).
 *
 * Implements the four required launcher guards:
 *   1. Independent wall watcher (`evaluateWallGuard`, v4k): honours `wallS` and
 *      `graceS` in ALL modes including `stub` mode.
 *   2. Independent cap watcher (`evaluateCapGuard`, v4k): honours `cap` and
 *      `margin` in ALL modes including `stub` mode (`spend = max(drop, rate * elapsed_h)`).
 *   3. `vitals.log` parser & `DEAD HARNESS` / `STALL` watcher (`parseVitalsLog`,
 *      `evaluateVitalsAndStallGuard`, v4p): trips `DEAD_HARNESS_TRIPPED` when 2
 *      consecutive `phase: run` samples have 0 active worker processes, and trips
 *      `STALL_GUARD_TRIPPED` when neither rows nor `vitals.log` advance in `stallS`.
 *   4. Host-RAM / cgroup limit pre-load projection check & between-item fetch
 *      (`checkHostRamProjection`, `runBetweenItemFetch`, v4q): refuses any step
 *      whose projected anonymous host RAM (`projectedMb * 1.05 > limitMb`) would
 *      trigger a kernel SIGKILL (`rc=-9`), and copies completed artifacts listed
 *      in `current.json` before `current.json` is overwritten for the next item.
 */

import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { inputError as rawInputError } from './errors.js';

function inputError(code, msg) {
  return rawInputError(code, `${code}: ${msg}`);
}

const WORKER_PROC_RE = /\b(comfy|main\.py|ai-toolkit|run\.py|llama-server|ollama|lane1_render\.py)\b/i;

/**
 * 1. Independent wall-clock watcher (v4k).
 * Never disabled in `stub` mode: trips when `elapsedS >= wallS - graceS`.
 *
 * @param {Object} opts
 * @param {string} [opts.mode='live']
 * @param {number} opts.elapsedS
 * @param {number} [opts.wallS=3000]
 * @param {number} [opts.graceS=60]
 * @returns {{ mode: string, tripped: boolean, code: string|null, remainingS: number, thresholdS: number }}
 */
export function evaluateWallGuard({
  mode = 'live',
  elapsedS,
  wallS = 3000,
  graceS = 60,
} = {}) {
  const thresholdS = Math.max(0, Number(wallS) - Number(graceS));
  const remainingS = thresholdS - Number(elapsedS);
  const tripped = Number(elapsedS) >= thresholdS;
  return {
    mode,
    tripped,
    code: tripped ? 'WALL_GUARD_TRIPPED' : null,
    remainingS,
    thresholdS,
  };
}

/**
 * 2. Independent CCU spend cap watcher (v4k).
 * Never disabled in `stub` mode: computes `spend = max(startBalance - currentBalance, rateCcuPerHour * elapsedH)`
 * and trips when `spend >= cap - margin`.
 *
 * @param {Object} opts
 * @param {string} [opts.mode='live']
 * @param {number} [opts.cap=0.05]
 * @param {number} [opts.margin=0.01]
 * @param {number|null} [opts.startBalance=null]
 * @param {number|null} [opts.currentBalance=null]
 * @param {number} [opts.rateCcuPerHour=0]
 * @param {number} [opts.elapsedS=0]
 * @returns {{ mode: string, tripped: boolean, code: string|null, spendCcu: number, ceilingCcu: number }}
 */
export function evaluateCapGuard({
  mode = 'live',
  cap = 0.05,
  margin = 0.01,
  startBalance = null,
  currentBalance = null,
  rateCcuPerHour = 0,
  elapsedS = 0,
} = {}) {
  const balanceDrop =
    startBalance !== null && currentBalance !== null
      ? Math.max(0, Number(startBalance) - Number(currentBalance))
      : 0;
  const rateEst = Math.max(0, (Number(rateCcuPerHour) * Number(elapsedS)) / 3600);
  const spendCcu = Math.max(balanceDrop, rateEst);
  const ceilingCcu = Math.max(0, Number(cap) - Number(margin));
  const tripped = spendCcu >= ceilingCcu;
  return {
    mode,
    tripped,
    code: tripped ? 'CAP_GUARD_TRIPPED' : null,
    spendCcu: Number(spendCcu.toFixed(6)),
    ceilingCcu: Number(ceilingCcu.toFixed(6)),
  };
}

/**
 * Parse `vitals.log` blocks (`=== VITALS <iso> ===`) emitted by the VM vitals sampler (v4p).
 *
 * @param {string} vitalsText
 * @returns {Array<{ timestamp: string, phase: string|null, workerProcCount: number, rawBlock: string }>}
 */
export function parseVitalsLog(vitalsText = '') {
  const blocks = String(vitalsText)
    .split(/^===\s*VITALS\s+/m)
    .map((b) => b.trim())
    .filter(Boolean);

  const samples = [];
  for (const block of blocks) {
    const lines = block.split(/\r?\n/);
    const header = lines[0] || '';
    const tsMatch = /^([^\s=]+)/.exec(header);
    const timestamp = tsMatch ? tsMatch[1] : '';

    let phase = null;
    let workerProcCount = 0;
    let inProc = false;

    for (let i = 1; i < lines.length; i++) {
      const line = lines[i];
      if (line.startsWith('PROC:')) {
        inProc = true;
        continue;
      }
      if (line.startsWith('HARNESS:')) {
        inProc = false;
        const payload = line.slice('HARNESS:'.length).trim();
        try {
          const parsed = JSON.parse(payload);
          phase = parsed.phase || null;
        } catch {
          const m = /"phase"\s*:\s*"([^"]+)"/.exec(payload) || /phase:\s*([a-z0-9_-]+)/i.exec(payload);
          phase = m ? m[1] : null;
        }
        continue;
      }
      if (inProc && WORKER_PROC_RE.test(line)) {
        workerProcCount++;
      }
    }

    samples.push({
      timestamp,
      phase,
      workerProcCount,
      rawBlock: block,
    });
  }
  return samples;
}

/**
 * 3. Evaluate the `DEAD HARNESS` and `STALL` watcher over `vitals.log` + idle timer (v4p).
 *
 * Trips `DEAD_HARNESS_TRIPPED` when the last 2 vitals samples both show
 * `phase === 'run'` (or `phase.startsWith('run')`) and `workerProcCount === 0`.
 * Otherwise trips `STALL_GUARD_TRIPPED` when `idleSeconds >= stallS`.
 *
 * @param {Object} opts
 * @param {string} opts.vitalsText
 * @param {number} [opts.idleSeconds=0]
 * @param {number} [opts.stallS=300]
 * @returns {{ tripped: boolean, code: string|null, reason: string|null, samplesCount: number }}
 */
export function evaluateVitalsAndStallGuard({
  vitalsText = '',
  idleSeconds = 0,
  stallS = 300,
} = {}) {
  const samples = parseVitalsLog(vitalsText);
  if (samples.length >= 2) {
    const lastTwo = samples.slice(-2);
    const bothDeadInRun = lastTwo.every(
      (s) => typeof s.phase === 'string' && s.phase.startsWith('run') && s.workerProcCount === 0
    );
    if (bothDeadInRun) {
      return {
        tripped: true,
        code: 'DEAD_HARNESS_TRIPPED',
        reason: '2 consecutive vitals samples in phase=run with 0 active worker processes',
        samplesCount: samples.length,
      };
    }
  }

  if (Number(idleSeconds) >= Number(stallS)) {
    return {
      tripped: true,
      code: 'STALL_GUARD_TRIPPED',
      reason: `No output row or vitals progress for ${idleSeconds}s (stallS=${stallS}s)`,
      samplesCount: samples.length,
    };
  }

  return {
    tripped: false,
    code: null,
    reason: null,
    samplesCount: samples.length,
  };
}

/**
 * 4a. Host-RAM / cgroup limit pre-load projection check (v4q).
 * Refuses any step whose projected anonymous host RAM (`(currentAnonMb + projectedDeltaMb) * safetyFactor`)
 * exceeds `min(memTotalMb, cgroupMaxMb)`.
 *
 * @param {Object} opts
 * @param {number} opts.currentAnonMb
 * @param {number} opts.projectedDeltaMb
 * @param {number} opts.memTotalMb
 * @param {number|null} [opts.cgroupMaxMb=null]
 * @param {number} [opts.safetyFactor=1.05]
 * @returns {{ ok: true, projectedMb: number, limitMb: number }}
 */
export function checkHostRamProjection({
  currentAnonMb,
  projectedDeltaMb,
  memTotalMb,
  cgroupMaxMb = null,
  safetyFactor = 1.05,
}) {
  const limits = [Number(memTotalMb)];
  if (cgroupMaxMb !== null && cgroupMaxMb !== undefined && Number.isFinite(Number(cgroupMaxMb))) {
    limits.push(Number(cgroupMaxMb));
  }
  const limitMb = Math.min(...limits);
  const rawProjected = Number(currentAnonMb) + Number(projectedDeltaMb);
  const projectedWithMargin = rawProjected * Number(safetyFactor);

  if (projectedWithMargin > limitMb) {
    throw inputError(
      'HOST_RAM_PROJECTION_EXCEEDED',
      `Projected anonymous host RAM ${projectedWithMargin.toFixed(1)} MB (${rawProjected} MB * ${safetyFactor}) exceeds host/cgroup ceiling ${limitMb} MB (v4q guard against kernel SIGKILL rc=-9).`
    );
  }

  return {
    ok: true,
    projectedMb: Number(projectedWithMargin.toFixed(1)),
    limitMb,
  };
}

/**
 * 4b. Between-item fetch (v4q): copies every completed file listed in `current.json`
 * from `remoteDir` to `localDir` BEFORE `current.json` is overwritten for `nextItem`.
 *
 * @param {Object} opts
 * @param {string} opts.remoteDir
 * @param {string} opts.localDir
 * @param {Object|null} [opts.nextItem=null]
 * @returns {{ copiedFiles: string[], previousItem: Object|null }}
 */
export function runBetweenItemFetch({ remoteDir, localDir, nextItem = null }) {
  mkdirSync(localDir, { recursive: true });
  const currentJsonPath = join(remoteDir, 'current.json');
  const copiedFiles = [];
  let previousItem = null;

  if (existsSync(currentJsonPath)) {
    previousItem = JSON.parse(readFileSync(currentJsonPath, 'utf-8'));
    const files = Array.isArray(previousItem?.files) ? previousItem.files : [];
    for (const relFile of files) {
      const src = join(remoteDir, relFile);
      if (existsSync(src)) {
        const dst = join(localDir, relFile);
        mkdirSync(join(dst, '..'), { recursive: true });
        copyFileSync(src, dst);
        copiedFiles.push(relFile);
      }
    }
    copyFileSync(currentJsonPath, join(localDir, 'current.json'));
  }

  if (nextItem) {
    writeFileSync(currentJsonPath, JSON.stringify(nextItem, null, 2) + '\n', 'utf-8');
  }

  return { copiedFiles, previousItem };
}
