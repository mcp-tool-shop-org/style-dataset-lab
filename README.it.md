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

Trasformare i contenuti visivi approvati in set di dati versionati, supportati da revisioni, suddivisioni, pacchetti di esportazione e pacchetti di valutazione.

## Di cosa si tratta

Una **pipeline per la creazione di un canone visivo e di set di dati**. Definisci l'aspetto del tuo progetto. Seleziona i contenuti in base alle regole definite. Crea pacchetti di set di dati riproducibili con suddivisioni sicure da "data leakage". Genera pacchetti di valutazione per la verifica futura dei modelli.

La pipeline produce quattro elementi:

| Elemento | Descrizione |
|----------|-----------|
| **Snapshot** | Selezione di record idonei, "congelata" e con "impronta digitale". Ogni inclusione ha una traccia esplicita della motivazione. |
| **Split** | Partizione train/val/test sicura da "data leakage". I record che condividono la stessa famiglia di soggetti vengono sempre inseriti nella stessa partizione. |
| **Export package** | Set di dati autonomo: manifest, metadati, immagini, suddivisioni, scheda del set di dati e checksum. |
| **Eval pack** | Compiti di verifica attenti al canone: copertura delle aree, prevenzione di derive indesiderate, ancoraggi/riferimenti, coerenza dei soggetti. |

Ogni risorsa all'interno della pipeline contiene tre elementi:

1. **Provenienza** -- cronologia completa della generazione (checkpoint, LoRA, seed, sampler, cfg, timing)
2. **Vincolo al canone** -- quali regole del canone questa risorsa soddisfa, non soddisfa o soddisfa parzialmente
3. **Valutazione della qualità** -- approvato/rifiutato/al limite, con punteggi per ogni dimensione.

Adatto per arte di videogiochi, progettazione di personaggi, progettazione di creature, architettura, concept di veicoli/meccanismi e qualsiasi dominio in cui la produzione visiva deve rimanere coerente.

## Guida rapida

```bash
# Install the CLI + pipeline
npm install -g @mcptoolshop/style-dataset-lab

# Scaffold a new project
sdlab init my-project --domain character-design

# Validate the project structure
sdlab project doctor --project my-project
```

Domini disponibili: `game-art`, `character-design`, `creature-design`, `architecture`, `vehicle-mech` o `generic`.

## Interfaccia a riga di comando (CLI)

```bash
sdlab init <name> [--domain <domain>]     # Scaffold a new project
sdlab project doctor [--project <name>]   # Validate project config

sdlab generate <pack> [--project <name>]  # Generate candidates via ComfyUI
sdlab generate:identity <packet>          # Named-subject identity images
sdlab generate:controlnet                 # ControlNet-guided generation
sdlab generate:ipadapter                  # IP-Adapter reference-guided

sdlab curate <id> <status> <explanation>  # Record review judgment
sdlab compare <a> <b> <winner> <reason>   # Pairwise A-vs-B comparison
sdlab bind [--project <name>]             # Bind records to constitution rules
sdlab painterly [--project <name>]        # Post-processing style pass

sdlab snapshot create [--profile <name>]  # Create frozen dataset snapshot
sdlab snapshot list                       # List all snapshots
sdlab snapshot diff <a> <b>               # Compare two snapshots
sdlab eligibility audit                   # Audit record training eligibility
sdlab split build [--snapshot <id>]       # Build train/val/test split
sdlab split audit <id>                    # Audit split for leakage + balance
sdlab card generate                       # Generate dataset card (md + JSON)
sdlab export build [--snapshot <id>]      # Build versioned export package
sdlab eval-pack build                     # Build canon-aware eval pack
```

Tutti i comandi accettano `--project <nome>` (predefinito: `star-freight`).

## Modello del progetto

Ogni progetto è una directory autonoma all'interno di `projects/`, con il proprio canone, configurazione e dati.

```
projects/
  my-project/
    project.json            Project identity + generation defaults
    constitution.json       Rules array with rationale templates
    lanes.json              Subject lanes with detection patterns
    rubric.json             Scoring dimensions + thresholds
    terminology.json        Group vocabulary + detection order
    canon/                  Style constitution (markdown)
    records/                Per-asset JSON (provenance + judgment + canon)
    inputs/prompts/         Prompt packs (JSON)
    outputs/                Generated images (gitignored)
    comparisons/            A-vs-B preference judgments
    snapshots/              Frozen dataset snapshots
    splits/                 Train/val/test partitions
    exports/                Versioned export packages
    eval-packs/             Canon-aware eval instruments
```

## Pipeline

```
canon → generate → curate → bind → snapshot → split → export → eval
  |        |          |        |        |         |        |       |
rules   ComfyUI   judgment  rules   frozen    subject  package  verify
                                    selection isolation
```

