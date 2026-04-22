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

Definisci le tue regole visive. Genera immagini. Valuta ogni immagine in base a quelle regole. Invia i risultati come dati di addestramento versionati e verificabili, quindi metti in funzione i modelli addestrati nei flussi di lavoro di produzione reali e reinserisci i risultati migliori nel tuo database.

Style Dataset Lab collega le caratteristiche del vostro stile artistico definite in precedenza al set di dati utilizzato per l'addestramento. Definite una "costituzione" che includa regole sulla silhouette, vincoli di palette, linguaggio dei materiali, o qualsiasi altro aspetto rilevante per il vostro progetto. Il sistema genera candidati, li valuta in base a tali regole e confeziona le opere approvate in set di dati riproducibili, in cui ogni elemento spiega perché è stato incluso.

Successivamente, entra in gioco l'ambiente di lavoro di produzione: compila le istruzioni di generazione a partire dalle informazioni del progetto, eseguile tramite ComfyUI, valuta i risultati, genera in batch fogli di espressioni e schemi ambientali, seleziona i risultati migliori e reinseriscili come nuovi candidati. Il ciclo si chiude: genera, seleziona, valuta, migliora.

## La pipeline

```bash
# Write your canon. Scaffold the project.
sdlab init my-project --domain character-design

# Generate candidates via ComfyUI, then review them
sdlab generate inputs/prompts/wave1.json --project my-project
sdlab curate <id> approved "Strong silhouette, correct faction palette"

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

Quest'ultimo comando è fondamentale. I risultati selezionati vengono sottoposti allo stesso processo di valutazione di tutto il resto. Il database cresce e le regole rimangono valide.

## Cosa produce

Sono disponibili sette elementi del database e un intero ambiente di lavoro di produzione. Ogni elemento è collegato ai suoi predecessori, in modo da poter risalire a qualsiasi record di addestramento alla regola che lo ha approvato.

| Artefatto. | Cos'è. |
|----------|-----------|
| **Snapshot** | Selezione di record "congelati" con impronta di configurazione. Ogni inclusione ha una motivazione esplicita. |
| **Split** | Partizione di addestramento/validazione/test in cui le famiglie di soggetti non si sovrappongono. |
| **Export package** | Set di dati autonomo: manifest, metadati, immagini, suddivisioni, scheda del set di dati, checksum. |
| **Eval pack** | Compiti di test sensibili al "canone": copertura delle "lane", deriva proibita, ancoraggi/modelli di riferimento, continuità dei soggetti. |
| **Training package** | Layout pronto per l'addestramento tramite adattatori (`diffusers-lora`, `generic-image-caption`). Stessa verità, formato diverso. |
| **Eval scorecard** | Valutazione di superamento/non superamento per ogni compito, in base alla valutazione dei risultati generati rispetto ai set di valutazione. |
| **Implementation pack** | Esempi di prompt, errori noti, test di continuità e indicazioni per il reinserimento. |

L'ambiente di lavoro di produzione offre:

| Superficie di interazione | Cosa fa |
|---------|-------------|
| **Compiled brief** | Generazione deterministica a partire dal profilo del flusso di lavoro e dalle informazioni del progetto. |
| **Run** | Artefatto di esecuzione stabile: istruzioni + seed + output di ComfyUI + manifest. |
| **Critique** | Valutazione strutturata e multidimensionale dei risultati rispetto al modello di riferimento. |
| **Batch** | Produzione coordinata su più canali (fogli di espressioni, schemi ambientali, pacchetti di silhouette). |
| **Selection** | Artefatto delle decisioni creative: quali output sono stati scelti, perché e da dove provengono. |
| **Re-ingest** | Gli output selezionati vengono restituiti come record candidati con la completa provenienza della generazione. |

## Perché esiste

I dati di addestramento sono l'elemento più importante in qualsiasi pipeline di intelligenza artificiale visiva. Tuttavia, la maggior parte dei dati di addestramento è costituita da una cartella di immagini senza una cronologia, senza una traccia di valutazione e senza un collegamento alle regole di stile che avrebbero dovuto seguire.

Style Dataset Lab rende esplicito questo collegamento. La vostra "costituzione" definisce le regole. La vostra "rubrica" definisce le dimensioni della valutazione. I vostri registri di "curazione" documentano la valutazione. La vostra "prova canonica" dimostra il collegamento. E il vostro set di dati porta con sé tutto questo come una verità strutturata, interrogabile e riproducibile.

Il risultato pratico: quando il vostro LoRA si discosta, potete capire *perché*. Quando la vostra prossima fase di addestramento necessita di dati migliori, sapete esattamente quali record sono "quasi giusti" e quale singola regola hanno violato. Quando un nuovo membro del team chiede qual è il linguaggio visivo del progetto, la risposta non è una lavagna Figma, ma una "costituzione" ricercabile con 1.182 esempi valutati.

## Cinque domini, regole reali

Non modelli di esempio. Ogni dominio viene fornito con regole di "costituzione" di livello professionale, definizioni di "lane", rubriche di valutazione e vocabolario di gruppo.

| Dominio. | Lane. | Cosa viene valutato. |
|--------|-------|-----------------|
| **game-art** | personaggio, ambiente, oggetto, interfaccia utente, nave, interno, attrezzatura. | Silhouette alla scala del gameplay, interpretazione della fazione, usura e invecchiamento. |
| **character-design** | ritratto, figura intera, vista a 360°, foglio di espressioni, posa d'azione. | proporzioni, logica dell'abbigliamento, personalità, chiarezza dei gesti. |
| **creature-design** | concept, ortografico, studio dei dettagli, azione, riferimento delle dimensioni, habitat. | anatomia, logica evolutiva, distinzione della silhouette. |
| **architecture** | esterno, interno, paesaggio urbano, dettaglio strutturale, rovina, paesaggio. | struttura, coerenza dei materiali, prospettiva, coerenza dell'epoca. |
| **vehicle-mech** | esterno, cabina di pilotaggio, componente, schema, foglio di silhouette, variante danneggiata. | logica meccanica, linguaggio del design, punti di accesso, narrazione dei danni. |

## Struttura del progetto

Ogni progetto è autonomo. Cinque file di configurazione JSON definiscono le regole; il resto è costituito da dati.

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

## Principi fondamentali

Questi principi non sono solo aspirazionali, ma vengono applicati rigorosamente.

- **Gli snapshot sono immutabili.** L'impronta digitale della configurazione (SHA-256) dimostra che nulla è cambiato.
- **Le suddivisioni impediscono la fuoriuscita di dati.** Le famiglie di soggetti (definite da identità, lignaggio o suffisso ID) non attraversano i confini delle partizioni.
- **I manifesti sono contratti vincolanti.** Esportazione dell'hash + impronta digitale della configurazione. Se qualcosa cambia, è necessario crearne uno nuovo.
- **Gli adattatori non possono alterare i dati.** Layout diversi, ma stessi record. Nessuna aggiunta, nessuna rimozione, nessuna riclassificazione.
- **Gli output generati vengono riesaminati.** Non ci sono scorciatoie. Vengono curati e collegati come tutto il resto.

## Star Freight

Il repository include un esempio completo e funzionante: 1.182 record, 5 fazioni, 7 percorsi, 24 regole costituzionali, 892 risorse approvate, 2 profili di addestramento. Un canone visivo di un RPG fantascientifico, completamente curato.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## Formati di output

`sdlab` è proprietaria del dataset. La conversione del formato è gestita da [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset): TRL, LLaVA, Qwen2-VL, JSONL, Parquet e altro. `repo-dataset` esegue la conversione; non decide quali dati includere.

## Installazione

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Richiede Node.js 20+ e [ComfyUI](https://github.com/comfyanonymous/ComfyUI) installato localmente all'indirizzo localhost:8188 per la generazione.

### Prova senza ComfyUI

È possibile esplorare l'intera interfaccia di interazione, escluse le funzioni di generazione, tramite l'ispezione, la curatela, lo snapshot, la suddivisione e l'esportazione, utilizzando il progetto Star Freight incluso, senza installare ComfyUI o scaricare alcun file SDXL.

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

Il comando `sdlab project doctor` convalida la configurazione di ogni progetto (costituzione, percorsi, rubriche, terminologia) e segnala l'idoneità senza utilizzare la GPU. Qualsiasi comando che modifichi lo stato generato accetta l'opzione `--dry-run` per visualizzare l'effetto prima di applicarlo.

Se si dimentica `--project`, la CLI passa al primo progetto trovato nella cartella `projects/` e visualizza un avviso; per disattivare l'avviso, è necessario specificare esplicitamente `--project`.

### Riprendere un'esecuzione interrotta

È possibile riprendere le lunghe esecuzioni di generazione senza dover ripetere il lavoro già completato:

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

Entrambi i comandi funzionano perché ogni sezione scrive il proprio file manifest in modo atomico al termine dell'esecuzione; un arresto anomalo durante l'esecuzione non corrompe lo stato parziale.

## Risoluzione dei problemi

Modalità di errore comuni e soluzioni:

**`ECONNREFUSED 127.0.0.1:8188` in qualsiasi comando `sdlab generate` / `sdlab run generate` / `sdlab batch generate`**
ComfyUI non è in esecuzione. Avvia ComfyUI (`python main.py --listen 127.0.0.1 --port 8188`) e verifica con `curl http://127.0.0.1:8188/system_stats`. Per puntare a un host/porta diverso, imposta `COMFY_URL=http://host:port`.

