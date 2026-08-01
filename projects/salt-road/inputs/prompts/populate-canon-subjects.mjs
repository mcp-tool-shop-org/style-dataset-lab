#!/usr/bin/env node
// populate-canon-subjects — write a CONTENT-ONLY subject line onto each approved
// record's canon block, for caption_strategy 'subject-natural-language'.
//
// Source of truth is the authored subject (wave-v2.json items[].subject, or the
// v1 manifest plates[].subject) — NEVER provenance.prompt, which carries the
// style preamble (prompt-bleed antipattern, see lib/captions.js).
//
// A sanitizer strips style vocabulary that leaked into a few hand-authored
// subjects ("soft painted gouache texture throughout"). Style must attach to the
// `saltroad` trigger; naming it in the caption teaches dependence on the phrase.
import { readFile, writeFile, readdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJ = join(HERE, "..", "..");
const recDir = join(PROJ, "records");

// Style phrases that must never appear in a caption.
const STYLE_PATTERNS = [
  /\bsoft painted gouache texture throughout\b,?\s*/gi,
  /\bhand-painted[^,]*,?\s*/gi,
  /\bpainterly gouache[^,]*,?\s*/gi,
  /\bvisible brushwork\b,?\s*/gi,
  /\bsixteen-bit[^,]*,?\s*/gi,
  /\brestrained palette[^,]*,?\s*/gi,
  /\bflat readable silhouettes[^,]*,?\s*/gi,
  /\bmemory-bright colou?r\b,?\s*/gi,
  /\bgame environment art plate\b,?\s*/gi,
  /\bbroad visible gouache strokes\b/gi,
];

function sanitize(s) {
  let out = " " + s.trim() + " ";
  for (const p of STYLE_PATTERNS) out = out.replace(p, " ");
  return out.replace(/\s+/g, " ").replace(/\s+,/g, ",").replace(/,\s*,/g, ",")
    .replace(/^[,\s]+/, "").replace(/[,\s]+$/, "").trim();
}

const subjects = new Map();

// wave-2 (67 plates, ids w2_*)
const wave = JSON.parse(await readFile(join(HERE, "wave-v2.json"), "utf8"));
for (const it of wave.items) subjects.set(`styleset_${it.id}`, it.subject);

// v1 keepers (ids p01..p20 — manifest plates carry preamble separately)
const man = JSON.parse(await readFile(join(HERE, "style-set-v1-manifest.json"), "utf8"));
for (const p of man.plates) {
  const short = p.id.split("-")[0];             // p01-quay-dawn -> p01
  for (const suffix of ["", "v2"]) {
    const key = `styleset_${short}${suffix}_${p.id.split("-").slice(1).join("_")}`;
    subjects.set(key, p.subject);
  }
  subjects.set(`__by_short_${short}`, p.subject);
}

let written = 0, missing = [];
for (const f of await readdir(recDir)) {
  if (!f.endsWith(".json")) continue;
  const rp = join(recDir, f);
  const r = JSON.parse(await readFile(rp, "utf8"));
  if (r.judgment?.status !== "approved") continue;

  let subj = subjects.get(r.id);
  if (!subj) {
    // v1 records: styleset_p11v2_beam_scale -> short p11
    const m = r.id.match(/^styleset_(p\d\d)/);
    if (m) subj = subjects.get(`__by_short_${m[1]}`);
  }
  if (!subj) { missing.push(r.id); continue; }

  const clean = sanitize(subj);
  r.canon = { ...(r.canon || {}), subject: clean, subject_source: "authored subject line (wave-v2.json / style-set-v1-manifest.json) — NOT provenance.prompt" };
  await writeFile(rp, JSON.stringify(r, null, 2) + "\n");
  written++;
}

console.log(`canon.subject written: ${written}`);
if (missing.length) console.log(`NO SUBJECT FOUND (${missing.length}): ${missing.join(", ")}`);
