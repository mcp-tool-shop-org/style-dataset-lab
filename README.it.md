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

Scrivi le tue regole visive. Genera immagini. Valuta ogni immagine in base a tali regole. Pubblica i risultati come dati di addestramento versionati e verificabili, quindi metti a disposizione i modelli addestrati per l'utilizzo in flussi di lavoro di produzione reali e reintroduci gli output migliori nel tuo corpus.

Style Dataset Lab collega le informazioni che hai scritto sullo stile artistico al set di dati da cui effettivamente esegui l'addestramento, quindi completa il ciclo fino alla produzione. Definisci una serie di regole: regole sulla silhouette, vincoli sulla palette, linguaggio dei materiali, tutto ciò che è importante per il tuo progetto. La pipeline genera candidati, li valuta in base a tali regole e raggruppa il lavoro approvato in set di dati riproducibili, in cui ogni record spiega perché è stato incluso.

Quindi, la workstation di produzione prende il controllo: compila le specifiche di generazione a partire dai dati di riferimento del progetto, le esegue tramite ComfyUI, valuta gli output, produce in batch le schede di espressione e le tavole di ambientazione, seleziona i risultati migliori e li reintroduce come nuovi candidati. Il ciclo si chiude: produci, seleziona, rivedi, rafforza.

## La pipeline

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

Quest'ultimo comando è il punto cruciale. Gli output selezionati vengono sottoposti allo stesso processo di revisione di tutti gli altri. Il corpus cresce e le regole rimangono valide.

## Il flusso di asset: esportazioni 3D come dati di addestramento

`sdlab ingest` accetta le immagini grezze senza riserve. `sdlab asset ingest` richiede un **contratto**.

Quando un asset 3D supera la fase di accettazione, il rendering da N angolazioni diverse ti fornisce una vista coerente *per costruzione*, una proprietà che la diffusione per ogni vista non può garantire. Il flusso di asset accetta queste esportazioni come dati di addestramento che contengono informazioni sulla provenienza:

```bash
# Validate an export's manifest end to end, run the gates, write nothing
sdlab asset ingest ~/exports/dragon_dense --project my-project --dry-run

# Register it: records, candidates, masks, channels, receipt
sdlab asset ingest ~/exports/dragon_dense --project my-project
```

La directory di esportazione contiene un manifesto `asset-source.json` (schema **1.3.0**) che dichiara
i suoi canali, le bande della palette, le soglie, il verdetto di accettazione, il registro dello stile, come
i rendering sono stati creati e la loro provenienza. sdlab verifica ogni dichiarazione
con i byte effettivi e rifiuta l'intero caricamento in caso di violazione: nulla viene registrato
se il manifesto non è valido.

**Il punto di connessione:** sdlab fornisce il meccanismo, l'asset fornisce la semantica. sdlab non esegue mai il ray tracing,
non esegue mai il rendering e non impara mai che un canale chiamato "provenienza" è speciale. Verifica,
misura, registra e raggruppa. Il significato dei numeri rimane con l'asset.

Cosa garantisce il contratto:

| fase | cosa viene verificato |
|---|---|
| **schema** | forma, ID, bande della palette ben formate e un verdetto di accettazione che è letteralmente `"accepted"` |
| **containment** | ogni percorso di riferimento si risolve *all'interno* della directory di esportazione (è un input non attendibile) ed esiste |
| **encoding** | l'intestazione PNG corrisponde alla codifica dichiarata; un'intestazione NPY corrisponde al dtype e alla forma dichiarati. Un manifesto che "sembra corretto" ma non corrisponde ai suoi byte è la classe di errore che questo flusso esiste per evitare |
| **categorical** | le immagini PNG indicizzate dimostrano che PLTE ⊆ palette dichiarata; i canali filtrati con `nearest` ottengono una decodifica dei pixel *esaustiva*; le immagini NPY categoriche ottengono una scansione esaustiva dei valori |
| **gates** | il controllo della palette viene eseguito per ogni rendering, utilizzando le bande e le soglie del manifesto: un rendering non valido viene rifiutato in modo evidente e segnalato, non accettato silenziosamente |

