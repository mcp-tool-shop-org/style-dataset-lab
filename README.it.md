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

Una pipeline per la creazione di dataset visivi, che parte da regole definite (canon), passa attraverso prompt strutturati, generazione con ComfyUI e arriva a dati di training curati e conformi alle regole stabilite.

## Di cosa si tratta

Una **pipeline** per la creazione di dataset visivi strutturati per l'addestramento. Si definiscono regole di stile (canon), si compongono prompt, si genera con ComfyUI, si effettua una selezione basata su criteri dimensionali, si collegano le valutazioni alle regole di stile e si esportano i dati in 10 formati tramite [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset).

La pipeline è indipendente dal gioco. Ogni gioco ha la propria directory di dati, situata in `games/<nome>/`; gli script e i modelli predefiniti sono condivisi. Ogni risorsa generata contiene tre elementi:

1. **Pixel dell'immagine** -- generati da ComfyUI con informazioni complete sulla provenienza (checkpoint, LoRA, seed, sampler, cfg).
2. **Spiegazione in base alle regole (canon)** -- motivazione per cui l'immagine è conforme o non conforme allo stile definito, basata su una costituzione di stile.
3. **Valutazione della qualità** -- approvata/rifiutata con punteggi dimensionali e regole citate.

## Modello di sicurezza

**Esclusivamente locale.** style-dataset-lab comunica con ComfyUI su `localhost:8188` e non effettua richieste a reti esterne. Nessuna telemetria, nessuna analisi, nessuna trasmissione di dati. La generazione delle immagini avviene interamente sulla vostra GPU. I dati e le informazioni relative alle regole rimangono sul vostro filesystem.

## Cosa include il pacchetto npm

`npm install @mcptoolshop/style-dataset-lab` fornisce:

- **13 script** -- per la generazione, la selezione, il confronto, l'associazione alle regole, la creazione di immagini pittoriche, la generazione di identità, la generazione con ControlNet/IP-Adapter, la selezione in blocco e la migrazione.
- **Modelli predefiniti** -- costituzione di base, griglia di valutazione e pacchetto di esempi di prompt, situati nella directory `templates/`.

Il pacchetto npm **non** include i dati del gioco. Clonate il repository se desiderate l'esempio di Star Freight (1.182 record, 28 sequenze di prompt, 18 categorie visive).

## Installazione

```bash
# Get the pipeline scripts + templates
npm install @mcptoolshop/style-dataset-lab

# Or clone the repo for the Star Freight example data
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
npm install
```

Per iniziare un nuovo gioco a partire dai modelli:

```bash
# Copy templates into your game directory
mkdir -p games/my-game/{records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
cp -r templates/canon games/my-game/canon
cp templates/inputs/prompts/example-wave.json games/my-game/inputs/prompts/wave1.json
# Edit the canon and prompts, then generate
```

## Struttura del monorepository

La pipeline si trova nelle directory `scripts/` e `templates/`. Ogni gioco si trova nella directory `games/<nome>/` e contiene le proprie regole, i dati e le risorse. Gli script accettano l'argomento `--game <nome>` (il valore predefinito è `star-freight`).

```
style-dataset-lab/
  scripts/                  13 pipeline scripts (generate, curate, compare, etc.)
  templates/                Blank starting point for new games
    canon/                  Starter constitution + review rubric
    inputs/prompts/         Example prompt pack
  games/
    star-freight/           Star Freight example (1,182 records, repo-only)
      canon/                Style constitution, review rubric, species canon
      records/              Per-asset JSON (provenance + judgment + canon)
      comparisons/          A-vs-B preference judgments
      inputs/               Prompt packs, identity packets, references
      outputs/              Generated images (gitignored)
      exports/              repo-dataset output (gitignored)
    <your-game>/            Add more games with the same structure
```

## Flusso di lavoro della pipeline

L'intero flusso di lavoro, dalle regole alla creazione dei dati per l'addestramento:

```bash
# 1. Write your canon -- style constitution + review rubric
#    (start from templates/ or write from scratch)

# 2. Create prompt packs in inputs/prompts/
#    (see templates/inputs/prompts/example-wave.json)

# 3. Start ComfyUI and generate candidates
npm run generate -- --game star-freight inputs/prompts/wave1.json
npm run generate -- --game star-freight inputs/prompts/wave1.json --dry-run

# 4. Generate identity-packet characters (named subjects)
npm run generate:identity -- --game star-freight inputs/identity-packets/wave27a.json

# 5. Curate -- approve, reject, or mark borderline
npm run curate -- --game star-freight <asset_id> approved "explanation"
npm run curate -- --game star-freight <asset_id> rejected "explanation" --failures "too_clean"

# 6. Generate painterly variants of approved assets
npm run painterly -- --game star-freight

# 7. Bind canon explanations to curated assets
npm run canon-bind -- --game star-freight

# 8. Record pairwise comparisons
npm run compare -- --game star-freight <asset_a> <asset_b> a "A has better faction read"

# 9. Export training data via repo-dataset
repo-dataset visual generate ./games/star-freight --format trl
repo-dataset visual inspect ./games/star-freight
```

## Aggiunta di un nuovo gioco

```bash
# Create structure and copy blank templates
mkdir -p games/my-game/{records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
cp -r templates/canon games/my-game/canon
cp templates/inputs/prompts/example-wave.json games/my-game/inputs/prompts/wave1.json

# Edit your canon/constitution.md and canon/review-rubric.md
# Edit your prompt pack, then run the pipeline with --game my-game
```

## Struttura della directory per ogni gioco

Ogni directory `games/<nome>/` contiene:

```
canon/                  Style constitution, review rubric, species canon, identity gates
inputs/
  prompts/              Prompt packs per wave (JSON: subjects, variations, defaults)
  references/           IP-Adapter reference images
  control-guides/       ControlNet guide overlays
  identity-packets/     Named character identity spines
outputs/
  candidates/           Raw generations (gitignored)
  approved/             Curated approved (gitignored)
  rejected/             Curated rejected (gitignored)
  borderline/           Curated borderline (gitignored)
  painterly/            Painterly-style variants (gitignored)
records/                Per-asset JSON (provenance + judgment + canon binding)
comparisons/            A-vs-B preference judgments
exports/                repo-dataset output (gitignored)
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

Modalità di generazione aggiuntive: ControlNet (guidata da pose/profondità), IP-Adapter (basata su riferimento) e pacchetti di identità (coerenza dei personaggi).

## Requisiti

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) in esecuzione su localhost:8188
- Checkpoint DreamShaper XL Turbo + LoRA ClassipeintXL
- Node.js 20+
- [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) per l'esportazione dei dati per l'addestramento.

## Licenza

MIT

---

Creato da <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
