<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.md">English</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/style-dataset-lab/readme.png" width="400">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@mcptoolshop/style-dataset-lab"><img src="https://img.shields.io/npm/v/@mcptoolshop/style-dataset-lab" alt="npm"></a>
  <a href="https://github.com/mcp-tool-shop-org/style-dataset-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/style-dataset-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://codecov.io/gh/mcp-tool-shop-org/style-dataset-lab"><img src="https://codecov.io/gh/mcp-tool-shop-org/style-dataset-lab/branch/main/graph/badge.svg" alt="codecov"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

Scrivi le tue regole visive. Genera immagini. Valuta ogni immagine in base a tali regole. Pubblica i risultati come dati di addestramento verificabili e versionati, quindi utilizza i modelli addestrati in flussi di lavoro di produzione reali e reintroduci gli output migliori nel tuo corpus.

Style Dataset Lab collega le indicazioni che hai fornito sullo stile artistico al set di dati da cui effettivamente esegui l'addestramento, quindi completa il ciclo fino alla fase di produzione. Definisci una serie di regole: regole sulla silhouette, vincoli sulla palette, linguaggio dei materiali o qualsiasi altro elemento rilevante per il tuo progetto. Il flusso di lavoro genera candidati, li valuta in base alle regole e raggruppa gli elementi approvati in set di dati riproducibili, dove ogni record spiega perché è stato incluso.

Successivamente, l'ambiente di lavoro di produzione prende il sopravvento: compila le specifiche per la generazione a partire dai dati del progetto, eseguile tramite ComfyUI, valuta gli output, genera in batch fogli di espressione e schede ambientali, seleziona i risultati migliori e reintroducili come nuovi candidati. Il ciclo si chiude: produci, seleziona, rivedi, rafforza.

## Il flusso di lavoro

```bash
# Write your canon. Scaffold the project.
sdlab init my-project --domain character-design

# Generate candidates via ComfyUI, then review them
sdlab generate inputs/prompts/wave1.json --project my-project
sdlab sheet outputs/candidates --project my-project   # HTML contact sheet to triage
sdlab curate <id> approved "Strong silhouette, correct faction palette"

# Already have images? Bring them in without generating anything
sdlab ingest ~/renders/wave1 --project my-project

# Measure what the pixels actually are — palette and texture, as numbers
sdlab measure outputs/candidates --project my-project

# Bind approved work to constitution rules
# (`sdlab bind` is a shorter alias for `canon-bind`)
sdlab canon-bind --project my-project

# Freeze a versioned dataset
sdlab snapshot create --project my-project
sdlab split build
sdlab export build

# Build a training package
sdlab training-manifest create --profile character-style-lora
sdlab training-package build

# Compile a production brief and run it
sdlab brief compile --workflow character-portrait-set --subject kael_maren
sdlab run generate --brief brief_2026-04-16_001

# Critique, refine, batch-produce
sdlab critique --run run_2026-04-16_001
sdlab refine --run run_2026-04-16_001 --pick 001.png
sdlab batch generate --mode expression-sheet --subject kael_maren

# Select the best outputs and bring them back
sdlab select --run run_2026-04-16_001 --approve 001.png,003.png
sdlab reingest selected --selection selection_2026-04-16_001
```

Quest'ultimo comando è il punto cruciale. Gli output selezionati vengono reintrodotti nello stesso processo di revisione insieme a tutti gli altri elementi. Il corpus si espande e le regole rimangono valide.

## Definizione del canone

Before the dataset pipeline runs, the `sdlab canon *` namespace turns your project's canon entity store into the three projections training and production actually consume — and locks the entries that must not drift.

```bash
# Build three projections from the canon entity store:
#   dataset.jsonl  → training adapters
#   prompts/*.j2   → ComfyUI workflow invocation
#   context/*.md   → Role OS narrative dispatch
sdlab canon build --project my-project

# Freeze an entry so regeneration can't silently change it
sdlab canon freeze kael_maren --project my-project --reason "prologue portrait locked"

# Report drift on frozen entries since the last clean build
sdlab canon drift --project my-project
```

`canon build` è basato sull'indirizzamento dei contenuti: il suo output è identificato da un `canon_sha` e memorizzato nella cache, quindi una versione invariata del set di dati viene ricostruita istantaneamente. `canon freeze` registra ogni "freeze" rispetto a una specifica build e lo aggiunge a un registro di controllo `freeze-events.jsonl`: le voci `frozen` rifiutano esplicitamente la rigenerazione, le voci `soft-advisory` rifiutano per impostazione predefinita (è possibile aggirare questa limitazione con `--i-know`). `canon drift` ricalcola l'hash di ogni voce monitorata e segnala qualsiasi elemento che è stato modificato rispetto all'ultima build pulita.

