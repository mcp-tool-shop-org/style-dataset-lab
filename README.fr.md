<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.md">English</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
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

Écrivez vos règles visuelles. Générez des œuvres d’art. Évaluez chaque image en fonction de ces règles. Diffusez les résultats sous forme de données d’entraînement versionnées et auditables, puis mettez en œuvre les modèles entraînés dans des flux de travail de production réels et renvoyez les meilleurs résultats dans votre corpus.

Style Dataset Lab relie ce que vous avez écrit sur votre style artistique à l’ensemble de données à partir duquel vous effectuez réellement l’entraînement, puis boucle le processus jusqu’à la production. Vous définissez une constitution : règles de silhouette, contraintes de palette, langage des matériaux, tout ce qui compte pour votre projet. Le pipeline génère des candidats, les évalue en fonction de ces règles et regroupe les œuvres approuvées dans des ensembles de données reproductibles où chaque enregistrement explique pourquoi il a été inclus.

Ensuite, l’environnement de travail de production prend le relais : compilez des instructions de génération à partir des éléments clés du projet, exécutez-les via ComfyUI, évaluez les résultats, produisez en série des feuilles d’expression et des planches d’ambiance, sélectionnez les meilleurs résultats et réintégrez-les en tant que nouveaux candidats. La boucle se ferme : produire, sélectionner, examiner, améliorer.

## Le pipeline

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

Cette dernière commande est essentielle. Les résultats sélectionnés repassent par le même processus d’évaluation que tous les autres éléments. Le corpus s’enrichit et les règles sont respectées.

## Création de contenu canonique

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

`canon build` est adressable par contenu : sa sortie est indexée par un `canon_sha` et mise en cache, de sorte qu’une version non modifiée se reconstruit instantanément. `canon freeze` enregistre chaque « gel » par rapport à une version spécifique et l’ajoute à un historique d’audit `freeze-events.jsonl` : les entrées `frozen` refusent purement et simplement la régénération, les entrées `soft-advisory` refusent par défaut (contournement possible avec `--i-know`). `canon drift` recalcule le hachage de chaque entrée suivie et signale tout ce qui a été modifié depuis la dernière version propre.

Flux de travail complet dans le manuel : [Canon build](handbook/canon-build/), [Canon freeze](handbook/canon-freeze/) et [Empilement Two-LoRA](handbook/two-lora-stacking/).

## Ce qu’il produit

Sept artefacts d’ensemble de données et un environnement de travail de production complet. Chaque artefact est lié à ses prédécesseurs, ce qui vous permet de retracer tout enregistrement d’entraînement jusqu’à la règle qui l’a approuvé.

| Artefact. | Ce que c’est. |
|----------|-----------|
| **Snapshot** | Sélection des enregistrements figés avec empreinte de configuration. Chaque inclusion a une raison explicite. |
| **Split** | Partitionnement entraînement/validation/test où les familles de sujets ne se croisent jamais. |
| **Export package** | Ensemble de données autonome : manifeste, métadonnées, images, partitions, fiche d’informations sur l’ensemble de données, sommes de contrôle. |
| **Eval pack** | Tâches de test tenant compte du canon : couverture des voies, dérive interdite, ancrage/or, continuité des sujets. |
| **Training package** | Mise en page prête pour l’entraînement via des adaptateurs (`diffusers-lora`, `generic-image-caption`). Même vérité, format différent. |
| **Eval scorecard** | Résultat de réussite/échec par tâche obtenu en évaluant les résultats générés par rapport aux ensembles d’évaluation. |
| **Implementation pack** | Exemples d’invites, erreurs connues, tests de continuité et instructions pour la réintégration. |

L’environnement de travail de production ajoute :

| Surface. | Ce que cela fait. |
|---------|-------------|
| **Compiled brief** | Instruction de génération déterministe à partir du profil de flux de travail + des éléments clés du projet. |
| **Run** | Artefact d’exécution figé : instruction + graines + résultats ComfyUI + manifeste. |
| **Critique** | Évaluation structurée multidimensionnelle des résultats de l’exécution par rapport au canon. |
| **Batch** | Production coordonnée multi-slots (feuilles d’expression, planches d’ambiance, ensembles de silhouettes). |
| **Selection** | Artefact de décision créative : quels résultats ont été choisis, pourquoi et d’où ils proviennent. |
| **Re-ingest** | Les résultats sélectionnés sont renvoyés en tant qu’enregistrements candidats avec une provenance complète de la génération. |

## Pourquoi cela existe

Les données d’entraînement constituent l’artefact le plus important dans tout pipeline d’IA visuelle. Mais la plupart des données d’entraînement ne sont qu’un dossier d’images sans historique, sans suivi de l’évaluation et sans lien avec les règles de style qu’elles étaient censées suivre.

Style Dataset Lab rend le lien explicite. Votre constitution définit les règles. Votre barème définit les dimensions d’évaluation. Vos enregistrements de sélection consignent l’évaluation. Votre liaison canonique prouve le lien. Et votre ensemble de données conserve tout cela sous une forme structurée, interrogeable et reproductible.

