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

Scrivete le vostre regole visive. Generate opere d'arte. Valutate ogni immagine in base a tali regole. Distribuite i risultati come dati di addestramento versionati e verificabili.

Style Dataset Lab collega le caratteristiche del vostro stile artistico definite in precedenza al set di dati utilizzato per l'addestramento. Definite una "costituzione" che includa regole sulla silhouette, vincoli di palette, linguaggio dei materiali, o qualsiasi altro aspetto rilevante per il vostro progetto. Il sistema genera candidati, li valuta in base a tali regole e confeziona le opere approvate in set di dati riproducibili, in cui ogni elemento spiega perché è stato incluso.

Il ciclo si chiude: addestrate un modello, generate nuovi risultati, valutateli in base agli stessi criteri e reinserite ciò che supera i test. Il set di dati cresce e le regole rimangono valide.

## La pipeline

```bash
# Write your canon. Scaffold the project.
sdlab init my-project --domain character-design

# Generate candidates via ComfyUI, then review them
sdlab generate inputs/prompts/wave1.json --project my-project
sdlab curate <id> approved "Strong silhouette, correct faction palette"

# Bind approved work to constitution rules
sdlab bind --project my-project

# Freeze a versioned dataset
sdlab snapshot create --project my-project
sdlab split build
sdlab export build

# Build a training package and close the loop
sdlab training-manifest create --profile character-style-lora
sdlab training-package build
sdlab eval-run create && sdlab eval-run score <id> --outputs results.jsonl
sdlab reingest generated --source ./outputs --manifest <id>
```

L'ultimo comando è fondamentale. I risultati generati vengono sottoposti allo stesso processo di revisione di tutto il resto. Il ciclo si chiude.

## Cosa produce

Sette artefatti versionati e con checksum. Ognuno è collegato ai suoi predecessori, in modo da poter risalire a qualsiasi record di addestramento alla regola che lo ha approvato.

| Artefatto. | Cos'è. |
|----------|-----------|
| **Snapshot** | Selezione di record "congelati" con impronta di configurazione. Ogni inclusione ha una motivazione esplicita. |
| **Split** | Partizione di addestramento/validazione/test in cui le famiglie di soggetti non si sovrappongono. |
| **Export package** | Set di dati autonomo: manifest, metadati, immagini, suddivisioni, scheda del set di dati, checksum. |
| **Eval pack** | Compiti di test sensibili al "canone": copertura delle "lane", deriva proibita, ancoraggi/modelli di riferimento, continuità dei soggetti. |
| **Training package** | Layout pronto per l'addestramento tramite adattatori (`diffusers-lora`, `generic-image-caption`). Stessa verità, formato diverso. |
| **Eval scorecard** | Valutazione di superamento/non superamento per ogni compito, in base alla valutazione dei risultati generati rispetto ai set di valutazione. |
| **Implementation pack** | Esempi di prompt, errori noti, test di continuità e indicazioni per il reinserimento. |

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

## Sicurezza

Funziona solo localmente. Nessuna telemetria, nessuna analisi, nessuna richiesta esterna. Le immagini rimangono sulla GPU e sul filesystem locale.

## Licenza

MIT

---

Creato da <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
