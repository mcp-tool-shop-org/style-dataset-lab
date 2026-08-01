#!/usr/bin/env node
// prompt-foundry — bulk subject generation on the pinned Salt Road formula.
// Seeds (territory matrix) -> Ollama cloud-crew enrichment -> deterministic §5
// lint -> wave JSON for wave-runner.py. Runs without Claude in the loop.
//
//   node prompt-foundry.mjs [--model glm-4.6:cloud] [--no-llm] [--out wave-v2.json]
//
// --no-llm falls back to the raw kernels (still lint-gated) so the pipeline
// degrades gracefully when the daemon is down.
import { readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
// Default LOCAL (Director 2026-07-30: ollama cloud unreliable — "use my local
// models or openrouter free models"). Cloud aliases rot (glm-4.6/deepseek/gemini
// all 410 Gone); the 5090 is idle while generation runs on Comfy Cloud.
const MODEL = arg("--model", "qwen3.6:35b-a3b");
const OUT = arg("--out", join(HERE, "wave-v2.json"));
const NO_LLM = args.includes("--no-llm");
const OLLAMA = process.env.OLLAMA_HOST || "http://localhost:11434";

const formula = JSON.parse(await readFile(join(HERE, "formula.json"), "utf8"));
const G = formula.control_guides;

// ---------------------------------------------------------------------------
// Hand-authored rebuilds (Director cull 2026-07-30: richer, prouder, more fun).
// These skip the LLM but not the lint.
const FIXED = [
  { id: "w2_r04_crane_tower", seed: 730404, preamble: "ctl", neg: "ctl",
    cn: { image: G.p04_crane, type: "depth", strength: 0.5, end: 0.6 },
    subject: "the great harbour crane at golden evening, two round towers of weathered oxide-red brick patched with lime repairs and gull stains, iron tie plates and putlog holes in the brickwork, a steep moss-edged tile roof between the towers, the mighty oak jib slung out over the water with its pulley block and hemp fall lowering a branded cask toward a waiting barge, coiled hawsers and worn stone bollards on the quay platform, small barred windows glowing faintly, long warm reflections trembling in the grey-green water, gulls wheeling around the roof, low raking sunlight" },
  { id: "w2_r05_crane_treadwheel", seed: 730405, preamble: "ctl", neg: "ctl",
    cn: { image: G.p05_treadwheel, type: "depth", strength: 0.5, end: 0.6 },
    subject: "inside the harbour crane's open gallery at working noon, the great oak treadwheel filling the archway between brick piers, polished treads and heavy spokes worn pale by use, the thick axle drum wound with taut hemp rope running over an iron-shod pulley to a cask swinging above the quay edge, tarred braces and pegged joints, chalk tallies scratched beside the arch, stacked casks and a coiled line on the worn timber deck below, bright water glittering beyond the arch, warm light raking through the gallery" },
  { id: "w2_r07_bonded_door", seed: 730407, preamble: "ctl", neg: "ctl",
    cn: { image: G.p07_door_v3, type: "depth", strength: 0.55, end: 0.6 },
    subject: "the bonded warehouse door in a narrow quay lane, heavy oak double door aged silver-brown with hand-forged iron straps and clenched nails, a crimson wax seal on plaited cord over the meeting stile, the lintel scored with old tally marks, patchwork limewash in mismatched ochre and cream batches flaking to show earlier colours, a stout hoist beam overhead with its tackle block and hook throwing a long shadow, shuttered windows, neighbouring leaning facades crowding in on both sides, worn cobbles with cart ruts and grass tufts, warm afternoon side light" },
  { id: "w2_r14_crooked_stair", seed: 730414, preamble: "ctl", neg: "ctl",
    cn: { image: G.p14_stair_v3, type: "depth", strength: 0.5, end: 0.6 },
    subject: "the crooked harbour stair plunging between crowding buildings, twenty-two uneven stone steps each worn to a hollow, risers patched with brick and mortar, moss and ferns in the shaded joints, flaking limewash walls in mismatched warm batches with an iron handrail stub and a rusted ring bolt, washing-line shadow crossing the passage, a bright sliver of grey-blue harbour water with a moored boat's bow at the bottom, rooftop tiles catching sun at the top, cool shade cut by one warm shaft of light" },
  { id: "w2_r16_hull_brig", seed: 730416, preamble: "ctl", neg: "ctl",
    cn: { image: G.p16_brig, type: "depth", strength: 0.7, end: 0.6 },
    subject: "a two-masted trading brig moored broadside at the stone quay, dark tarred hull with a pale scrubbed sheer strake and rope fenders, weather-stained patched sails loosed to dry from the square yards, hemp standing rigging and ratlines taut, deck crowded with branded casks, coiled lines and a tarpaulined hatch, heavy mooring hawsers running to worn stone bollards, gulls on the yardarms, morning mist thinning over grey-blue water, warm light catching the mastheads and canvas, the quay stones wet in a cooler ramp at the lip" },
  { id: "w2_r17_hull_caravel", seed: 730417, preamble: "ctl", neg: "ctl",
    negExtra: ", red cross, crusader cross, templar cross, heraldic cross",
    cn: { image: G.p17_caravel, type: "depth", strength: 0.7, end: 0.6 },
    subject: "a small weathered caravel at the quay seen from her quarter, rounded oak hull with visible strakes, scuffed paint and a patched rubbing strake, tall lateen sails of plain sun-bleached sailcloth with an intertwined merchant's mark in faded madder on the mainsail, hemp halyards and a rope ladder over the side, branded casks staged on the quay below the bollards, ripples lapping the hull with soft reflections, pale morning sky warming at the horizon, gulls about the masthead" },
  { id: "w2_r19_sea_chart", seed: 730419, preamble: "sea", neg: "sea", cn: null,
    subject: "flat top-down painted sea for a voyage map, cool slate grey-blue water built from broad visible gouache strokes in three muted tones, rhythmic hand-painted wave crests like an old chart's engraving turned to paint, a small wooden trading ship from above heeling slightly with a curling white wake, a hint of deeper slate shadow where the water deepens, calm deliberate plainness with the brushwork carrying all the life" },
];

// ---------------------------------------------------------------------------
// Territory matrix — 60 seeds. kernel = what the plate is; the LLM writes the
// full subject line in the house grammar.
const SEEDS = [
  // quay + exterior weather/light variants (14)
  ["w2_001", "land", "land", "the long quay in soft morning fog, hoists and masts fading in layers"],
  ["w2_002", "land", "land", "the quay after rain, wet cobbles mirroring warm windows, dripping hoist tackle"],
  ["w2_003", "land", "land", "the quay under bright overcast, colours flat and true, cargo everywhere awaiting the bell"],
  ["w2_004", "land", "land", "low tide exposing weed-slick lower quay stones, boats resting tilted on wet mud"],
  ["w2_005", "land", "land", "first winter frost on the quay, pale rime on casks and rooflines, breath-still water"],
  ["w2_006", "land", "land", "amber dusk over the warehouse row, last hoist load of the day swinging home"],
  ["w2_007", "land", "land", "a squall approaching the harbour, dark sky over sunlit ochre facades, tarpaulins hurried over cargo"],
  ["w2_008", "land", "land", "the warehouse row seen low from the water between two moored hulls"],
  ["w2_009", "land", "land", "spring morning, limewash fresh on one facade among faded neighbours, scaffold poles still up"],
  ["w2_010", "land", "land", "the harbour mouth breakwater of great tumbled stones, a beacon brazier at its head"],
  ["w2_011", "land", "land", "gulls mobbing a fish cart on the quay, baskets and glinting scales"],
  ["w2_012", "land", "land", "the customs pier at midday, striped mooring poles, an official skiff tied up"],
  ["w2_013", "land", "land", "salt cones under an open-sided quay shelter, white stacks catching the sun"],
  ["w2_014", "land", "land", "the quay at blue hour, lamplighter's ladder against a bracket, first lanterns lit"],
  // town fabric (8)
  ["w2_015", "land", "land", "a narrow alley between warehouse gables, hoist beams nearly touching overhead, one bright slot of sky"],
  ["w2_016", "land", "land", "rooftops of the port from a bell tower, tile ridges, hoist wheels, the harbour beyond"],
  ["w2_017", "land", "land", "the well square behind the quay, worn wellhead with windlass and bucket, cobbles radiating"],
  ["w2_018", "land", "land", "the chandlery front hung with coils of rope, lanterns, blocks and oars for sale"],
  ["w2_019", "land", "land", "the sail loft's tall gable with its full-height loading doors open, canvas bolt visible in shadow"],
  ["w2_020", "land", "land", "the cooperage yard, staves seasoning in stacks, finished casks in a pyramid, shavings drifted like snow"],
  ["w2_021", "land", "land", "net-drying racks along the shore, brown nets hung in catenaries, cork floats"],
  ["w2_022", "land", "land", "the town gate where the salt road leaves the port, worn arch, cart ruts heading inland"],
  // interiors (10)
  ["w2_023", "interior", "land", "the sail loft interior, an acre of pale canvas spread across a smooth timber floor, roped edges being seamed"],
  ["w2_024", "interior", "land", "the rope-walk, an impossibly long low shed with hemp strands stretched to a vanishing wheel"],
  ["w2_025", "interior", "land", "the chandlery interior, shelves dense with blocks, lanterns, tarred twine, brushes and bottled pitch"],
  ["w2_026", "interior", "land", "the cooperage at work, half-raised cask on the mare, shavings, firing cresset for bending staves"],
  ["w2_027", "interior", "land", "the salt store, white salt heaped in timber bays, wooden shovels, sacks stamped with the crown mark"],
  ["w2_028", "interior", "land", "the harbourmaster's room, tide tables pinned to boards, a brass telescope on the sill, the harbour in the window"],
  ["w2_029", "interior", "land", "the bonded warehouse upper gallery, sacks and chests in numbered bays, a shaft of light on dust"],
  ["w2_030", "interior", "land", "the weighing floor at dawn before opening, scales hanging still, queue-worn floor stones by the door"],
  ["w2_031", "interior", "land", "the counting house strongroom, iron-bound chests, a candle lantern, keys on a great ring"],
  ["w2_032", "interior", "land", "a warehouse doorway from inside, bright quay framed by dark tarred timbers, cargo silhouettes"],
  // studies (14)
  ["w2_033", "study", "land", "a mooring bollard wound with rope, every fibre and polished shoulder, wet stone around it"],
  ["w2_034", "study", "land", "folded brown nets with cork floats and a mending needle on the quay stones"],
  ["w2_035", "study", "land", "an iron lantern on its wall bracket, glass panes, smoke stain climbing the limewash"],
  ["w2_036", "study", "land", "a shuttered window in a patched limewash wall, flaking paint, iron hinge stains"],
  ["w2_037", "study", "land", "old roof tiles with moss and lichen, a gull standing on the ridge"],
  ["w2_038", "study", "land", "stamped salt sacks stacked on a pallet, crown and cooper marks, spilled white crystals"],
  ["w2_039", "study", "land", "sealing wax, brass stamp and folded papers on a worn oak counter"],
  ["w2_040", "study", "land", "a rusted iron mooring ring and chain on the wet quay lip, barnacles below the tide line"],
  ["w2_041", "study", "land", "a loaded handcart with iron-shod wheel standing in deep old ruts"],
  ["w2_042", "study", "land", "a row of worn stone bollards receding along the quay edge, each rope-polished differently"],
  ["w2_043", "study", "land", "great keys and a hasp lock on the bonded door's iron plate"],
  ["w2_044", "study", "land", "a hanging wooden signboard with a painted pictogram of a cask and beam-scale, no lettering, iron scrollwork"],
  ["w2_045", "study", "land", "stencilled crates and a tar brush resting on a barrel head, fresh black marks"],
  ["w2_046", "study", "land", "an old anchor leaning against the quay wall, flukes worn bright, chain pooled"],
  // water + light (8)
  ["w2_047", "sea", "sea", "harbour water close up, green-grey ripples with warm window reflections breaking across them"],
  ["w2_048", "sea", "sea", "open sea at silver dawn, glassy calm, one low fishing boat far off"],
  ["w2_049", "sea", "sea", "open sea in a grey chop, short white-capped waves in ranks, spray blowing"],
  ["w2_050", "sea", "sea", "evening sea with an amber light path from a low sun, small ship silhouetted"],
  ["w2_051", "sea", "sea", "waves breaking white on the breakwater stones, spray hanging"],
  ["w2_052", "sea", "sea", "a mooring buoy and tarred posts standing in calm harbour water, reflections wobbling"],
  ["w2_053", "sea", "sea", "rain falling on harbour water, overlapping circles, muted grey light"],
  ["w2_054", "sea", "sea", "a ship's wake from above, white lace unfurling across slate water"],
  // fun (6)
  ["w2_055", "study", "land", "a harbour cat asleep on a warm bollard among coiled ropes, afternoon sun"],
  ["w2_056", "land", "land", "moonlight path across the harbour, silhouetted masts and hoists, one amber window awake"],
  ["w2_057", "study", "land", "spice sacks split open at a corner, rare colour accents of saffron and madder against hemp and oak"],
  ["w2_058", "study", "land", "the tide mark on the quay wall, bands of weed, barnacle and dry stone reading like strata"],
  ["w2_059", "land", "land", "storm light over the harbour mouth, a searing bright band under bruised cloud, boats running in"],
  ["w2_060", "land", "land", "washing lines strung between warehouse gables, sailcloth shirts and linens luffing like flags"],
];

// ---------------------------------------------------------------------------
const SYSTEM = `You write ONE subject line for a hand-painted trading-port game art plate (think a modern memory of a 1994 SNES harbour game, painted like rich gouache concept art). Rules, all hard:
- Output ONLY the subject line. No preamble, no quotes, no explanations.
- 45-85 words, comma-separated concrete noun phrases in the style of: "the long stone quay at first light, row of tall narrow limewashed warehouse fronts in mismatched ochre batches, a timber hoist beam projecting from each gable peak, stacked casks branded with cooper marks, long cold shadows".
- Early-modern North European trading port. NO people, figures, hands or faces. Animals like gulls or a cat are allowed.
- NO fantasy, magic, pirates, skulls, treasure. NO modern objects. NO written words or lettering on anything (pictograms and painted marks are good).
- Name real materials from this palette where they fit: limewash (patchy mismatched batches), ochre, tarred timber, weathered oak, oxide brick, sailcloth, hemp rope, quay stone (wet lip cooler and bluer than dry), brass.
- Any cargo carries marks: burned brands, chalk tallies, painted merchant monograms.
- End with a concrete light phrase (raking sun, lantern pools, overcast flatness, fog layers...).
- Density lives in stuff, not adjectives: prefer one more concrete object over one more adverb.`;

async function enrich(kernel) {
  const res = await fetch(`${OLLAMA}/api/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      model: MODEL, stream: false,
      options: { temperature: 0.85 },
      messages: [
        { role: "system", content: SYSTEM },
        { role: "user", content: `Write the subject line for this plate: ${kernel}` },
      ],
    }),
  });
  if (!res.ok) throw new Error(`ollama ${res.status}`);
  const j = await res.json();
  const model = j.model || "?";
  let line = (j.message?.content || "").trim()
    .replace(/^["'“]|["'”]$/g, "").replace(/\s+/g, " ")
    .replace(/<think>[\s\S]*?<\/think>/g, "").trim();
  return { line, model };
}

function lint(subject) {
  const L = formula.lint;
  const words = subject.split(/\s+/).length;
  const low = " " + subject.toLowerCase() + " ";
  const errs = [];
  if (words < L.min_words || words > L.max_words) errs.push(`words=${words}`);
  for (const b of L.banned) if (low.includes(b.toLowerCase())) errs.push(`banned:${b.trim()}`);
  if (!L.required_any.some((a) => low.includes(a))) errs.push("no-material-anchor");
  return errs;
}

const items = [];
const report = { pass: 0, fail: [], model_used: NO_LLM ? "none" : MODEL };
for (const f of FIXED) {
  const errs = lint(f.subject);
  if (errs.length) { report.fail.push({ id: f.id, errs, subject: f.subject }); continue; }
  items.push(f); report.pass++;
}
let n = 0;
for (const [id, preamble, neg, kernel] of SEEDS) {
  n++;
  let subject = kernel, modelUsed = "kernel";
  if (!NO_LLM) {
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const r = await enrich(kernel);
        modelUsed = r.model;
        if (r.line && lint(r.line).length === 0) { subject = r.line; break; }
        if (attempt === 2 && r.line) subject = r.line;
      } catch (e) { if (attempt === 2) console.error(`${id}: LLM failed (${e.message}), using kernel`); }
    }
  }
  const errs = lint(subject);
  if (errs.length) {
    // fall back to kernel if the enriched line fails lint
    const kerrs = lint(kernel);
    if (kerrs.length) { report.fail.push({ id, errs: kerrs, subject: kernel }); continue; }
    subject = kernel;
  }
  items.push({ id, seed: 730500 + n, preamble, neg, cn: null, subject, enriched_by: modelUsed });
  report.pass++;
  process.stdout.write(`\r${n}/${SEEDS.length} ${id} [${modelUsed}]        `);
}
console.log();

await writeFile(OUT, JSON.stringify({ formula_ref: "formula.json", created: "2026-07-30", items }, null, 2) + "\n");
console.log(`wave written: ${OUT} — ${items.length} items (${report.pass} pass, ${report.fail.length} fail)`);
if (report.fail.length) console.log("LINT FAILURES:", JSON.stringify(report.fail, null, 2));
