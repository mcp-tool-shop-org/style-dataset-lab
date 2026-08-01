#!/usr/bin/env node
// build-review-page — regenerate the Director review HTML + contact-sheet list
// from the live sdlab records (borderline = candidates). Deterministic.
import { readFile, readdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJ = join(HERE, "..", "..");
const recDir = join(PROJ, "records");

const STATUS = process.argv[2] || "borderline";
const recs = [];
for (const f of await readdir(recDir)) {
  if (!f.endsWith(".json")) continue;
  const r = JSON.parse(await readFile(join(recDir, f), "utf8"));
  if (r.judgment?.status === STATUS) recs.push(r);
}
recs.sort((a, b) => a.id.localeCompare(b.id));
const flagged = recs.filter((r) => r.judgment.explanation.includes("FLAGGED"));
const clean = recs.filter((r) => !r.judgment.explanation.includes("FLAGGED"));

const card = (r) => {
  const img = r.asset_path.replace(/^outputs\//, "");
  const isFlag = r.judgment.explanation.includes("FLAGGED");
  const note = r.judgment.explanation
    .replace("Advisor-screened wave-2 candidate, FLAGGED: ", "")
    .replace("Advisor-screened wave-2 candidate: ", "")
    .replace("Advisor-screened candidate: ", "")
    .replace(" Awaiting Director ruling.", "").replace(" Awaiting ruling.", "");
  return `<div class="card"><a href="${img}"><img src="${img}" loading="lazy"></a><div class="body"><div class="id">${r.id.replace("styleset_", "")}</div><div class="${isFlag ? "flag" : "ok"}">${note}</div></div></div>`;
};

const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Salt Road — Style Set v2 pool — Director Review</title>
<style>
:root{color-scheme:dark}body{background:#16181c;color:#d8d5cd;font:15px/1.5 "Segoe UI",system-ui,sans-serif;margin:0;padding:32px}
h1{font-size:22px;color:#e8c987;margin:0 0 4px}h2{font-size:17px;color:#e8c987;margin:30px 0 10px}
.rule{background:#26221a;border:1px solid #6b5a33;border-radius:8px;padding:10px 14px;margin:14px 0 20px;color:#e8d9b0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:16px}
.card{background:#1d2025;border:1px solid #33373e;border-radius:10px;overflow:hidden}
.card img{width:100%;display:block}.card .body{padding:9px 12px}.card .id{font-weight:600;color:#f0ede4}
.flag{color:#e0a35c;font-size:13px;margin-top:3px}.ok{color:#8fbc8f;font-size:13px;margin-top:3px}
table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #33373e;padding:6px 10px;font-size:13.5px;text-align:left}
code{background:#26292e;padding:1px 5px;border-radius:4px;font-size:13px}
</style></head><body>
<h1>Salt Road — the expanded pool: ${recs.length} candidates</h1>
<div>${clean.length} advisor-clean + ${flagged.length} flagged · all curated <b>borderline</b> (HOLD) in sdlab · 25 rejects with named failures in <code>outputs/rejected/</code> · every prompt/seed/setting pinned (wave-v2.json + formula.json + manifest).</div>
<div class="rule">⚖ <b>Judge at FULL RES</b> — click any tile; files live in <code>outputs\\borderline\\</code>. Recommendation: rule the whole pool, aiming for ~50 finals. Flagged plates carry exactly what to weigh; several are one finishing-pass away from clean.</div>
<h2>The rulings needed</h2>
<table>
<tr><th>#</th><th>Question</th></tr>
<tr><td>1</td><td><b>The look</b> — the pool now spans weather, seasons, interiors, studies, sea states and the fun lane. Is this the game? Name any plate that feels like a different game.</td></tr>
<tr><td>2</td><td><b>Half-timber</b> — three delightful plates (w2_008 cat+bows, w2_015 alley, w2_060 laundry courtyard) lean on exposed timber framing, which the contract's material table excludes. Admit the material, or re-roll those subjects in limewashed masonry?</td></tr>
<tr><td>3</td><td><b>Isometric strays</b> — w2_014 (blue-hour dock) reads cozy-isometric rather than the flat-on oblique. Keep as variety or hold the projection line?</td></tr>
<tr><td>4</td><td><b>Finishing-pass queue</b> — ~10 plates are keeper-grade except one artifact (digits on a cask, a glowing emblem, pseudo-text plaque). Approve them conditional on the human finishing pass the contract already requires?</td></tr>
<tr><td>5</td><td><b>Set size</b> — advisor recommends ~50 finals from these ${recs.length}. More breadth (60+) risks register dilution; fewer (30) under-covers interiors and weather.</td></tr>
</table>
<h2>Advisor-clean candidates (${clean.length})</h2>
<div class="grid">${clean.map(card).join("\n")}</div>
<h2>Flagged — your call (${flagged.length})</h2>
<div class="grid">${flagged.map(card).join("\n")}</div>
</body></html>`;

await writeFile(join(PROJ, "outputs", "style-set-v2-review.html"), html);
console.log(`review page: ${recs.length} candidates (${clean.length} clean, ${flagged.length} flagged)`);
