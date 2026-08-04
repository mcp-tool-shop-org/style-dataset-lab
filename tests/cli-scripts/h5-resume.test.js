/**
 * H5: generate.js was the only one of the four ComfyUI generator scripts
 * that implemented --resume (skip an item whose record + output image both
 * already exist, while still advancing the seed counter so a resumed run
 * stays bit-identical to an uninterrupted one). generate-identity.js,
 * generate-controlnet.js, generate-ipadapter.js had none — most expensive
 * for generate-identity, where an interrupted 12-subject run meant
 * regenerating all 12 from scratch.
 *
 * Ported via scripts/_resume.js (shared, since lib/ is outside this fix's
 * file ownership) so all three generators — and any future one — get the
 * same discipline by importing it.
 *
 * These tests drive the REAL CLI scripts against a minimal in-process fake
 * ComfyUI HTTP server (system_stats / prompt / history / view / upload —
 * just enough surface for submitAndWait + downloadImage + uploadImage to
 * succeed), so no real GPU/ComfyUI install is required.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdirSync, writeFileSync, rmSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { REPO_ROOT } from '../../lib/paths.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BIN = join(__dirname, '..', '..', 'bin', 'sdlab.js');
const PROJECTS_DIR = join(REPO_ROOT, 'projects');

/**
 * Minimal fake ComfyUI: /system_stats always 200 (health check), /prompt
 * returns an incrementing prompt_id, /history/<id> reports completed
 * immediately with one fake image, /view returns arbitrary bytes (nothing
 * in these scripts decodes the PNG — they just persist imgData to disk and
 * record its byte length), /upload/image acks any upload.
 */
function startFakeComfyServer() {
  let promptCounter = 0;
  const FAKE_BYTES = Buffer.from([0x89, 0x50, 0x4e, 0x47, 1, 2, 3, 4]);
  const server = createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    if (req.method === 'GET' && url.pathname === '/system_stats') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end('{}');
      return;
    }
    if (req.method === 'POST' && url.pathname === '/prompt') {
      req.resume();
      req.on('end', () => {
        promptCounter++;
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ prompt_id: `fake-prompt-${promptCounter}` }));
      });
      return;
    }
    if (req.method === 'GET' && url.pathname.startsWith('/history/')) {
      const id = url.pathname.slice('/history/'.length);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        [id]: { status: { completed: true }, outputs: { '9': { images: [{ filename: `${id}.png`, subfolder: '' }] } } },
      }));
      return;
    }
    if (req.method === 'GET' && url.pathname === '/view') {
      res.writeHead(200, { 'Content-Type': 'image/png' });
      res.end(FAKE_BYTES);
      return;
    }
    if (req.method === 'POST' && url.pathname === '/upload/image') {
      req.resume();
      req.on('end', () => {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ name: 'uploaded.png' }));
      });
      return;
    }
    res.writeHead(404);
    res.end('not found');
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      resolve({ server, url: `http://127.0.0.1:${server.address().port}` });
    });
  });
}

function stopFakeComfyServer(server) {
  return new Promise((resolve) => server.close(() => resolve()));
}

// spawnSync would block THIS process's event loop for the child's entire
// lifetime — and the in-process fake ComfyUI server above needs that event
// loop running concurrently to answer the child's HTTP requests. Async
// spawn() (wrapped in a Promise) keeps both running at once.
function runCli(args, env = {}) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [BIN, ...args], {
      env: { ...process.env, SDLAB_QUIET_FALLBACK: '1', ...env },
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { stdout += d; });
    child.stderr.on('data', (d) => { stderr += d; });
    const timer = setTimeout(() => child.kill(), 30000);
    child.on('close', (status) => {
      clearTimeout(timer);
      resolve({ stdout, stderr, status });
    });
  });
}

function makeFixture(name, files) {
  const dir = join(PROJECTS_DIR, name);
  mkdirSync(dir, { recursive: true });
  for (const [rel, content] of Object.entries(files)) {
    const full = join(dir, rel);
    mkdirSync(join(full, '..'), { recursive: true });
    writeFileSync(full, content);
  }
  return dir;
}

function removeFixture(name) {
  rmSync(join(PROJECTS_DIR, name), { recursive: true, force: true });
}

const PROJECT_JSON = JSON.stringify({ name: 'fixture', domain: 'test', defaults: {} });

// ─── generate-identity.js: skip + seed-preservation across the skip ──────

