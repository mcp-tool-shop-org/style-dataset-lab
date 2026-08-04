/**
 * M3: scripts/qwen_generate.py's subject/variation loop called generate()
 * with no try/except, and generation.json was written exactly ONCE, after
 * the loop finished. A single item's failure (a real, named failure mode —
 * generate() raises RuntimeError("ComfyUI generation timed out") on a
 * genuine timeout, or — as in this test environment, deliberately — a fast
 * connection-refused because no ComfyUI is listening) crashed the whole
 * process uncaught, BEFORE generation.json was ever written. A 200-image
 * wave failing at item 130 left 129 rendered PNGs on disk with NO
 * generation.json at all — the PIN_PER_STEP provenance this file's own
 * docstring promises, fully lost for every item, including the ones that
 * succeeded.
 *
 * This drives the REAL CLI script. No ComfyUI is required — the absence of
 * one on 127.0.0.1:8188 in this environment IS the per-item failure this
 * test exercises (confirmed fast: WinError 10061 / ECONNREFUSED, not the
 * 10-minute polling timeout) — and asserts generation.json exists
 * afterward with per-item status/error detail, and that the process does
 * not crash with an uncaught Python traceback even when every item fails.
 *
 * Skips gracefully (not fail) when `python` is unavailable, matching
 * qwen-python-parity.test.js's convention — Python is a runtime dependency
 * of this ONE bridge script, not of the package.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, '..', '..');
const QWEN_SCRIPT = join(REPO_ROOT, 'scripts', 'qwen_generate.py');

function findPython() {
  for (const cmd of ['python', 'python3']) {
    const res = spawnSync(cmd, ['--version'], { encoding: 'utf-8' });
    if (res.status === 0) return cmd;
  }
  return null;
}

/**
 * The interpreter existing is not the same as the script being runnable —
 * qwen_generate.py imports Pillow. Probing only for a python binary passed on
 * ubuntu-latest (which ships python3) while Pillow was absent, so this test
 * FAILED with ModuleNotFoundError instead of skipping. A missing optional
 * dependency must skip; a real regression must fail.
 */
function pythonCanRunScript(cmd) {
  if (!cmd) return false;
  const res = spawnSync(cmd, ['-c', 'import PIL; from PIL import Image'], { encoding: 'utf-8' });
  return res.status === 0;
}

const PYTHON_BIN = findPython();
const PYTHON = pythonCanRunScript(PYTHON_BIN) ? PYTHON_BIN : null;
const SKIP_REASON = PYTHON_BIN
  ? 'python found but Pillow is not installed — qwen_generate.py cannot run, skipping'
  : 'python not found on PATH — skipping cross-language check';

const WAVE = {
  wave: 'm3-partial-failure-check',
  style_prefix: 'test style',
  defaults: { negative: 'bad', width: 512, height: 512, steps: 4, cfg: 2.0, base_seed: 500 },
  subjects: [
    { id: 'subj_a', prompt: 'a test prompt', variations: 1 },
    { id: 'subj_b', prompt: 'another test prompt', variations: 1 },
  ],
};

test(
  'qwen_generate.py: a per-item generation failure still writes generation.json with per-item error detail, not an uncaught crash (M3)',
  { skip: PYTHON ? false : SKIP_REASON, timeout: 60000 },
  () => {
    const dir = mkdtempSync(join(tmpdir(), 'sdlab-qwen-m3-'));
    try {
      const wavePath = join(dir, 'wave.json');
      const outDir = join(dir, 'out');
      writeFileSync(wavePath, JSON.stringify(WAVE, null, 2));

      // No ComfyUI is expected to be listening on 127.0.0.1:8188 in this
      // test environment — that absence IS the per-item failure driven here.
      const res = spawnSync(PYTHON, [QWEN_SCRIPT, '--wave', wavePath, '--out', outDir], {
        encoding: 'utf-8',
        cwd: REPO_ROOT,
        timeout: 55000,
      });

      // Before the fix: an unhandled RuntimeError/URLError from generate()
      // prints a raw Python traceback and generation.json is NEVER written.
      // After the fix: a controlled failure summary, and a receipt either way.
      assert.doesNotMatch(
        res.stderr || '',
        /Traceback \(most recent call last\)/,
        `expected no uncaught Python traceback:\nstdout: ${res.stdout}\nstderr: ${res.stderr}`
      );

      const receiptPath = join(outDir, 'generation.json');
      assert.ok(
        existsSync(receiptPath),
        `generation.json was not written at all — this is the M3 provenance-loss defect: a failed item took the ` +
        `whole wave's receipt down with it.\nstdout: ${res.stdout}\nstderr: ${res.stderr}`
      );

      const receipt = JSON.parse(readFileSync(receiptPath, 'utf-8'));
      assert.equal(receipt.items.length, 2, 'both attempted items should be recorded, not just the ones before the first failure');
      for (const item of receipt.items) {
        assert.equal(item.status, 'error', `expected item "${item.id}" to be recorded with status "error"`);
        assert.ok(typeof item.error === 'string' && item.error.length > 0, `expected item "${item.id}" to carry an error message`);
      }
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }
);