I record vengono caricati **senza curatela** (`judgment: null`) con `provenance.source: "asset"`, contenendo
il blocco di accettazione letteralmente, gli hash per file, la posizione e l'orientamento della telecamera, le misurazioni, il registro dello stile dichiarato e il fotogramma di generazione e il seme per immagine. Quindi,
vengono sottoposti alla stessa curatela di tutti gli altri record.

Il caricamento segnala anche ciò che un manifesto *non* dichiara: un registro di stile sconosciuto, una
mancanza di `identity.subject_name`, l'assenza di informazioni sulla provenienza della generazione, come **avvisi** piuttosto che
come errori. Questi vengono inclusi nella ricevuta e stampati sulla CLI. Una lacuna di cui nessuno è a conoscenza è una lacuna
che nessuno può colmare; e poiché un manifesto può *dichiarare* che i suoi rendering sono derivazioni deterministiche senza un seme proprio, il flusso non segnala mai una lacuna per un'esportazione che è corretta.

Contratto completo, la scala di convalida e la motivazione di ogni campo:
[docs/asset-lane-design.md](docs/asset-lane-design.md).

## Creazione del canone

Prima che la pipeline del set di dati venga eseguita, lo spazio dei nomi `sdlab canon *` trasforma l'archivio di entità del canone del tuo progetto nelle tre proiezioni che l'addestramento e la produzione effettivamente utilizzano, e blocca le voci che non devono cambiare.

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

Un modello locale può anche creare il canone, ma non può decidere in merito. `sdlab canon draft <class_id> --endpoint <url> --brief "<text>" --out <path>` richiede a un server compatibile con OpenAI e con loopback esclusivo una voce del canone e dei suggerimenti, e le scrive con `status: "draft"`, `judgment: null` e il modello di creazione stampato su ogni output. Una bozza non può essere congelata finché una persona non la approva: la fase di congelamento rifiuta qualsiasi voce creata da un modello senza un'approvazione umana, una motivazione e l'hash della bozza esatta che è stata approvata.

`canon build` è indirizzabile in base al contenuto: il suo output è identificato da un `canon_sha` e memorizzato nella cache, quindi una ricostruzione del canone non modificato viene eseguita istantaneamente. `canon freeze` testimonia ogni congelamento rispetto a una build specifica e aggiunge una traccia di controllo `freeze-events.jsonl`: le voci `frozen` rifiutano esplicitamente la rigenerazione, le voci `soft-advisory` rifiutano per impostazione predefinita (bypass con `--i-know`). `canon drift` ricalcola l'hash di ogni voce monitorata e segnala qualsiasi cosa che si sia spostata dall'ultima build pulita.

Flusso di lavoro completo nel manuale: [Creazione del canone](handbook/canon-build/), [Congelamento del canone](handbook/canon-freeze/) e [Stacking a due livelli di LoRA](handbook/two-lora-stacking/).

## Cosa produce

Sette artefatti del set di dati e una workstation di produzione completa. Ogni artefatto è collegato ai suoi predecessori, in modo da poter risalire a qualsiasi record di addestramento fino alla regola che lo ha approvato.

| Artefatto | Cos'è |
|----------|-----------|
| **Snapshot** | Selezione di record congelati con impronta di configurazione. Ogni inclusione ha una motivazione esplicita. |
| **Split** | Partizione di addestramento/validazione/test in cui le famiglie di soggetti non attraversano mai i confini. |
| **Export package** | Set di dati autonomo: manifesto, metadati, immagini, suddivisioni, scheda del set di dati, checksum. |
| **Eval pack** | Attività di test che tengono conto del canone: copertura delle corsie, deriva proibita, riferimento/modello, continuità del soggetto. |
| **Training package** | Layout pronto per l'addestramento tramite adattatori (`diffusers-lora`, `generic-image-caption`). La stessa verità, formato diverso. |
| **Eval scorecard** | Valutazione per ogni attività: approvazione/rifiuto in base al punteggio degli output generati rispetto ai pacchetti di valutazione. |
| **Implementation pack** | Esempi di prompt, errori noti, test di continuità e indicazioni per il re-inserimento dei dati. |