test('H5: generate-identity.js --resume skips an already-done shot AND the NEXT shot still gets the seed it would have gotten uninterrupted', async () => {
  const name = 'sdl-h5-identity-resume';
  let comfy;
  try {
    comfy = await startFakeComfyServer();

    const packet = {
      lane: 'test-lane',
      style_prefix: 'test style',
      negative_base: 'test negative',
      subjects: [{
        subject_name: 'test_subject',
        subject_type: 'named_character',
        faction: 'test',
        role: 'test',
        identity_lock: { non_negotiable_details: ['detail 1'], forbidden_drift_cues: ['cue 1'] },
        shots: [{
          id: 'shot1', view_type: 'anchor_portrait', shot_type: 'test',
          identity_anchor: 'test', scene_function: 'test', prompt: 'a test prompt',
        }],
      }],
    };
    const projectDir = makeFixture(name, {
      'project.json': PROJECT_JSON,
      'identity-packet.json': JSON.stringify(packet),
    });

    // Simulate "seed 0 already completed by a prior, interrupted run":
    // pre-create BOTH the record and the output image for shot1_s0. seeds
    // 1 and 2 do not exist yet and must be freshly generated this run.
    const BASE_SEED = 27000; // DEFAULTS.base_seed in generate-identity.js
    mkdirSync(join(projectDir, 'records'), { recursive: true });
    mkdirSync(join(projectDir, 'outputs', 'candidates'), { recursive: true });
    writeFileSync(join(projectDir, 'records', 'shot1_s0.json'), JSON.stringify({ id: 'shot1_s0', provenance: { seed: BASE_SEED } }));
    writeFileSync(join(projectDir, 'outputs', 'candidates', 'shot1_s0.png'), Buffer.from([0x89, 0x50, 0x4e, 0x47]));

    const { stdout, status } = await runCli(
      ['generate:identity', 'identity-packet.json', '--project', name, '--seeds', '3', '--resume'],
      { COMFY_URL: comfy.url }
    );
    assert.equal(status, 0, `expected exit 0, got ${status}\nstdout: ${stdout}`);
    assert.match(stdout, /shot1_s0.*resumed.*skipped/i, `expected shot1_s0 to be reported as resumed/skipped:\n${stdout}`);

    // The crux of H5: seed 1 and seed 2 must land on base+1 / base+2 — NOT
    // base+0 / base+1, which is what they would get if the skip failed to
    // advance imageIndex (reusing the skipped slot's seed for the next
    // real item, then compounding the shift for every item after it).
    const rec1 = JSON.parse(readFileSync(join(projectDir, 'records', 'shot1_s1.json'), 'utf-8'));
    const rec2 = JSON.parse(readFileSync(join(projectDir, 'records', 'shot1_s2.json'), 'utf-8'));
    assert.equal(rec1.provenance.seed, BASE_SEED + 1, `shot1_s1 seed must be base+1 (uninterrupted-run value), got ${rec1.provenance.seed}`);
    assert.equal(rec2.provenance.seed, BASE_SEED + 2, `shot1_s2 seed must be base+2 (uninterrupted-run value), got ${rec2.provenance.seed}`);
  } finally {
    if (comfy) await stopFakeComfyServer(comfy.server);
    removeFixture(name);
  }
});

// ─── generate-controlnet.js: skip works (seed math is loop-index-derived,
//     so it is safe by construction — this proves the SKIP itself fires) ──

test('H5: generate-controlnet.js --resume skips seed slots whose output image already exists', async () => {
  const name = 'sdl-h5-controlnet-resume';
  let comfy;
  try {
    comfy = await startFakeComfyServer();
    const projectDir = makeFixture(name, {
      'project.json': PROJECT_JSON,
      'guide.png': '',
    });

    // Pre-create ALL THREE expected outputs — every seed slot is already
    // "done", so a correct --resume run should skip everything and never
    // even need the fake server's /prompt or /history endpoints.
    const BASE_SEED = 27100; // DEFAULTS.base_seed in generate-controlnet.js
    mkdirSync(join(projectDir, 'outputs', 'candidates'), { recursive: true });
    for (let si = 0; si < 3; si++) {
      writeFileSync(join(projectDir, 'outputs', 'candidates', `test_subject_cn_s${si}.png`), Buffer.from([0x89, 0x50, 0x4e, 0x47]));
    }

    const { stdout, status } = await runCli(
      ['generate:controlnet', '--project', name, '--subject', 'test_subject', '--guide', 'guide.png', '--prompt', 'x', '--seeds', '3', '--resume'],
      { COMFY_URL: comfy.url }
    );
    assert.equal(status, 0, `expected exit 0, got ${status}\nstdout: ${stdout}`);
    assert.match(stdout, /test_subject_cn_s0.*resumed.*skipped/i, `expected s0 resumed/skipped:\n${stdout}`);
    assert.match(stdout, /test_subject_cn_s1.*resumed.*skipped/i, `expected s1 resumed/skipped:\n${stdout}`);
    assert.match(stdout, /test_subject_cn_s2.*resumed.*skipped/i, `expected s2 resumed/skipped:\n${stdout}`);
    assert.match(stdout, /3 resumed/, `expected the summary line to report 3 resumed:\n${stdout}`);
  } finally {
    if (comfy) await stopFakeComfyServer(comfy.server);
    removeFixture(name);
  }
});

// ─── generate-ipadapter.js: skip works ────────────────────────────────────

test('H5: generate-ipadapter.js --resume skips seed slots whose output image already exists', async () => {
  const name = 'sdl-h5-ipadapter-resume';
  let comfy;
  try {
    comfy = await startFakeComfyServer();
    const projectDir = makeFixture(name, {
      'project.json': PROJECT_JSON,
      'ref.png': '',
    });

    const BASE_SEED = 27200; // DEFAULTS.base_seed in generate-ipadapter.js
    mkdirSync(join(projectDir, 'outputs', 'candidates'), { recursive: true });
    for (let si = 0; si < 2; si++) {
      writeFileSync(join(projectDir, 'outputs', 'candidates', `test_subject_ipa_s${si}.png`), Buffer.from([0x89, 0x50, 0x4e, 0x47]));
    }

    const { stdout, status } = await runCli(
      ['generate:ipadapter', '--project', name, '--subject', 'test_subject', '--ref', 'ref.png', '--prompt', 'x', '--seeds', '2', '--resume'],
      { COMFY_URL: comfy.url }
    );
    assert.equal(status, 0, `expected exit 0, got ${status}\nstdout: ${stdout}`);
    assert.match(stdout, /test_subject_ipa_s0.*resumed.*skipped/i, `expected s0 resumed/skipped:\n${stdout}`);
    assert.match(stdout, /test_subject_ipa_s1.*resumed.*skipped/i, `expected s1 resumed/skipped:\n${stdout}`);
    assert.match(stdout, /2 resumed/, `expected the summary to report 2 resumed:\n${stdout}`);
  } finally {
    if (comfy) await stopFakeComfyServer(comfy.server);
    removeFixture(name);
  }
});