Flusso di lavoro completo nel manuale: [Canon build](handbook/canon-build/), [Canon freeze](handbook/canon-freeze/) e [Two-LoRA stacking](handbook/two-lora-stacking/).

## Cosa produce

Sette artefatti del set di dati e un ambiente di lavoro di produzione completo. Ogni artefatto è collegato ai suoi predecessori, in modo da poter risalire a qualsiasi record di addestramento fino alla regola che lo ha approvato.

| Artefatto | Cos'è |
|----------|-----------|
| **Snapshot** | Selezione di record congelati con impronta di configurazione. Ogni inclusione ha una motivazione esplicita. |
| **Split** | Partizione train/val/test in cui le famiglie di soggetti non superano i confini. |
| **Export package** | Set di dati autonomo: manifesto, metadati, immagini, suddivisioni, scheda del set di dati, checksum. |
| **Eval pack** | Attività di test consapevoli del canone: copertura delle corsie, divieto di modifiche, ancoraggio/oro, continuità dei soggetti. |
| **Training package** | Layout pronto per l'addestramento tramite adattatori (`diffusers-lora`, `generic-image-caption`). La stessa base, formato diverso. |
| **Eval scorecard** | Valutazione per attività con esito positivo/negativo basata sulla valutazione degli output generati rispetto ai pacchetti di valutazione. |
| **Implementation pack** | Esempi di prompt, errori noti, test di continuità e indicazioni per la reintroduzione. |

L'ambiente di lavoro di produzione aggiunge:

| Superficie | Cosa fa |
|---------|-------------|
| **Compiled brief** | Istruzioni di generazione deterministiche dal profilo del flusso di lavoro + dati del progetto. |
| **Run** | Artefatto di esecuzione congelato: breve descrizione + seed + output ComfyUI + manifesto. |
| **Critique** | Valutazione strutturata multidimensionale degli output rispetto al canone. |
| **Batch** | Produzione coordinata multi-slot (fogli di espressione, schede ambientali, pacchetti di silhouette). |
| **Selection** | Artefatto decisionale creativo: quali output sono stati scelti, perché e da dove provengono. |
| **Re-ingest** | Gli output selezionati vengono reintrodotti come record candidati con la cronologia completa della generazione. |

## Perché esiste

I dati di addestramento sono l'artefatto più importante in qualsiasi flusso di lavoro di intelligenza artificiale visiva. Ma la maggior parte dei dati di addestramento è una cartella di immagini senza cronologia, senza traccia delle valutazioni e senza collegamento con le regole di stile che avrebbero dovuto seguire.

Style Dataset Lab rende esplicita questa connessione. La tua costituzione definisce le regole. La tua rubrica definisce le dimensioni della valutazione. I tuoi record di curatela registrano la valutazione. Il tuo legame con il canone dimostra la connessione. E il tuo set di dati conserva tutto questo come informazioni strutturate, ricercabili e riproducibili.

Il risultato pratico: quando il tuo LoRA subisce modifiche indesiderate, puoi chiedere *perché*. Quando il tuo prossimo ciclo di addestramento richiede dati migliori, sai esattamente quali record sono quasi corretti e quale singola regola hanno violato. Quando un nuovo membro del team chiede qual è il linguaggio visivo del progetto, la risposta non è una bacheca Figma, ma una costituzione ricercabile con 1.182 esempi valutati.

## Testato in produzione

Questo non è un ambiente di test. Due reali modelli LoRA sono stati utilizzati per intero: lo stesso ciclo canonico → curatela → addestramento → distribuzione, agli estremi opposti dello spettro della curatela.

- **[Tallow Fen](handbook/case-study-tallow-fen/)** (progettazione di creature): un set di dati canonico creato da zero, con circa il 34% di approvazioni su 293 record curati (169 rifiutati: il filtro è rigoroso). Distribuito `tallow_fen_style_v3.safetensors` @ 1.5 su `qwen-image`.
- **[Rustline](handbook/case-study-rustline/)** (progettazione concettuale): un set di dati canonico denso e preformato, con circa il 96% di approvazioni su 180 record. Distribuito `rustline_v3ckpt_1500.safetensors` @ 1.0 su `qwen-image`, riutilizzato a valle da un secondo progetto.

Lo stesso flusso di lavoro, due profili di produzione: il filtro di curatela è reale (rifiuta in modo rigoroso gli argomenti controversi) e un set di dati canonico ben definito produce un'elevata percentuale di accettazione.