L'ambiente di lavoro di produzione aggiunge:

| Superficie | Cosa fa |
|---------|-------------|
| **Compiled brief** | Istruzione di generazione deterministica dal profilo del flusso di lavoro + verità del progetto. |
| **Run** | Artefatto di esecuzione congelato: breve descrizione + seed + output ComfyUI + manifesto. |
| **Critique** | Valutazione strutturata multidimensionale degli output di esecuzione rispetto al canone. |
| **Batch** | Produzione coordinata multi-slot (schede di espressione, pannelli ambientali, pacchetti di silhouette). |
| **Selection** | Artefatto di decisione creativa: quali output sono stati scelti, perché e da dove provengono. |
| **Re-ingest** | Gli output selezionati vengono restituiti come record candidati con la completa provenienza della generazione. |

## Perché esiste

I dati di addestramento sono l'artefatto più importante in qualsiasi pipeline di intelligenza artificiale visiva. Ma la maggior parte dei dati di addestramento è una cartella di immagini senza cronologia, senza una traccia di valutazione e senza un collegamento alle regole di stile che avrebbe dovuto seguire.

Style Dataset Lab rende esplicita la connessione. La tua costituzione definisce le regole. La tua rubrica definisce le dimensioni del punteggio. Le tue registrazioni di curatela documentano la valutazione. Il tuo vincolo di canone dimostra la connessione. E il tuo set di dati porta tutto questo avanti come verità strutturata, ricercabile e riproducibile.

Il risultato pratico: quando il tuo LoRA devia, puoi chiedere *perché*. Quando la tua prossima sessione di addestramento necessita di dati migliori, sai esattamente quali record sono quasi fallimenti e quale singola regola hanno violato. Quando un nuovo membro del team chiede qual è il linguaggio visivo del progetto, la risposta non è una bacheca Figma, ma una costituzione ricercabile con 1.182 esempi valutati.

## Dimostrato in produzione

Questa non è una pipeline di dimostrazione. Due veri e propri style-LoRA sono stati implementati completamente — lo stesso ciclo canone → curatela → addestramento → implementazione, alle estremità opposte dello spettro della curatela.

- **[Tallow Fen](handbook/case-study-tallow-fen/)** (progettazione di creature) — un canone di bestiario creato da zero, **~34% di approvazione** su 293 record curati (169 rifiutati — il filtro rifiuta in modo rigoroso). Implementato `tallow_fen_style_v3.safetensors` @ 1.5 su `qwen-image`.
- **[Rustline](handbook/case-study-rustline/)** (progettazione di concept) — canone denso e preformato, **~96% di approvazione** su 180 record. Implementato `rustline_v3ckpt_1500.safetensors` @ 1.0 su `qwen-image`, riutilizzato a valle da un secondo progetto.

La stessa pipeline, due profili di produzione: il filtro di curatela è reale (rifiuta in modo rigoroso su soggetti aperti) e un canone disciplinato produce un'alta accettazione.

## Cinque domini, regole reali

Non modelli di esempio. Ogni dominio viene fornito con regole di costituzione di livello di produzione, definizioni di corsie, rubriche di valutazione e vocabolario di gruppo.

| Dominio | Corsie | Cosa viene valutato |
|--------|-------|-----------------|
| **game-art** | personaggio, ambiente, oggetto di scena, interfaccia utente, nave, interno, attrezzatura | Silhouette su scala di gioco, leggibilità della fazione, usura e invecchiamento |
| **character-design** | ritratto, figura intera, rotazione, scheda di espressioni, posa d'azione | Proporzioni, logica del costume, personalità, chiarezza della gestualità |
| **creature-design** | concept, ortografico, studio dei dettagli, azione, riferimento di scala, habitat | Anatomia, logica evolutiva, distinzione della silhouette |
| **architecture** | esterno, interno, paesaggio urbano, dettaglio strutturale, rovina, paesaggio | Struttura, coerenza dei materiali, prospettiva, coerenza dell'epoca |
| **vehicle-mech** | esterno, cabina di pilotaggio, componente, schema, scheda di silhouette, variante di danno | Logica meccanica, linguaggio del design, punti di accesso, narrazione del danno |

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

