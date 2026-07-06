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

Écrivez vos règles visuelles. Générez des œuvres d’art. Évaluez chaque image en fonction de ces règles. Diffusez les résultats sous forme de données d’entraînement versionnées et auditables, puis mettez à profit les modèles entraînés dans des flux de travail de production réels et renvoyez les meilleurs résultats dans votre corpus.

Style Dataset Lab relie ce que vous avez écrit concernant votre style artistique au jeu de données à partir duquel vous effectuez réellement l’entraînement, puis boucle le processus jusqu’à la production. Vous définissez une constitution : règles de silhouette, contraintes de palette, langage des matériaux, tout ce qui compte pour votre projet. Le pipeline génère des candidats, les évalue en fonction de ces règles et regroupe les éléments approuvés dans des jeux de données reproductibles où chaque enregistrement explique pourquoi il a été inclus.

Ensuite, l’environnement de travail de production prend le relais : compilez des briefs de génération à partir des données du projet, exécutez-les via ComfyUI, évaluez les résultats, produisez en série des feuilles d’expression et des planches d’ambiance, sélectionnez les meilleurs résultats et réintégrez-les en tant que nouveaux candidats. La boucle se ferme : produire, sélectionner, examiner, améliorer.

## Le pipeline

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

Cette dernière commande est essentielle. Les éléments sélectionnés repassent par le même processus d’évaluation que tous les autres. Le corpus s’enrichit et les règles sont respectées.

## Création du canon

Avant l’exécution du pipeline de jeu de données, l’espace de noms `sdlab canon *` transforme le référentiel d’entités canoniques de votre projet en les trois projections que l’entraînement et la production utilisent réellement, et verrouille les entrées qui ne doivent pas être modifiées.

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

`canon build` est adressable par contenu : sa sortie est indexée par un `canon_sha` et mise en cache, de sorte qu’une reconstruction du canon non modifié se fait instantanément. `canon freeze` atteste de chaque blocage par rapport à une version spécifique et l’ajoute à un journal d’audit `freeze-events.jsonl` : les entrées `frozen` refusent purement et simplement la régénération, les entrées `soft-advisory` refusent par défaut (contournement avec `--i-know`). `canon drift` recalcule le hachage de chaque entrée surveillée et signale tout ce qui a changé depuis la dernière reconstruction propre.

Flux de travail complet dans le manuel : [Canon build](handbook/canon-build/), [Canon freeze](handbook/canon-freeze/) et [Two-LoRA stacking](handbook/two-lora-stacking/).

## Ce que cela produit

Sept artefacts de jeu de données et un environnement de travail de production complet. Chaque artefact est lié à ses prédécesseurs, ce qui vous permet de retracer tout enregistrement d’entraînement jusqu’à la règle qui l’a approuvé.

| Artefact | Ce que c’est |
|----------|-----------|
| **Snapshot** | Sélection des enregistrements figés avec empreinte de configuration. Chaque inclusion a une raison explicite. |
| **Split** | Partitionnement entraînement/validation/test où les familles de sujets ne franchissent jamais les frontières. |
| **Export package** | Jeu de données autonome : manifeste, métadonnées, images, partitions, fiche d’informations du jeu de données, sommes de contrôle. |
| **Eval pack** | Tâches de test tenant compte du canon : couverture des voies, dérive interdite, ancrage/or, continuité des sujets. |
| **Training package** | Disposition prête pour l’entraîneur via des adaptateurs (`diffusers-lora`, `generic-image-caption`). Même vérité, format différent. |
| **Eval scorecard** | Résultat de réussite/échec par tâche à partir de l’évaluation des résultats générés par rapport aux ensembles d’évaluation. |
| **Implementation pack** | Exemples d’invites, échecs connus, tests de continuité et directives de réintégration. |

L’environnement de travail de production ajoute :

