<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.md">English</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/style-dataset-lab/readme.png" width="400">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@mcptoolshop/style-dataset-lab"><img src="https://img.shields.io/npm/v/@mcptoolshop/style-dataset-lab" alt="npm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

# style-dataset-lab

Strumento per la creazione di dataset visivi: genera, organizza ed esporta dati di training multimodali per l'affinamento di modelli di visione e linguaggio (VLM).

## Cos'è questo

Un toolkit per creare una "verità visiva" addestrabile. Ogni elemento contiene tre informazioni:

1. **Pixel dell'immagine** -- generati da ComfyUI con informazioni complete sulla provenienza (checkpoint, LoRA, seed, sampler, cfg).
2. **Spiegazione canonica** -- perché questo elemento è conforme o non conforme allo stile, basata su una "costituzione" dello stile.
3. **Valutazione della qualità** -- approvato/rifiutato con punteggi per ogni dimensione e regole citate.

L'output viene utilizzato da [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) per creare dati di training multimodali in 10 formati: TRL, LLaVA, Qwen2-VL, Axolotl, LLaMA-Factory, ShareGPT, coppie RLHF, DPO, didascalie e classificazione.

## Modello di sicurezza

**Solo locale.** style-dataset-lab comunica con ComfyUI su `localhost:8188` e non effettua richieste alla rete esterna. Nessuna telemetria, nessuna analisi, nessuna trasmissione di dati. La generazione delle immagini avviene interamente sulla tua GPU. I dati e le informazioni canoniche rimangono sul tuo filesystem.

## Statistiche del dataset

| Metrica | Valore |
|--------|-------|
| Elementi curati | 1,182 |
| Elementi totali | 2.571 (893 approvati, 887 varianti pittoriche) |
| Prompt utilizzati | 28 |
| Categorie visive | 18 (costumi, navi, interni, attrezzature, ambienti, specie, stazioni, segnaletica, illuminazione, carico, architettura, creature, superfici, vita quotidiana, pianeti, danni/riparazioni, biologia aliena, dettagli di ambienti vissuti) |
| Confronti a coppie | 6 creati da umani + 71 creati sinteticamente |
| Tipi di rifiuto distinti | 30+ |
| Sistema di "identity packet" | Personaggi nominati con DNA della fazione, grado e riferimenti visivi. |
| Formati di esportazione | 10 (tramite @mcptoolshop/repo-dataset) |

## Installazione

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Successivamente, clona un progetto o inizializza un nuovo spazio di lavoro per il dataset:

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab my-dataset
cd my-dataset
npm install
```

## Flusso di lavoro

```bash
# 1. Start ComfyUI
# (point it at your checkpoint + LoRA setup)

# 2. Generate candidates from a prompt pack
npm run generate -- inputs/prompts/wave1.json
npm run generate -- inputs/prompts/wave1.json --dry-run

# 3. Generate identity-packet characters
npm run generate:identity -- inputs/identity-packets/wave27a-identity-spine.json

# 4. Generate painterly variants of approved assets
npm run painterly -- <asset_id>

# 5. Curate -- approve, reject, or mark borderline
npm run curate -- <asset_id> approved "explanation" --scores "silhouette:0.9,palette:0.8"
npm run curate -- <asset_id> rejected "explanation" --failures "too_clean,wrong_material"

# 6. Bind canon explanations to assets
npm run canon-bind -- <asset_id>

# 7. Record pairwise comparisons
npm run compare -- <asset_a> <asset_b> a "A has better faction read because..."

# 8. Export training data via repo-dataset
npm run export
npm run inspect
npm run validate
```

## Struttura delle directory

```
canon/                  Style constitution, review rubric, identity gates, species canon
inputs/
  prompts/              Prompt packs per wave (JSON: subjects, variations, defaults)
  references/           IP-Adapter reference images
  control/              ControlNet control images
  control-guides/       ControlNet guide overlays
  identity-packets/     Named character identity spines (faction DNA, rank, visual anchors)
outputs/
  candidates/           Raw generations (gitignored)
  approved/             Curated approved (gitignored)
  rejected/             Curated rejected (gitignored)
  borderline/           Curated borderline (gitignored)
  painterly/            Painterly-style variants (gitignored)
records/                Per-asset JSON (provenance + judgment + canon binding)
comparisons/            A-vs-B preference judgments
exports/                repo-dataset output (gitignored)
scripts/                generate, curate, compare, canon-bind, painterly, identity gen
workflows/              Reusable ComfyUI workflow templates
```

## Configurazione della generazione

```yaml
checkpoint: dreamshaperXL_v21TurboDPMSDE.safetensors
lora: classipeintxl_v21.safetensors (weight: 1.0)
resolution: 1024x1024
steps: 8
cfg: 2.0
sampler: dpmpp_sde
scheduler: karras
speed: ~9s per image (RTX 5080)
```

Modalità di generazione aggiuntive: ControlNet (guidato da posa/profondità), IP-Adapter (guidato da riferimento) e "identity packets" (coerenza dei personaggi nominati).

## Requisiti

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) in esecuzione su localhost:8188
- Checkpoint DreamShaper XL Turbo + LoRA ClassipeintXL
- Node.js 20+
- [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) per l'esportazione dei dati di training

## Licenza

MIT

---

Creato da <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a