Le résultat pratique : lorsque votre LoRA dérive, vous pouvez demander *pourquoi*. Lorsque votre prochain cycle d’entraînement a besoin de meilleures données, vous savez exactement quels enregistrements sont presque corrects et quelle règle ils ont violée. Lorsqu’un nouveau membre de l’équipe demande quel est le langage visuel du projet, la réponse n’est pas un tableau Figma, mais une constitution consultable avec 1 182 exemples notés.

## Prouvé en production

Il ne s’agit pas d’un pipeline de démonstration. Deux LoRA de style réels ont été mis en œuvre de bout en bout grâce à celui-ci, en utilisant la même boucle canon → sélection → entraînement → diffusion, aux extrémités opposées du spectre de la sélection.

- **[Tallow Fen](handbook/case-study-tallow-fen/)** (conception de créatures) — un bestiaire entièrement nouveau, avec environ **34 % d’approbation** sur 293 enregistrements sélectionnés (169 rejetés — le système de validation est strict). Publié `tallow_fen_style_v3.safetensors` @ 1.5 sur `qwen-image`.
- **[Rustline](handbook/case-study-rustline/)** (conception de concepts) — un ensemble dense et préformaté, avec environ **96 % d’approbation** sur 180 enregistrements. Publié `rustline_v3ckpt_1500.safetensors` @ 1.0 sur `qwen-image`, réutilisé par un deuxième projet.

Même pipeline, deux profils de production : la porte de sélection est réelle (elle rejette fermement les sujets ouverts) et une canonisation disciplinée donne des taux d’acceptation élevés.

## Cinq domaines, règles réelles

Pas de modèles génériques. Chaque domaine est livré avec des règles de constitution de qualité professionnelle, des définitions de voies, des barèmes d’évaluation et un vocabulaire de groupe.

| Domaine | Voies | Ce qui est évalué |
|--------|-------|-----------------|
| **game-art** | personnage, environnement, accessoire, interface utilisateur, vaisseau, intérieur, équipement | Silhouette à l’échelle du jeu, identification de la faction, usure et vieillissement |
| **character-design** | portrait, corps entier, rotation, feuille d’expressions, pose d’action | Proportions, cohérence du costume, personnalité, clarté des gestes |
| **creature-design** | concept, orthographique, étude de détails, action, référence d’échelle, habitat | Anatomie, logique évolutive, distinction de la silhouette |
| **architecture** | extérieur, intérieur, paysage urbain, détail structurel, ruine, paysage | Structure, cohérence des matériaux, perspective, cohérence de l’époque |
| **vehicle-mech** | extérieur, cockpit, composant, schéma, feuille de silhouette, variante de dommage | Logique mécanique, langage du design, points d’accès, récit des dommages |

## Structure du projet

Chaque projet est autonome. Cinq fichiers de configuration JSON définissent les règles ; tout le reste est constitué de données.

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

## Propriétés de confiance

Ce ne sont pas des objectifs à atteindre. Elles sont appliquées.

- **Les instantanés sont immuables.** L’empreinte de configuration (SHA-256) prouve qu’aucun changement n’a été apporté. Les identifiants sont attribués de manière atomique, de sorte que deux exécutions simultanées ne peuvent pas se mélanger dans un seul répertoire.
- **Les divisions empêchent les fuites — et la vérification qui le confirme est indépendante.** Les familles d’éléments (par identité, lignée ou racine d’identifiant normalisée) ne traversent jamais les limites des partitions, et une deuxième vérification redétermine l’identité de l’élément à partir de zéro plutôt que de relire la carte utilisée par la division elle-même. Une carte de jeu de données n’indique « fuite : aucune (vérifiée) » que lorsque les deux vérifications ont été exécutées et réussies ; une division antérieure à la deuxième vérification indique exactement cela.
- **Les manifestes sont des contrats figés.** Hachage d’exportation + empreinte de configuration, et `validate` recalcule le hachage de chaque fichier répertorié par `checksums.txt` — ainsi, le remplacement d’une image dans une exportation terminée est détecté, y compris pour les manifestes créés avant l’existence de cette vérification.
- **Les exécutions définissent leur graphique exact.** Chaque génération enregistre `comfy_workflow_sha` + hachages du contenu du modèle/LoRA + politique de graines, de sorte qu’une série peut être rejouée octet par octet. Les exécutants JS et Python sont maintenus à un hachage identique au niveau de l’octet par un test qui les lance tous les deux. Le hachage des modèles est facultatif (`--hash-models`) et n’est jamais fabriqué — un fichier non résolvable enregistre `sha256: null` avec une note.
- **Aucun modèle ne vérifie sa propre sortie.** Les évaluations enregistrent `judged_by_model` et `generator_model` ; un avertissement s’affiche si elles sont identiques.
- **Une évaluation indique qui l’a créée.** `eligibility audit` distingue les évaluations écrites par une personne des évaluations générées par un script en masse, de sorte qu’une justification décrivant une catégorie plutôt qu’une image ne peut pas être considérée comme une curation.
- **La mesure n’est pas un verdict.** `sdlab measure` associe des nombres à un enregistrement. Elle ne définit jamais une évaluation, une adéquation ou une approbation — et lorsqu’une mesure est indéfinie pour une image, elle enregistre `null` plutôt qu’un nombre plausible.
- **Les adaptateurs ne peuvent pas modifier la vérité.** Mise en page différente, mêmes enregistrements. Pas d’ajouts, pas de suppressions, pas de reclassification.
- **Les sorties générées réintègrent le processus via l’examen.** Aucun contournement possible. Curater et lier comme tout le reste. Les images générées en externe entrent de la même manière via `sdlab ingest`, sans curation préalable.
- **Les échecs sont visibles.** Un enregistrement manquant, une image impossible à placer ou une légende qui ne peut pas être créée interrompent une exportation ou un ensemble d’entraînement plutôt que de le réduire silencieusement.