| Surface | Ce que cela fait |
|---------|-------------|
| **Compiled brief** | Instruction de génération déterministe à partir du profil de flux de travail + des données du projet. |
| **Run** | Artefact d’exécution figé : bref + graines + sorties ComfyUI + manifeste. |
| **Critique** | Évaluation structurée multidimensionnelle des résultats de l’exécution par rapport au canon. |
| **Batch** | Production coordonnée multi-slots (feuilles d’expression, planches d’ambiance, ensembles de silhouettes). |
| **Selection** | Artefact de décision créative : quels éléments ont été choisis, pourquoi et d’où ils proviennent. |
| **Re-ingest** | Les éléments sélectionnés sont renvoyés en tant qu’enregistrements candidats avec la provenance complète de la génération. |

## Pourquoi cela existe

Les données d’entraînement constituent l’artefact le plus important dans tout pipeline d’IA visuelle. Mais la plupart des données d’entraînement ne sont qu’un dossier d’images sans historique, sans suivi de l’évaluation et sans lien avec les règles de style qu’elles étaient censées suivre.

Style Dataset Lab rend le lien explicite. Votre constitution définit les règles. Votre barème définit les dimensions d’évaluation. Vos enregistrements de sélection consignent l’évaluation. Votre liaison canonique prouve le lien. Et votre jeu de données conserve tout cela sous forme de vérité structurée, interrogeable et reproductible.

Le résultat pratique : lorsque votre LoRA dérive, vous pouvez demander *pourquoi*. Lorsque votre prochain cycle d’entraînement a besoin de meilleures données, vous savez exactement quels enregistrements sont presque corrects et quelle règle unique ils ont violée. Lorsqu’un nouveau membre de l’équipe demande quelle est la langue visuelle du projet, la réponse n’est pas un tableau Figma, mais une constitution consultable avec 1 182 exemples notés.

## Cinq domaines, règles réelles

Pas de modèles d’espace réservé. Chaque domaine est livré avec des règles de constitution de qualité professionnelle, des définitions de voies, des barèmes d’évaluation et un vocabulaire de groupe.

| Domaine | Voies | Ce qui est évalué |
|--------|-------|-----------------|
| **game-art** | personnage, environnement, accessoire, interface utilisateur, vaisseau, intérieur, équipement | Silhouette à l’échelle du jeu, lisibilité de la faction, usure et vieillissement |
| **character-design** | portrait, corps entier, rotation, feuille d’expression, pose d’action | Proportions, logique des costumes, personnalité, clarté des gestes |
| **creature-design** | concept, orthographique, étude détaillée, action, référence d’échelle, habitat | Anatomie, logique évolutive, distinction de la silhouette |
| **architecture** | extérieur, intérieur, paysage urbain, détail structurel, ruine, paysage | Structure, cohérence des matériaux, perspective, cohérence de l’époque |
| **vehicle-mech** | extérieur, cockpit, composant, schéma, feuille de silhouette, variante de dommage | Logique mécanique, langage du design, points d’accès, récit des dommages |

## Structure du projet

Chaque projet est autonome. Cinq fichiers de configuration JSON définissent les règles ; tout le reste sont des données.

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

Il ne s’agit pas d’objectifs à atteindre. Elles sont appliquées.

- **Les instantanés sont immuables.** L’empreinte de configuration (SHA-256) prouve qu’aucun changement n’a été apporté.
- **Les séparations empêchent les fuites.** Les familles de sujets (par identité, lignée ou suffixe d’ID) ne traversent jamais les limites des partitions.
- **Les manifestes sont des contrats figés.** Hachage d’exportation + empreinte de configuration. Si quoi que ce soit change, créez-en un nouveau.
- **Les adaptateurs ne peuvent pas modifier la vérité.** Disposition différente, mêmes enregistrements. Pas d’ajouts, pas de suppressions, pas de reclassification.
- **Les résultats générés sont réintégrés via une revue.** Pas de contournement. Organisez et liez comme tout le reste.

## Star Freight

Le dépôt inclut un exemple complet fonctionnel : 1 182 enregistrements, 5 factions, 7 voies, 24 règles de constitution, 892 actifs approuvés, 2 profils d’entraînement. Un canon visuel RPG de science-fiction réaliste, entièrement organisé.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## Formats en aval

