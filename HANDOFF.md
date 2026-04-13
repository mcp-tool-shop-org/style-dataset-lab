# Session Handoff — 2026-04-12

## What this repo is

A Comfy-backed visual dataset factory for manufacturing multimodal training data. Every asset carries three things: **image pixels + canonical explanation + quality judgment**. The output feeds into `repo-dataset` to produce training data for vision-language model fine-tuning.

Current lane: **Gritty Space** — uniforms and costumes for Star Freight's lived-in sci-fi universe.

## What happened this session

1. Scaffolded repo from scratch — scripts, canon, directory structure
2. First attempt with RPG item icons — **scrapped** (wrong direction entirely)
3. Pivoted to gritty space costumes grounded in Star Freight visual bible
4. Iterated on checkpoint (JuggernautXL → DreamShaper XL) and prompts (Earth clothes → sci-fi shipboard gear)
5. Downloaded DreamShaper XL Turbo + ClassipeintXL painterly LoRA
6. Generated 10 waves of candidates across 3 factions
7. Curated all 432 assets with judgment records
8. First export: 570 training units in TRL format

## Current state

- **Repo:** https://github.com/mcp-tool-shop-org/style-dataset-lab
- **Local:** F:/AI/style-dataset-lab
- **Assets:** 432 curated (345 approved, 71 rejected, 16 borderline)
- **Records:** 432 JSON files with provenance + judgment
- **Comparisons:** 6 human pairwise
- **Export:** 570 training units, 528MB image folder
- **All pushed.** Working tree clean.

---

## Generation setup

```yaml
checkpoint: dreamshaperXL_v21TurboDPMSDE.safetensors
lora: classipeintxl_v21.safetensors (weight: 1.0)
resolution: 1024x1024
steps: 8
cfg: 2.0
sampler: dpmpp_sde
scheduler: karras
comfyui: http://127.0.0.1:8188
```

**Start ComfyUI:** `cd F:/AI-Models/ComfyUI-runtime && python main.py --listen 127.0.0.1 --port 8188`

**Note:** Output is still photorealistic despite painterly LoRA. Post-processing painterly pass not yet implemented. The costume design is strong, the rendering style needs work.

---

## Dataset composition (10 waves)

| Wave | Focus | Subjects | Rejects |
|------|-------|----------|---------|
| Anchor | Style finding — 10 Compact crew roles | 10 | 0 |
| 1 | Compact + Veshan + Reach + traps | 28 | 8 |
| 2 | Compact diversity — ethnicities, body types, roles | 21 | 4 |
| 3 | Veshan deep — full rank + non-combat | 13 | 3 |
| 4 | Sable Reach deep — specialists + mixed species | 13 | 3 |
| 5 | Cross-faction comparisons | 15 | 3 |
| 6 | Compact civilians — station life, refugees, children | 15 | 3 |
| 7 | Veshan society — diplomat, priest, cook, mother | 10 | 2 |
| 8 | Reach specialists + borderline rejects | 8 | 7 |
| 9 | Iteration pairs + edge cases | 12 | 4 |
| 10 | Final push — more diversity + iteration pairs | 19 | 4 |

**Rejection categories:** generic sci-fi, too clean, wrong material vocabulary, Star Trek, anime, too heroic, mixed factions, modern Earth, cyberpunk, steampunk, fantasy knight, Warhammer, too sexy, cute dragon, Fortnite, samurai, pin-up, MMORPG, superhero, zombie, invisible, xenomorph.

**Borderline categories:** almost-right-Compact (too stylish), almost-right-Veshan (too ornate), almost-right-Reach (too coordinated), right-style-wrong-era, too-much-wear.

---

## What's next

### Quality improvements
1. **Canon binding pass** — populate `canon_assertions` in records by linking each asset to specific constitution rules. This will bring triangle completion from 0% to target >90%.
2. **More pairwise comparisons** — only 6 human comparisons. Need 50+ for meaningful DPO training. Use same-role cross-variation and cross-faction pairs.
3. **Painterly post-processing** — img2img pass through ComfyUI with stronger painterly style transfer to convert photorealistic renders to concept art.
4. **Human review override** — bulk curation used rule-based first pass at confidence 0.75. Individual visual review would raise confidence to 0.9+.

### Scale to 500
- Currently at 432. Need ~70 more for 500 target.
- Could add: Orryn (cephalopod) subjects, Keth (arthropod) with ControlNet, more civilian roles, more iteration pairs.

### Export improvements
- Run with `--embed` for self-contained base64 JSONL
- Try `llava`, `qwen2vl`, `llama_factory` formats
- Run `repo-dataset visual validate` on the export for health metrics

---

## Key files

| File | Purpose |
|------|---------|
| `canon/constitution.md` | Style rules — art pillars, material vocab, shape language, color rules |
| `canon/review-rubric.md` | Curation protocol + failure mode catalog |
| `inputs/prompts/wave*.json` | Prompt packs per wave (subjects, variations, defaults) |
| `scripts/generate.js` | ComfyUI HTTP API automation — generates + writes provenance |
| `scripts/curate.js` | Individual asset curation — approve/reject/borderline |
| `scripts/compare.js` | Pairwise A-vs-B preference recording |
| `scripts/bulk-curate-wave2-5.js` | Rules-based bulk curation for large batches |
| `records/*.json` | Per-asset structured records (provenance + judgment) |
| `comparisons/*.json` | A-vs-B preference judgments |
| `exports/_manifest.json` | Latest export metadata |

---

## Commands

```bash
# Generate candidates (ComfyUI must be running)
node scripts/generate.js inputs/prompts/wave1.json
node scripts/generate.js inputs/prompts/wave1.json --dry-run

# Curate individual assets
node scripts/curate.js <asset_id> approved "explanation" --scores "k:v,..."
node scripts/curate.js <asset_id> rejected "explanation" --failures "f1,f2"
node scripts/curate.js --list

# Record comparisons
node scripts/compare.js <asset_a> <asset_b> <a|b|tie> "reasoning"

# Export via repo-dataset (local build)
node F:/AI/repo-dataset/dist/cli.js visual generate . --format trl --output exports --allow-incomplete
node F:/AI/repo-dataset/dist/cli.js visual inspect .
node F:/AI/repo-dataset/dist/cli.js visual validate exports/dataset.jsonl
```