Queste non sono aspirazionali. Sono applicate.

- **Gli snapshot sono immutabili.** L'impronta di configurazione (SHA-256) dimostra che non sono state apportate modifiche. Gli ID vengono acquisiti in modo atomico, quindi due esecuzioni concorrenti non possono sovrapporsi in una singola directory.
- **Le suddivisioni prevengono perdite di dati e il controllo che lo attesta è indipendente.** Le famiglie di soggetti (per identità, discendenza o ID normalizzato) non attraversano mai i confini delle partizioni e un secondo controllo deriva nuovamente l'identità del soggetto da zero anziché rileggere la mappa utilizzata dalla suddivisione stessa. Una scheda del set di dati afferma solo che non ci sono "perdite di dati" quando entrambi i controlli vengono eseguiti e superati; una suddivisione precedente al secondo controllo afferma esattamente questo.
- **I manifest sono contratti vincolanti.** Hash di esportazione + impronta di configurazione e `validate` ricalcola l'hash di ogni file elencato da `checksums.txt`, quindi la sostituzione di un'immagine all'interno di un'esportazione completata viene rilevata, anche per i manifest creati prima dell'esistenza di tale controllo.
- **Le esecuzioni definiscono il loro grafo esatto.** Ogni generazione registra `comfy_workflow_sha` + hash del contenuto del modello/LoRA + policy di seed, quindi un ciclo può essere riprodotto byte per byte. Gli esecutori JS e Python sono vincolati a un hash identico a livello di byte da un test che li avvia entrambi. L'hashing del modello è opzionale (`--hash-models`) e non viene mai falsificato: un file irrisolvibile registra `sha256: null` con una nota.
- **Nessun modello verifica il proprio output.** I giudizi registrano `judged_by_model` e `generator_model`; viene generato un avviso se sono sempre lo stesso modello.
- **Un giudizio indica chi lo ha creato.** `eligibility audit` distingue i giudizi scritti da una persona dai giudizi generati da uno script di massa, quindi una motivazione che descrive una categoria anziché un'immagine non può essere considerata una curatela.
- **La misurazione non è una sentenza.** `sdlab measure` associa numeri a un record. Non stabilisce mai un giudizio, un adattamento o un'approvazione e, quando una misurazione non è definita per un'immagine, registra `null` anziché un numero plausibile.
- **Un rilascio può dimostrare da dove proviene ogni immagine.** `sdlab verify --project <name>` esamina la catena offline per ogni record: il proprietario e la licenza nel record, la voce del canone a cui era vincolato (tramite hash), la licenza di ogni modello e LoRA che lo ha creato (ID SPDX, URL della licenza, la data in cui è stato letto e l'hash del file) e l'hash del flusso di lavoro nel manifest dell'esecuzione. Un collegamento mancante fa fallire il controllo anziché superarlo.
- **Gli adattatori non possono modificare la verità.** Layout diverso, stessi record. Nessuna aggiunta, nessuna rimozione, nessuna riclassificazione.
- **Gli output generati vengono reintrodotti tramite la revisione.** Nessun bypass. Curare e vincolare come tutto il resto. Le immagini generate esternamente entrano nello stesso modo tramite `sdlab ingest`, senza curatela.
- **I fallimenti sono visibili.** Un record mancante, un'immagine non collocabile o una didascalia che non può essere creata interrompe un'esportazione o un pacchetto di addestramento anziché ridurlo silenziosamente.

## Star Freight

Il repository include un esempio completo e funzionante: 1.182 record, 5 fazioni, 7 percorsi, 24 regole costitutive, 892 risorse approvate, 2 profili di addestramento. Un canone visivo di un RPG fantascientifico, completamente curato.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## Formati downstream

`sdlab` possiede il set di dati. La conversione del formato è gestita da [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset): TRL, LLaVA, Qwen2-VL, JSONL, Parquet e altro. `repo-dataset` esegue il rendering; non decide mai l'inclusione.

## Installazione

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Richiede Node.js 20+ e [ComfyUI](https://github.com/comfyanonymous/ComfyUI) su localhost:8188 per la generazione.

### Prova senza ComfyUI

È possibile esplorare l'intera superficie non di generazione (ispezione, curatela, snapshot, suddivisione, esportazione) utilizzando il progetto Star Freight incluso senza installare ComfyUI o scaricare alcun peso SDXL.

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor` convalida ogni configurazione del progetto (costituzione, percorsi, rubrica, terminologia) e segnala l'idoneità senza toccare la GPU. Qualsiasi comando che modifica lo stato generato accetta `--dry-run` per visualizzare in anteprima l'effetto.

Se si dimentica `--project`, la CLI torna al primo progetto che trova in `projects/` e stampa un avviso: passare `--project` esplicitamente per disattivarlo.

### Ripresa di un'esecuzione interrotta

Le lunghe esecuzioni possono essere riprese senza ripetere il lavoro completato:

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

Entrambi i comandi funzionano perché ogni slot scrive la voce del manifest in modo atomico al termine: un arresto anomalo a metà esecuzione non corrompe mai lo stato parziale.

## Risoluzione dei problemi

Modalità di errore comuni e soluzioni:

**`ECONNREFUSED 127.0.0.1:8188` su qualsiasi `sdlab generate` / `sdlab run generate` / `sdlab batch generate`**
ComfyUI non è in esecuzione. Avviare ComfyUI (`python main.py --listen 127.0.0.1 --port 8188`) e confermare con `curl http://127.0.0.1:8188/system_stats`. Per puntare a un host/porta diverso, impostare `COMFY_URL=http://host:port`.

**`missing checkpoint` / `LoRA weight not found`**
Il profilo del flusso di lavoro fa riferimento a un file di modello che non si trova nella cartella `models/checkpoints/` o `models/loras/` di ComfyUI. Aprire `projects/<project>/workflows/profiles/<profile>.json`, individuare il campo `checkpoint` o `lora` e scaricare il peso di riferimento oppure sostituirlo con uno che si ha già. Rieseguire `sdlab project doctor --project <project>` per confermare la correzione.

**Errori `sdlab project doctor`**
Doctor restituisce codici di errore strutturati. Alcuni comuni:
- `E_PROJECT_NOT_FOUND`: la directory del progetto non esiste in `projects/`. Controllare l'ortografia.
- `E_CONFIG_INVALID`: uno dei cinque file di configurazione JSON non ha superato la convalida dello schema. Il campo `hint` indica il file e il campo errati.
- `E_RECORD_DRIFT`: l'impronta di configurazione di un record non corrisponde più alla sua origine. Curare o vincolare nuovamente come suggerito.

**`No --project specified, falling back to <name>`**
Un avviso leggero. Passare `--project <name>` esplicitamente per selezionare il progetto corretto e disattivare l'avviso.

**Problemi di memoria VRAM / "Painterly"**
Consultare `docs/internal/HANDOFF.md` per le note sulla regolazione del denoise "painterly". In breve: ridurre la forza del denoise, ridurre la dimensione del batch o passare a un checkpoint più piccolo nel profilo del flusso di lavoro.

**Segnalazione di bug**
Aprire un problema su https://github.com/mcp-tool-shop-org/style-dataset-lab/issues con la versione di sdlab (`sdlab --version`), la versione di Node (`node -v`), il comando completo e l'output di errore strutturato. Un modello di segnalazione di bug precompila i campi.

## Sicurezza

Locale per impostazione predefinita. Nessun telemetria, nessuna analisi e nessuna richiesta esterna dalla CLI `sdlab`: le immagini rimangono sulla GPU e sul file system e `canon draft` rifiuta qualsiasi endpoint che non sia loopback.

L’unica eccezione è l’opzione di consenso esplicito. `scripts/colab/` contiene i kit di avvio per eseguire un rendering o un passaggio di addestramento LoRA sul proprio account Google Colab. Caricano solo i file che vengono specificati, vengono eseguiti entro un limite di spesa definito dal saldo attuale del proprio account Colab e interrompono la propria sessione all’uscita. Questi kit sono **sperimentali**: non hanno ancora completato un ciclo di test completo.

## Licenza

MIT

---

Realizzato da <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
