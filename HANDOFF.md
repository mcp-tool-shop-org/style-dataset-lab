# Session Handoff — 2026-04-13 (Universe Expansion + Painterly Pass)

## What Happened This Session

Expanded the Star Freight universe with new species, customs, stations, and visual identities. Then ran the full 887-image painterly post-processing pass.

### Deliverables

1. **SPECIES_CANON.md v0.2** — 12 new customs for core aliens (Keth molting/hive-song/pheromone libraries/seasonal debt, Veshan forge-trials/scale-reading/cold-debt/battle-opera, Orryn drift parliament/crystal inheritance/dark trade/tentacle autonomy). 3 minor species (Thresh silicon filter-feeders, Mire colonial aggregates, Vaelk gaseous proxy-traders). Extinct Architects. Station fauna (void lice, drift kelp, faction vermin). Cross-species trade protocols (pidgin trade-sign, station protocols, smuggler cant).

2. **VISUAL_BIBLE.md v0.3** — Added anatomy specs for Thresh, Mire, Vaelk proxy. Architect ruins visual language. Drift kelp spec.

3. **STATION_BIBLE.md v0.1** — 9 stations with full visual identity (thesis, architecture, lighting, sound, smell, commerce infrastructure, wear patterns, key landmarks). New station: Burn Gate (Veshan border toll — needs code implementation).

4. **Wave 25** (expanded universe) — 60 images, 48 approved / 12 rejected
5. **Wave 25b** (species regen) — 18 images, fixed SDXL human-default with negative prompt trick
6. **Wave 26** (station identities) — 46 images, 23 subjects × 2 variations
7. **Painterly post-processing pass** — 887 approved images through img2img at denoise 0.5, ClassipeintXL LoRA 1.0

### Key Discovery: Alien Negative Prompt

SDXL defaults all figures to human anatomy. Adding `human, person, man, woman` to the negative prompt + frontloading species anatomy in the prompt text solved this immediately. This is the single biggest lever for non-human species accuracy.

### Key Discovery: Painterly Denoise Sweet Spot

- **0.38** — barely visible difference (too subtle)
- **0.50** — visible brushwork, composition preserved, content intact (sweet spot)
- **0.60** — faces change, phantom figures appear (too much)
- **0.70** — completely different image (content destroyed)

---

## Current State

```
887 approved originals + 124 new candidates (waves 25/25b/26)
887 painterly versions (in progress, ~9s/image)
18 visual categories across 26 waves
```

### Pipeline Architecture

```
Canon (species, factions, world lore)
  → Visual Style Bible (art rules, prompt fragments, validation checklist)
    → Style Dataset Lab (ComfyUI txt2img + painterly img2img + curation)
      → repo-dataset (training JSONL export)
        → Fine-tuned VLM (consistent style generation + judgment)
```

### Generation Setup

```yaml
# txt2img (base generation)
checkpoint: dreamshaperXL_v21TurboDPMSDE.safetensors
lora: classipeintxl_v21.safetensors (weight: 1.0)
resolution: 1024x1024
steps: 8, cfg: 2.0, sampler: dpmpp_sde, scheduler: karras

# img2img (painterly post-processing)
same checkpoint + lora at 1.0
denoise: 0.50, steps: 10, cfg: 2.5, seed: 42
prompt: "oil painting, visible brushstrokes, painterly concept art..."
negative: "photorealistic, photograph, 3d render, smooth CG..."
```

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/generate.js` | txt2img ComfyUI automation |
| `scripts/painterly.js` | img2img painterly post-processing |
| `scripts/painterly-test.js` | A/B test denoise levels |
| `scripts/curate.js` | Individual curation |
| `scripts/curate-wave25.js` | Bulk curation for wave 25 |
| `scripts/compare.js` | Pairwise A-vs-B preference |
| `scripts/bulk-curate-waves11-18.js` | Bulk curation waves 11-24 |
| `scripts/canon-bind.js` | Canon binding (25 rules) |
| `canon/constitution.md` | Style rules |
| `canon/species-canon.md` | Species cultural depth |
| `canon/review-rubric.md` | Curation protocol |

### Companion Files

| File | Purpose |
|------|---------|
| `F:/AI/star-freight-ue5/VISUAL_BIBLE.md` | v0.3 — design authority |
| `F:/AI/star-freight-ue5/SPECIES_CANON.md` | v0.2 — species/culture |
| `F:/AI/star-freight-ue5/STATION_BIBLE.md` | v0.1 — 9 stations |

---

## Commands

```bash
# Start ComfyUI
cd F:/AI-Models/ComfyUI-runtime && python main.py --listen 127.0.0.1 --port 8188

# Generate a wave
cd F:/AI/style-dataset-lab
node scripts/generate.js inputs/prompts/wave26-station-identities.json

# Painterly pass (auto-skips already processed)
node scripts/painterly.js --limit 100
node scripts/painterly.js --source outputs/candidates --limit 50

# Curate wave 25
node scripts/curate-wave25.js

# Canon bind all records
node scripts/canon-bind.js --force

# Export dataset
node F:/AI/repo-dataset/dist/cli.js visual generate . --format trl --output exports
```

---

## What's Next

1. **Painterly pass completion** — 887 images running
2. **Painterly the new waves** — run waves 25/25b/26 through painterly after curation
3. **Pairwise comparisons** — original vs painterly pairs for DPO preference data
4. **Export** — training JSONL with both original and painterly variants
5. **Blank pipeline template** — extract reusable starter kit from this workflow
6. **Crew character concepts** — 6 named crew as individuals
7. **Ship fleet sheets** — faction ship design language rendered

---

*The pipeline is now: canon informs bible, bible informs generation, generation produces training data, training data teaches the model to maintain the style. Each new game starts with a blank template and fills it in.*