**`missing checkpoint` / `LoRA weight not found`**
Il profilo del flusso di lavoro indica un file modello che non si trova nelle cartelle `models/checkpoints/` o `models/loras/` di ComfyUI. Apri `projects/<project>/workflows/profiles/<profile>.json`, individua il campo `checkpoint` o `lora` e scarica il file corrispondente oppure sostituiscilo con uno che hai già. Esegui nuovamente `sdlab project doctor --project <project>` per confermare la correzione.

**Errori di `sdlab project doctor`**
Doctor restituisce codici di errore strutturati. Alcuni esempi comuni:
- `E_PROJECT_NOT_FOUND` — la directory del progetto non esiste nella cartella `projects/`. Verifica l'ortografia.
- `E_CONFIG_INVALID` — uno dei cinque file di configurazione JSON non ha superato la convalida dello schema. Il campo `hint` indica il file e il campo errati.
- `E_RECORD_DRIFT` — l'impronta digitale della configurazione di un record non corrisponde più alla sua origine. Ricurata o ricollega come suggerito nell'hint.

**`Nessun progetto specificato, si utilizza il valore predefinito <name>`**
Un avviso di lieve entità. Utilizzare l'opzione `--project <name>` per specificare esplicitamente il progetto desiderato e silenziare l'avviso.

**Problemi relativi alla memoria della VRAM (painterly)**
Consultare il file `docs/internal/HANDOFF.md` per le note sulla regolazione del denoising "painterly". In breve: ridurre l'intensità del denoising, diminuire la dimensione del batch o utilizzare un checkpoint più piccolo nel profilo di lavoro.

**Segnalazione di bug**
Aprire una segnalazione all'indirizzo https://github.com/mcp-tool-shop-org/style-dataset-lab/issues, includendo la versione di sdlab (`sdlab --version`), la versione di Node (`node -v`), il comando completo e l'output dettagliato dell'errore. Un modello per la segnalazione di bug precompila i campi.

## Sicurezza

Funziona solo localmente. Nessuna telemetria, nessuna analisi, nessuna richiesta esterna. Le immagini rimangono sulla GPU e sul filesystem locale.

## Licenza

MIT

---

Creato da <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
