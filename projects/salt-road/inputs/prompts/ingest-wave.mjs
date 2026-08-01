#!/usr/bin/env node
// ingest-wave — turn a prompt-foundry wave + wave-runner receipts into sdlab
// records (schema 2.0.0, full pinned provenance), ready for `sdlab curate`.
//   node ingest-wave.mjs [--wave wave-v2.json] [--dir set-v2-2026-07-30]
import { readFile, writeFile, mkdir, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJ = join(HERE, "..", "..");
const args = process.argv.slice(2);
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const WAVE = arg("--wave", join(HERE, "wave-v2.json"));
const DIR = arg("--dir", "set-v2-2026-07-30");

const F = JSON.parse(await readFile(join(HERE, "formula.json"), "utf8"));
const wave = JSON.parse(await readFile(WAVE, "utf8"));
const S = F.settings;

const recDir = join(PROJ, "records");
await mkdir(recDir, { recursive: true });
let written = 0, skipped = 0, missing = 0;
for (const item of wave.items) {
  const file = `${item.id}.png`;
  const abs = join(PROJ, "inbox", "generated", DIR, file);
  if (!existsSync(abs)) { missing++; continue; }
  const rid = `styleset_${item.id}`;
  const rp = join(recDir, `${rid}.json`);
  if (existsSync(rp)) { skipped++; continue; }
  const rec = {
    id: rid,
    schema_version: "2.0.0",
    created_at: new Date().toISOString(),
    asset_path: `inbox/generated/${DIR}/${file}`,
    image: { format: "png", width: S.width, height: S.height, bytes: (await stat(abs)).size },
    provenance: {
      source: "generated-qwen-cloud",
      wave: `salt-road-style-set-${DIR}`,
      base: "qwen-image-2512",
      backend: "comfy-cloud official API via wave-runner.py (bridge transport)",
      prompt: `${F.preambles[item.preamble]}, ${item.subject}`,
      negative_prompt: F.negatives[item.neg] + (item.negExtra || ""),
      seed: item.seed,
      steps: S.steps, cfg: S.cfg, sampler: S.sampler, scheduler: S.scheduler, shift: S.shift,
      width: S.width, height: S.height,
      unet: S.unet, clip: S.clip, vae: S.vae,
      style_prefix: "saltroad (trigger reserved — LoRA not yet trained)",
      loras: [],
      controlnet: item.cn ? { model: S.controlnet_model, ...item.cn } : null,
      enriched_by: item.enriched_by || "hand-authored",
      gpu_model: "Comfy Cloud RTX 6000",
      run_manifest: "inputs/prompts/wave-v2.json + formula.json + receipts.jsonl",
    },
    judgment: null,
    canon: null,
    tags: ["style-set-v2", "environment", "salt-road"],
  };
  await writeFile(rp, JSON.stringify(rec, null, 2) + "\n");
  written++;
}
console.log(`records: ${written} written, ${skipped} existing, ${missing} images missing`);
