#!/usr/bin/env node
// Ingest the salt-road style-set v1 candidates (generated on Comfy Cloud via
// explicit Qwen graphs, 2026-07-30) as sdlab records, so `sdlab curate` can
// judge them through the official flow. Emits records/<id>.json + a
// curate-plan.json the curation loop consumes. Idempotent: skips existing.
//
// Run: node projects/salt-road/inputs/prompts/ingest-styleset-records.mjs
import { writeFile, mkdir, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJ = join(HERE, "..", "..");
const IMG_DIR = "inbox/generated/set-v1-2026-07-30";

const PIN = {
  backend: "comfy-cloud explicit submit_workflow graph",
  unet: "qwen_image_2512_bf16.safetensors",
  clip: "qwen_2.5_vl_7b_fp8_scaled.safetensors",
  vae: "qwen_image_vae.safetensors",
  shift: 3.1, steps: 24, cfg: 3.5, sampler: "euler", scheduler: "simple",
  width: 1344, height: 768,
};

const STYLE = "Hand-painted 2D game environment art plate, painterly gouache texture with visible brushwork, restrained sixteen-bit palette discipline of about fifteen values per material family, flat readable silhouettes with crisp edges, oblique projection seen from slightly above with building fronts flat-on and parallel to the picture plane, minimal perspective recession, early-modern North European trading harbour, memory-bright color, dense detail concentrated in a few focal clusters with calm flat areas between";
const INTER = STYLE.replace("oblique projection seen from slightly above with building fronts flat-on and parallel to the picture plane, minimal perspective recession", "interior seen straight on from slightly above with minimal perspective recession");
const STUDY = STYLE.replace("oblique projection seen from slightly above with building fronts flat-on and parallel to the picture plane, minimal perspective recession", "close material study seen from slightly above with minimal perspective recession");
const SEA = "Hand-painted 2D game environment art plate, painterly gouache texture with visible brushwork, restrained sixteen-bit palette discipline of about fifteen values per material family, flat readable silhouettes with crisp edges, early-modern North European harbour seas, memory-bright color, quiet spare composition";
const CTL = "Hand-painted 2D game environment art plate, painterly gouache texture with visible brushwork, restrained palette of about fifteen values per material family, flat readable silhouettes with crisp edges, early-modern North European trading harbour, memory-bright color, dense detail concentrated in a few focal clusters with calm flat areas between";

const NEG_LAND = "anime, manga, cel shaded, chibi, fantasy, magic, dragons, glowing runes, wizards, pirate flag, skull and crossbones, tricorn hat, treasure chest, cutlass, grimdark, dystopian, ruined, neon signs, sodium vapor haze, cyberpunk, photograph, photorealistic, DSLR, glossy 3D render, CGI, octane render, vector art, flat design illustration, airbrushed smoothness, HD remaster, identical repeating facades, half-timbered facades, exposed timber framing, empty bare quay, modern buildings, cars, shipping containers, streetlights, power lines, text, watermark, logo, signature, people, faces, portrait";
const NEG_SEA = NEG_LAND.replace("identical repeating facades, half-timbered facades, exposed timber framing, empty bare quay", "buildings, rooftops, town, houses, half-timbered facades");
const NEG_CTL = NEG_LAND + ", pixel art, pixelated, dithering, 8-bit sprite, flat single-color background, isolated object on plain background, turquoise, teal";

// [id, file, seed, preamble, subject, negative, controlnet|null]
const CANDIDATES = [
  ["styleset_p01_quay_dawn", "p01_quay_dawn.png", 730101, STYLE, "the long stone quay at first light seen flat-on from across the water, cold pale eastern sky, row of tall narrow limewashed warehouse fronts in mismatched ochre and red-ochre batches, each front a slightly different faded tone with a faint chalky glow, facades leaning forward over the water, a timber hoist beam projecting from each gable peak just under the roof ridge with rope tackle, wet stone lip along the water darker and bluer than the dry pale upper stones, stacked casks branded with cooper marks, coiled hawsers, moored wooden boats, long cold shadows", NEG_LAND, null],
  ["styleset_p02_quay_noon", "p02_quay_noon.png", 730102, STYLE, "the long stone quay at working midday seen flat-on from across the water, clear high light, row of tall narrow limewashed warehouse fronts in mismatched ochre batches with patchy repainted sections, facades leaning forward, a timber hoist beam projecting from each gable peak with hanging tackle, oak loading doors open at several heights, crowded stacks of chalk-marked casks and canvas bales three deep, handcarts, coiled rope, stone ramps down to the water, short hard shadows under the beams", NEG_LAND, null],
  ["styleset_p03_quay_night", "p03_quay_night.png", 730103, STYLE, "the long stone quay at night seen flat-on from across the water, deep blue darkness with warm lantern glow, hanging iron lanterns and lit windows throwing warm pools of light on the leaning limewashed facades, hoist beams at the gable peaks silhouetted against the sky, wet stone lip catching faint reflections, marked casks stacked in shadow, a few windows amber, quiet water", NEG_LAND, null],
  ["styleset_p04v2_crane_tower", "p04v2_crane_tower.png", 730304, CTL, "a medieval harbour crane built as a building, two round masonry towers of oxide-red brick with a steep tiled roof between them, the great timber hoist jib slung from the crane house, heavy rope and tackle lowering a cask, small barred windows in the brick, stone base with bollards and coiled hawser, pale morning sky and calm grey-blue harbour water behind, the crane standing on its stone quay platform at the water's edge, low raking sunlight", NEG_CTL, { model: "Qwen-Image-2512-Fun-Controlnet-Union-2602.safetensors", type: "depth", strength: 0.6, end: 0.65, guide: "inputs/control-guides/p04-crane-tower/depth.png (Blender 5.2 blockout)" }],
  ["styleset_p05v2_crane_treadwheel", "p05v2_crane_treadwheel.png", 730305, CTL, "soft painted gouache texture throughout, closer view of the harbour crane, the open timber gallery between two brick towers showing the great treadwheel inside, thick oak axle, rope winding onto the drum, a cask slung mid-air from the hook over the quay edge, tarred timber posts and braces, pale sky and calm grey-blue harbour water beyond the gallery, warm afternoon light through the opening", NEG_CTL, { model: "Qwen-Image-2512-Fun-Controlnet-Union-2602.safetensors", type: "depth", strength: 0.6, end: 0.65, guide: "inputs/control-guides/p05-crane-treadwheel/depth.png" }],
  ["styleset_p06v2_warehouse_interior", "p06v2_warehouse_interior.png", 730206, INTER, "interior of a bonded warehouse, tarred black-brown timber posts and beams, a worn oak board ramp rising from the plank floor to an upper storage gallery loaded with sacks, stacked marked casks and canvas bales in ordered rows below, hemp sacking, shafts of dusty light from small high windows, dark pitch-coloured structure against warm ochre daylight", NEG_LAND, null],
  ["styleset_p07v2_bonded_door", "p07v2_bonded_door.png", 730307, CTL, "the sealed double door of a bonded warehouse seen straight on, heavy weathered oak boards with iron straps and a hanging red wax seal on a cord, the facade in patchwork limewash of mismatched warm ochre batches with a faint chalky glow, leaning forward, a heavy timber hoist beam seen end-on projecting overhead with a tackle block hanging beneath it, two shuttered windows above, worn stone threshold on a narrow cobbled quay lane, painted number plaque beside the door, warm side light", NEG_CTL, { model: "Qwen-Image-2512-Fun-Controlnet-Union-2602.safetensors", type: "depth", strength: 0.6, end: 0.65, guide: "inputs/control-guides/p07-bonded-door/depth.png" }],
  ["styleset_p08_cargo_casks", "p08_cargo_casks.png", 730108, STUDY, "still life study of marked wooden casks stacked three deep on quay stones, each cask branded and chalked with different mark systems, coopers marks burned into the heads, chalked tally strokes, painted ownership initials intertwined with crosses and simple line figures, iron hoops, oak staves in varied browns, coiled rope beside the stack, raking light", NEG_LAND, null],
  ["styleset_p09_cargo_bales", "p09_cargo_bales.png", 730109, STUDY, "still life study of canvas bales and wooden crates on a quay, off-white sailcloth wrapping tied with hemp cord, large painted merchant marks on the cloth, crosses and intertwined initials in dark pigment, a wooden crate stencilled with a simple line figure, tackle block and hook resting on top, hemp netting, warm side light", NEG_LAND, null],
  ["styleset_p10_weighing_floor", "p10_weighing_floor.png", 730110, INTER, "interior of the public weighing floor, six great brass beam scales hanging in a row from heavy roof timbers, chains and hooks, flat iron weights stacked on the flagstone floor, casks and sacks waiting in a queue line by the door, tarred roof trusses above, daylight from tall doorway falling across the flags", NEG_LAND, null],
  ["styleset_p11v2_beam_scale", "p11v2_beam_scale.png", 730211, INTER, "close study of a great equal-arm beam scale hung from a dark roof timber, a slender iron beam with a brass fitting at its centre, hanging chains on both sides, a shallow brass pan suspended on one side and an iron hook gripping a small marked cask on the other, stacked ring weights on the flagstones below, the brass warm against dark tarred wood, dust in a shaft of light", NEG_LAND + ", cannon, telescope, giant cylinder", null],
  ["styleset_p12_counting_house", "p12_counting_house.png", 730112, INTER, "interior of a counting house, a tall standing desk of dark oak with an open ledger, a burned-down wax jack and seal beside the inkwell, pigeonhole shelves stuffed with folded papers, a leaded window looking out on masts and water, warm afternoon light on the desk, worn floorboards", NEG_LAND, null],
  ["styleset_p13_customs_shed", "p13_customs_shed.png", 730113, INTER, "interior of the customs shed, a broad inspection counter with a heavy iron stamp and a wooden tally board with pegs, casks lined up each carrying chalked inspection marks, a clerk's stool, ledger books, one door open to the bright quay beyond, cool interior shadow against warm exterior light", NEG_LAND, null],
  ["styleset_p14v2_crooked_stair", "p14v2_crooked_stair.png", 730314, CTL, "a narrow crooked stone stair descending between two leaning buildings, rough stone masonry walls with patched flaking limewash, twenty-two steps no two the same height, every tread a separate worn stone block with a hollow worn centre, moss in the shaded joints, an iron handrail stub, a sliver of grey-blue harbour water at the bottom of the passage, strong raking side light across the steps, cool shade with warm light at the top", NEG_CTL, { model: "Qwen-Image-2512-Fun-Controlnet-Union-2602.safetensors", type: "depth", strength: 0.5, end: 0.6, guide: "inputs/control-guides/p14-crooked-stair/depth.png" }],
  ["styleset_p15_stone_study", "p15_stone_study.png", 730115, STUDY, "close study of the quay surface, worn stone setts with deep parallel cart ruts, a cast iron bollard with rope-polished shoulders and rust stains at its base, the wet lip stones near the water in a cooler bluer ramp than the dry pale stones above, scattered straw, a frayed rope end, strong raking light showing every hollow", NEG_LAND, null],
  ["styleset_p16v2_hull_brig", "p16v2_hull_brig.png", 730316, CTL, "a two-masted wooden brig moored broadside at the quay, dark tarred hull with a pale painted sheer line, sails loosed to dry on the square yards, standing rigging in hemp, mooring hawsers to stone bollards along the quay edge, the deck cluttered with casks and coiled line, pale morning sky, calm grey-blue harbour water with soft reflections, a low distant shoreline behind the masts, warm light on the masts and canvas", NEG_CTL, { model: "Qwen-Image-2512-Fun-Controlnet-Union-2602.safetensors", type: "depth", strength: 0.75, end: 0.65, guide: "inputs/control-guides/p16-hull-brig/depth.png (portlight brig-normalised GLB blockout)" }],
  ["styleset_p17v2_hull_caravel", "p17v2_hull_caravel.png", 730317, CTL, "a small caravel moored at the quay seen from its quarter, rounded oak hull with visible strakes, tall lateen sail set and marked with a painted merchant cross, deck rigging visible, stone bollards along the quay edge below, pale morning sky, calm grey-blue harbour water with soft reflections behind the hull, morning light on the canvas", NEG_CTL, { model: "Qwen-Image-2512-Fun-Controlnet-Union-2602.safetensors", type: "depth", strength: 0.75, end: 0.65, guide: "inputs/control-guides/p17-hull-caravel/depth.png (portlight caravel-normalised GLB blockout)" }],
  ["styleset_p18_sea_open", "p18_sea_open.png", 730118, SEA, "open harbour water at midday, nothing but water and sky, cool grey-blue sea rendered deliberately plain and calm, wide water with a low horizon, one small distant single-masted sailing boat, restrained flat wave pattern", NEG_SEA, null],
  ["styleset_p19v2_sea_chart", "p19v2_sea_chart_cropped.png", 730219, SEA, "flat top-down view of open sea as a map layer, deliberately plain cool slate grey-blue northern water in two or three flat muted tones, restrained repeating wave marks, a small wooden ship seen from above with a white wake line, the plainness deliberate and calm like an old chart brought to life", NEG_SEA + ", turquoise, teal, tropical water, coral", null, "cropped 285,70 780x620 from p19v2_sea_chart.png to remove the painted chart border the model added"],
  ["styleset_p20_shore_vs_sea", "p20_shore_vs_sea.png", 730120, STYLE, "the harbour mouth where the warm cluttered shore meets the cool empty sea, on one side the dense ochre quay with leaning facades, casks and moored boats in warm crowded detail, on the other side wide plain cool grey-blue water stretching empty to the horizon, the contrast between dense warm land and spare cool sea carrying the whole image", NEG_LAND, null],
];

// Superseded / register-failed versions — recorded then curated rejected.
// [id, file, seed, note, failures]
const REJECTS = [
  ["styleset_p04_crane_tower_v1", "p04_crane_tower.png", 730104, "depth-lock v1: crane geometry locked but painted as isolated asset on flat beige card (control far-black => void); superseded by p04v2", "flat_void_background,asset_card_register"],
  ["styleset_p05_crane_treadwheel_v1", "p05_crane_treadwheel.png", 730105, "depth-lock v1: collapsed into literal pixel-art register (sixteen-bit phrase + sparse scene text under ControlNet); superseded by p05v2", "pixel_art_register,teal_water"],
  ["styleset_p07_bonded_door_v1", "p07_bonded_door.png", 730107, "depth-lock v1: wax seal + beam good but olive void flanks and flat clean wall (law-1 weak); superseded by p07v2", "flat_void_background,limewash_flat"],
  ["styleset_p14_crooked_stair_v1", "p14_crooked_stair.png", 730114, "depth-lock v1: airbrushed mush, treads indistinct, no stone texture; superseded by p14v2", "airbrushed_mush,detail_loss"],
  ["styleset_p16_hull_brig_v1", "p16_hull_brig.png", 730116, "depth-lock v1: brig anatomy held but flat-design register with teal banded sea; superseded by p16v2", "flat_design_register,teal_water"],
  ["styleset_p16_hull_brig_canny_v1", "p16_hull_brig_canny.png", 730126, "canny variant: lovely painterly ship floating on blank cream page (canny empty zones); canny lane dropped", "void_background"],
  ["styleset_p17_hull_caravel_v1", "p17_hull_caravel.png", 730117, "depth-lock v1: full flat-vector register (contract S5 forbids); superseded by p17v2", "flat_design_register,teal_water"],
  ["styleset_p17_hull_caravel_canny_v1", "p17_hull_caravel_canny.png", 730127, "canny variant: literal pixel art + anatomy drift toward carrack; canny lane dropped", "pixel_art_register,anatomy_drift"],
  ["styleset_p06_warehouse_interior_v1", "p06_warehouse_interior.png", 730106, "txt2img v1: material/light excellent but the central ramp dead-ends into the back wall; superseded by p06v2", "implausible_architecture"],
  ["styleset_p11_beam_scale_v1", "p11_beam_scale.png", 730111, "txt2img v1: 'long polished beam' literalized as a giant brass cylinder, no balance anatomy; superseded by p11v2", "wrong_object"],
  ["styleset_p19_sea_chart_v1", "p19_sea_chart.png", 730119, "txt2img v1: composition right but turquoise-tropical hue violates the contract cool-slate sea ramp; superseded by p19v2 (cropped)", "off_palette_sea"],
  ["styleset_p19v2_sea_chart_uncropped", "p19v2_sea_chart.png", 730219, "v2 source image: hue correct but the model painted a literal chart border/frame; the cropped variant is the candidate", "border_frame"],
];

function record(id, file, seed, positive, negative, cn, extraNote) {
  return {
    id,
    schema_version: "2.0.0",
    created_at: new Date().toISOString(),
    asset_path: `${IMG_DIR}/${file}`,
    image: { format: "png", width: PIN.width, height: PIN.height, bytes: 0 },
    provenance: {
      source: "generated-qwen-cloud",
      wave: "salt-road-style-set-v1",
      base: "qwen-image-2512",
      backend: PIN.backend,
      prompt: positive,
      negative_prompt: negative,
      seed,
      steps: PIN.steps, cfg: PIN.cfg, sampler: PIN.sampler, scheduler: PIN.scheduler, shift: PIN.shift,
      width: PIN.width, height: PIN.height,
      unet: PIN.unet, clip: PIN.clip, vae: PIN.vae,
      style_prefix: "saltroad (trigger reserved — LoRA not yet trained; plates are the training set)",
      loras: [],
      controlnet: cn || null,
      gpu_model: "Comfy Cloud RTX 6000",
      run_manifest: "inputs/prompts/style-set-v1-manifest.json",
      note: extraNote || null,
    },
    judgment: null,
    canon: null,
    tags: ["style-set-v1", "environment", "salt-road"],
  };
}

const recDir = join(PROJ, "records");
await mkdir(recDir, { recursive: true });
const plan = [];
let written = 0, skipped = 0;

for (const [id, file, seed, pre, subj, neg, cn, note] of CANDIDATES) {
  const rp = join(recDir, `${id}.json`);
  const imgAbs = join(PROJ, IMG_DIR, file);
  if (!existsSync(imgAbs)) { console.error(`MISSING IMAGE: ${file}`); continue; }
  const r = record(id, file, seed, `${pre}, ${subj}`, neg, cn, note);
  r.image.bytes = (await stat(imgAbs)).size;
  if (existsSync(rp)) { skipped++; } else { await writeFile(rp, JSON.stringify(r, null, 2) + "\n"); written++; }
  plan.push({ id, status: "borderline" });
}
for (const [id, file, seed, note, failures] of REJECTS) {
  const rp = join(recDir, `${id}.json`);
  const imgAbs = join(PROJ, IMG_DIR, file);
  if (!existsSync(imgAbs)) { console.error(`MISSING IMAGE: ${file}`); continue; }
  const r = record(id, file, seed, `(v1 — exact prompt in run manifest: ${note})`, "(see manifest)", null, note);
  r.image.bytes = (await stat(imgAbs)).size;
  if (existsSync(rp)) { skipped++; } else { await writeFile(rp, JSON.stringify(r, null, 2) + "\n"); written++; }
  plan.push({ id, status: "rejected", failures });
}

await writeFile(join(HERE, "curate-plan.json"), JSON.stringify(plan, null, 2) + "\n");
console.log(`records written: ${written}, skipped(existing): ${skipped}, plan entries: ${plan.length}`);