## Cinque domini, regole reali

Non semplici modelli di esempio. Ogni dominio viene fornito con regole della costituzione adatte alla produzione, definizioni delle corsie, rubriche di valutazione e vocabolario di gruppo.

| Dominio | Corsie | Cosa viene valutato |
|--------|-------|-----------------|
| **game-art** | personaggio, ambiente, oggetto di scena, interfaccia utente, nave, interno, attrezzatura | Silhouette su scala di gioco, identificazione della fazione, usura e invecchiamento |
| **character-design** | ritratto, figura intera, rotazione a 360 gradi, foglio di espressioni, posa d'azione | Proporzioni, logica del costume, personalità, chiarezza dei gesti |
| **creature-design** | concetto, ortografico, studio dettagliato, azione, riferimento alla scala, habitat | Anatomia, logica evolutiva, distinzione della silhouette |
| **architecture** | esterno, interno, paesaggio urbano, dettaglio strutturale, rovina, paesaggio | Struttura, coerenza dei materiali, prospettiva, coerenza dell'epoca |
| **vehicle-mech** | esterno, cabina di pilotaggio, componente, schema, foglio di silhouette, variante danneggiata | Logica meccanica, linguaggio del design, punti di accesso, narrazione dei danni |

## Struttura del progetto

Ogni progetto è autonomo. Cinque file di configurazione JSON definiscono le regole; tutto il resto sono dati.

```
projects/my-project/
  project.json           Identity + generation defaults
  constitution.json      Rules with rationale templates
  lanes.json             Subject lanes with detection patterns
  rubric.json            Scoring dimensions + thresholds
  terminology.json       Group vocabulary + detection order
  records/               Per-asset JSON (provenance + judgment + canon)
  snapshots/             Frozen dataset snapshots
  splits/                Train/val/test partitions
  exports/               Versioned export packages
  training/              Profiles, manifests, packages, eval runs, implementations
  workflows/             Workflow profiles + batch mode definitions
  briefs/                Compiled generation briefs
  runs/                  Execution artifacts (brief + outputs + manifest)
  batches/               Coordinated multi-slot productions
  selections/            Chosen outputs with reasons and provenance
  inbox/generated/       Re-ingested images awaiting review
```

## Proprietà di affidabilità

Queste non sono semplici aspirazioni. Sono applicate rigorosamente.

- **Gli snapshot sono immutabili.** L'impronta della configurazione (SHA-256) dimostra che nulla è stato modificato. Gli ID vengono assegnati in modo atomico, quindi due esecuzioni simultanee non possono sovrapporsi nella stessa directory.
- **Le suddivisioni impediscono la dispersione e il controllo che lo verifica è indipendente.** Le famiglie di soggetti (per identità, discendenza o radice ID normalizzata) non attraversano mai i confini delle partizioni e un secondo controllo deriva nuovamente l'identità del soggetto da zero anziché rileggere la mappa utilizzata dalla suddivisione stessa. Una scheda del set di dati afferma solo "dispersione: nessuna (verificata)" quando entrambi i controlli sono stati eseguiti correttamente; una suddivisione precedente al secondo controllo indica esattamente questo.
- **I manifest sono contratti congelati.** Hash dell'esportazione + impronta della configurazione e `validate` ricalcola l'hash di ogni file elencato in `checksums.txt`: quindi, la sostituzione di un'immagine all'interno di un'esportazione completata viene rilevata, anche per i manifest creati prima che questo controllo esistesse.
- **Le esecuzioni definiscono il loro grafo esatto.** Ogni generazione registra `comfy_workflow_sha` + hash del contenuto del modello/LoRA + policy dei seed, quindi una serie può essere riprodotta byte per byte. Gli script JS e Python sono vincolati a un hash identico tramite un test che li avvia entrambi. L'hashing del modello è facoltativo (`--hash-models`) e non viene mai fabbricato: un file irrisolvibile registra `sha256: null` con una nota.
- **Nessun modello verifica il proprio output.** I giudizi registrano `judged_by_model` e `generator_model`; se questi sono sempre lo stesso modello, viene visualizzato un avviso.
- **Un giudizio indica chi l'ha creato.** `eligibility audit` distingue i giudizi scritti da una persona dai giudizi generati da uno script di massa, quindi una motivazione che descrive una categoria anziché un'immagine non può essere considerata come curatela.
- **La misurazione non è una valutazione.** `sdlab measure` associa numeri a un record. Non imposta mai un giudizio, un adattamento o un'approvazione e, quando una misura non è definita per un'immagine, registra `null` anziché un numero plausibile.
- **Gli adattatori non possono modificare la verità.** Layout diverso, stessi record. Nessuna aggiunta, nessuna rimozione, nessuna riclassificazione.
- **Gli output generati vengono reinseriti attraverso la revisione.** Nessun bypass. Curatela e associazione come per tutto il resto. Le immagini generate esternamente entrano nello stesso modo tramite `sdlab ingest`, senza curatela preliminare.
- **I fallimenti sono visibili.** Un record mancante, un'immagine che non può essere posizionata o una didascalia che non può essere creata interrompe un pacchetto di esportazione o addestramento anziché ridurlo silenziosamente.