`sdlab` est propriétaire du jeu de données. La conversion de format est gérée par [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) : TRL, LLaVA, Qwen2-VL, JSONL, Parquet et plus encore. `repo-dataset` effectue le rendu ; il ne décide jamais de l’inclusion.

## Installation

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Nécessite Node.js 20+ et [ComfyUI](https://github.com/comfyanonymous/ComfyUI) sur localhost:8188 pour la génération.

### Essayez-le sans ComfyUI

Vous pouvez explorer toute la surface non liée à la génération (inspection, organisation, instantané, séparation, exportation) en utilisant le projet Star Freight inclus sans installer ComfyUI ni télécharger des poids SDXL.

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor` valide chaque configuration de projet (constitution, voies, rubriques, terminologie) et signale l’éligibilité sans toucher au GPU. Toute commande qui modifie l’état généré accepte l’option `--dry-run` pour prévisualiser d’abord l’effet.

Si vous oubliez `--project`, l’interface de ligne de commande revient au premier projet qu’elle trouve dans `projects/` et affiche un avertissement ; passez explicitement `--project` pour le supprimer.

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

Les deux commandes fonctionnent car chaque emplacement écrit son entrée de manifeste de manière atomique lorsqu’il est terminé ; un plantage en cours d’exécution ne corrompt jamais l’état partiel.

## Dépannage

Modes d’échec courants et solutions :

**`ECONNREFUSED 127.0.0.1:8188` pour toute commande `sdlab generate` / `sdlab run generate` / `sdlab batch generate`**
ComfyUI n’est pas en cours d’exécution. Démarrez ComfyUI (`python main.py --listen 127.0.0.1 --port 8188`) et confirmez avec `curl http://127.0.0.1:8188/system_stats`. Pour pointer vers un autre hôte/port, définissez `COMFY_URL=http://host:port`.

**`missing checkpoint` / `LoRA weight not found`**
Votre profil de flux de travail nomme un fichier modèle qui ne se trouve pas dans le dossier `models/checkpoints/` ou `models/loras/` de ComfyUI. Ouvrez `projects/<project>/workflows/profiles/<profile>.json`, localisez le champ `checkpoint` ou `lora`, et téléchargez soit le poids référencé, soit remplacez-le par un que vous avez déjà. Réexécutez `sdlab project doctor --project <project>` pour confirmer la correction.

**Erreurs de `sdlab project doctor`**
Doctor renvoie des codes d’erreur structurés. Les plus courants :
- `E_PROJECT_NOT_FOUND` — le répertoire du projet n’existe pas dans `projects/`. Vérifiez l’orthographe.
- `E_CONFIG_INVALID` — l’un des cinq fichiers de configuration JSON a échoué à la validation du schéma. Le champ `hint` indique le fichier et le champ défectueux.
- `E_RECORD_DRIFT` — l’empreinte de configuration d’un enregistrement ne correspond plus à sa source. Réorganisez ou reliez comme le suggère l’indice.

**`No --project specified, falling back to <name>`**
Un simple avertissement. Passez explicitement `--project <name>` pour sélectionner le bon projet et supprimer l’avertissement.

**Problèmes de mémoire VRAM / problèmes d’aspect pictural**
Consultez `docs/internal/HANDOFF.md` pour les notes sur le réglage du débruitage pictural. En résumé : diminuez la force du débruitage, réduisez la taille du lot ou passez à un point de contrôle plus petit dans votre profil de flux de travail.

**Signalement des bogues**
Créez un problème sur https://github.com/mcp-tool-shop-org/style-dataset-lab/issues avec votre version de sdlab (`sdlab --version`), la version de Node (`node -v`), la commande complète et la sortie d’erreur structurée. Un modèle de rapport de bogue préremplit les champs.

## Sécurité

Uniquement local. Pas de télémétrie, pas d’analyses, pas de requêtes externes. Les images restent sur votre GPU et votre système de fichiers.

## Licence

MIT

---

Créé par <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