## Star Freight

Le dépôt comprend un exemple complet et fonctionnel : 1 182 enregistrements, 5 factions, 7 voies, 24 règles de constitution, 892 actifs approuvés, 2 profils d’entraînement. Un canon visuel RPG de science-fiction réaliste, entièrement organisé.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## Formats en aval

`sdlab` possède l’ensemble de données. La conversion de format est gérée par [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) : TRL, LLaVA, Qwen2-VL, JSONL, Parquet et plus encore. `repo-dataset` effectue le rendu ; il ne décide jamais de l’inclusion.

## Installation

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Nécessite Node.js 20+ et [ComfyUI](https://github.com/comfyanonymous/ComfyUI) sur localhost:8188 pour la génération.

### Essayez-le sans ComfyUI

Vous pouvez explorer toute la surface non liée à la génération (inspection, organisation, instantané, division, exportation) en utilisant le projet Star Freight inclus sans installer ComfyUI ni télécharger des poids SDXL.

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor` validates every project config (constitution, lanes, rubric, terminology) and reports eligibility without touching the GPU. Any command that mutates generated state accepts `--dry-run` to preview the effect first.

Si vous oubliez `--project`, l’interface en ligne de commande revient au premier projet qu’elle trouve sous `projects/` et affiche un avertissement — passez `--project` explicitement pour le supprimer.

### Reprise d’une exécution interrompue

Les longues exécutions peuvent être reprises sans refaire le travail terminé :

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

Les deux commandes fonctionnent car chaque emplacement écrit son entrée de manifeste de manière atomique lorsqu’il a terminé — un plantage en cours d’exécution ne corrompt jamais l’état partiel.

## Dépannage

Modes d’échec courants et solutions :

**`ECONNREFUSED 127.0.0.1:8188` sur n’importe quel `sdlab generate` / `sdlab run generate` / `sdlab batch generate`**
ComfyUI ne fonctionne pas. Démarrez ComfyUI (`python main.py --listen 127.0.0.1 --port 8188`) et confirmez avec `curl http://127.0.0.1:8188/system_stats`. Pour pointer vers un autre hôte/port, définissez `COMFY_URL=http://host:port`.

**`missing checkpoint` / `LoRA weight not found`**
Le nom de votre profil de flux de travail fait référence à un fichier de modèle qui ne se trouve pas dans le dossier `models/checkpoints/` ou `models/loras/` de ComfyUI. Ouvrez `projects/<project>/workflows/profiles/<profile>.json`, localisez le champ `checkpoint` ou `lora` et téléchargez soit le poids référencé, soit remplacez-le par celui que vous avez déjà. Relancez `sdlab project doctor --project <project>` pour confirmer la correction.

**Erreurs `sdlab project doctor`**
Doctor renvoie des codes d’erreur structurés. Les plus courants :
- `E_PROJECT_NOT_FOUND` — le répertoire du projet n’existe pas sous `projects/`. Vérifiez l’orthographe.
- `E_CONFIG_INVALID` — l’un des cinq fichiers de configuration JSON a échoué à la validation du schéma. Le champ `hint` indique le fichier et le champ défectueux.
- `E_RECORD_DRIFT` — l’empreinte de configuration d’un enregistrement ne correspond plus à sa source. Recurez ou reliez comme le suggère l’indication.

**Avertissement `No --project specified, falling back to <name>`**
Un avertissement modéré. Passez `--project <name>` explicitement pour sélectionner le bon projet et supprimer l’avertissement.

**Painterly / VRAM out-of-memory issues**
See `docs/internal/HANDOFF.md` for the painterly denoise tuning notes. In short: lower the denoise strength, reduce batch size, or switch to a smaller checkpoint in your workflow profile.

**Reporting bugs**
File an issue at https://github.com/mcp-tool-shop-org/style-dataset-lab/issues with your sdlab version (`sdlab --version`), Node version (`node -v`), the full command, and the structured error output. A bug-report template prefills the fields.

## Sécurité

Uniquement local. Pas de télémétrie, pas d’analyses, pas de demandes externes. Les images restent sur votre GPU et votre système de fichiers.

## Licence

MIT

---

Créé par <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