## Star Freight

Il repository include un esempio completo funzionante: 1.182 record, 5 fazioni, 7 percorsi, 24 regole costitutive, 892 risorse approvate, 2 profili di addestramento. Un canone visivo di fantascienza RPG, completamente curato.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## Formati downstream

`sdlab` possiede il set di dati. La conversione del formato è gestita da [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset): TRL, LLaVA, Qwen2-VL, JSONL, Parquet e altro ancora. `repo-dataset` esegue il rendering; non decide mai l'inclusione.

## Installazione

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Richiede Node.js 20+ e [ComfyUI](https://github.com/comfyanonymous/ComfyUI) su localhost:8188 per la generazione.

### Prova senza ComfyUI

È possibile esplorare l'intera interfaccia non di generazione (ispezione, curatela, snapshot, suddivisione, esportazione) utilizzando il progetto Star Freight incluso, senza installare ComfyUI o scaricare alcun peso SDXL.

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor` validates every project config (constitution, lanes, rubric, terminology) and reports eligibility without touching the GPU. Any command that mutates generated state accepts `--dry-run` to preview the effect first.

Se si dimentica `--project`, la CLI torna al primo progetto che trova in `projects/` e stampa un avviso: passare `--project` esplicitamente per disattivarlo.

### Ripresa di un'esecuzione interrotta

Le lunghe esecuzioni di generazione possono essere riprese senza ripetere il lavoro completato:

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

Entrambi i comandi funzionano perché ogni slot scrive la sua voce del manifest in modo atomico al termine; un arresto anomalo durante l'esecuzione non corrompe mai lo stato parziale.

## Risoluzione dei problemi

Modalità di errore comuni e soluzioni:

**`ECONNREFUSED 127.0.0.1:8188` su qualsiasi `sdlab generate` / `sdlab run generate` / `sdlab batch generate`**
ComfyUI non è in esecuzione. Avviare ComfyUI (`python main.py --listen 127.0.0.1 --port 8188`) e confermare con `curl http://127.0.0.1:8188/system_stats`. Per puntare a un host/porta diverso, impostare `COMFY_URL=http://host:port`.

**`missing checkpoint` / `LoRA weight not found`**
Il profilo del flusso di lavoro fa riferimento a un file modello che non si trova nelle cartelle `models/checkpoints/` o `models/loras/` di ComfyUI. Aprire `projects/<project>/workflows/profiles/<profile>.json`, individuare il campo `checkpoint` o `lora` e scaricare il peso di riferimento oppure sostituirlo con uno già disponibile. Rieseguire `sdlab project doctor --project <project>` per confermare la correzione.

**Errori `sdlab project doctor`**
Doctor restituisce codici di errore strutturati. Alcuni comuni:
- `E_PROJECT_NOT_FOUND`: la directory del progetto non esiste in `projects/`. Controllare l'ortografia.
- `E_CONFIG_INVALID`: uno dei cinque file di configurazione JSON non ha superato la convalida dello schema. Il campo `hint` indica il file e il campo problematici.
- `E_RECORD_DRIFT`: l'impronta della configurazione di un record non corrisponde più alla sua origine. Curare o riassociare come suggerito.

**Avviso `No --project specified, falling back to <name>`**
Un avviso lieve. Passare `--project <name>` esplicitamente per selezionare il progetto corretto e disattivare l'avviso.

**Painterly / VRAM out-of-memory issues**
See `docs/internal/HANDOFF.md` for the painterly denoise tuning notes. In short: lower the denoise strength, reduce batch size, or switch to a smaller checkpoint in your workflow profile.

**Reporting bugs**
File an issue at https://github.com/mcp-tool-shop-org/style-dataset-lab/issues with your sdlab version (`sdlab --version`), Node version (`node -v`), the full command, and the structured error output. A bug-report template prefills the fields.

## Sicurezza

Solo locale. Nessun telemetria, nessuna analisi, nessuna richiesta esterna. Le immagini rimangono sulla GPU e sul file system.

## Licenza

MIT

---

Realizzato da <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