1. **Definisci il canone** -- scrivi la tua costituzione dello stile e la griglia di valutazione.
2. **Genera** -- ComfyUI produce candidati con piena provenienza.
3. **Seleziona** -- approva/rifiuta con punteggi per ogni dimensione e modalità di errore.
4. **Collega** -- associa ogni risorsa alle regole del canone con verdetto di successo/fallimento/parziale.
5. **Snapshot** -- "congela" i record idonei in una selezione deterministica e con "impronta digitale".
6. **Suddividi** -- partiziona in train/val/test con isolamento dei soggetti e bilanciamento delle aree.
7. **Esporta** -- crea un pacchetto autonomo con manifest, metadati, immagini e checksum.
8. **Valuta** -- genera strumenti di test attenti al canone per la verifica del modello.

La conversione in formati specifici (TRL, LLaVA, Parquet, ecc.) è gestita da [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset). `sdlab` definisce la "verità" del set di dati; `repo-dataset` la trasforma in formati specializzati.

## Modelli per dominio

Ogni modello per dominio include definizioni di aree, regole del canone, griglie di valutazione e strutture terminologiche progettate per quel contesto di produzione:

| Dominio | Aree | Aspetti chiave |
|--------|-------|-------------|
| **game-art** | personaggio, ambiente, oggetto, interfaccia utente, nave, interno, equipaggiamento | Silhouette in scala di gioco, differenziazione delle fazioni, usura/invecchiamento |
| **character-design** | ritratto, figura intera, vista a 360°, foglio di espressioni, posa d'azione | accuratezza delle proporzioni, logica dell'abbigliamento, interpretazione della personalità, chiarezza dei gesti |
| **creature-design** | concept, proiezione ortogonale, studio dei dettagli, azione, riferimento di scala, habitat | plausibilità anatomica, logica evolutiva, distinzione della silhouette |
| **architecture** | esterno, interno, paesaggio urbano, dettaglio strutturale, rovina, paesaggio | plausibilità strutturale, coerenza dei materiali, prospettiva, coerenza dell'epoca |
| **vehicle-mech** | esterno, cabina di pilotaggio, componente, schema, foglio di silhouette, variante danneggiata | Logica meccanica, linguaggio di progettazione funzionale, punti di accesso, descrizione dei danni. |

## Produzione del dataset

La struttura completa del dataset: istantanea, suddivisione, esportazione, valutazione.

```
snapshot  -->  split  -->  export  -->  eval-pack
   |            |            |             |
  frozen     subject      package       canon-aware
  selection  isolation    (manifest,    test instruments
             + lane       metadata,     (4 task types)
             balance      images,
                          checksums,
                          card)
```

Le **istantanee** congelano una selezione deterministica di record idonei. Ogni inclusione ha una traccia della motivazione. Le "impronte" di configurazione garantiscono la riproducibilità.

Le **suddivisioni** assegnano i record alle partizioni di training/validazione/test, con isolamento dei soggetti (nessuna famiglia di soggetti compare in più suddivisioni) e distribuzione bilanciata per "corsia". Un generatore di numeri pseudo-casuali (PRNG) con seme garantisce risultati identici a partire dallo stesso seme.

I **pacchetti di esportazione** sono autonomi: manifest, metadata.jsonl, immagini (collegate simbolicamente o copiate), suddivisioni, scheda del dataset (markdown + JSON) e checksum in formato BSD. Tutto il necessario per ricostruire il dataset da zero.

I **pacchetti di valutazione** sono strumenti di test standardizzati, con quattro tipi di attività: copertura delle "corsie", deriva proibita, ancoraggi/riferimenti e continuità dei soggetti. Dimostrano che la struttura del dataset alimenta la valutazione futura dei modelli, e non solo l'accumulo di file.

Esportazione in formati compatibili con sistemi esterni tramite [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) (TRL, LLaVA, Qwen2-VL, JSONL, Parquet, e altri). `repo-dataset` gestisce la conversione dei formati; `sdlab` garantisce l'integrità del dataset.

## Esempio di Star Freight

Clonare il repository per un esempio funzionante completo: 1.182 record, 28 "onde" di prompt, 5 fazioni, 7 "corsie", 24 regole costituzionali e 892 risorse approvate provenienti da un RPG fantascientifico.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab

# Validate the project
sdlab project doctor --project star-freight

# Run the full dataset spine
sdlab snapshot create --project star-freight    # 839 eligible records
sdlab split build --project star-freight        # ~80/10/10, zero leakage
sdlab export build --project star-freight       # package with checksums
sdlab eval-pack build --project star-freight    # 78 eval records
```

## Migrazione dalla versione 1.x

La versione 2.0 rinomina `games/` in `projects/` e `--game` in `--project`:

```bash
# Rename your data directory
mv games projects

# --game still works with a deprecation warning (removed in v3.0)
sdlab bind --game star-freight   # works, prints warning
sdlab bind --project star-freight # canonical form
```

## Modello di sicurezza

**Solo locale.** Comunica con ComfyUI su `localhost:8188`. Nessuna telemetria, nessuna analisi, nessuna richiesta esterna. Le immagini rimangono sulla tua GPU e nel tuo filesystem.

## Requisiti

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) in esecuzione su localhost:8188
- Checkpoint DreamShaper XL Turbo + LoRA ClassipeintXL
- Node.js 20+
- [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) per l'esportazione dei dati per l'addestramento.

## Licenza

MIT

---

Creato da <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
