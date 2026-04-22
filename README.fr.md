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

Définissez vos règles visuelles. Générez des images. Évaluez chaque image par rapport à ces règles. Envoyez les résultats sous forme de données d'entraînement versionnées et auditables, puis mettez les modèles entraînés en œuvre dans des flux de travail de production réels et réinjectez les meilleurs résultats dans votre corpus.

Style Dataset Lab relie les éléments que vous avez écrits concernant votre style artistique à l'ensemble de données sur lequel vous entraînez réellement votre modèle. Vous définissez une constitution : règles de silhouette, contraintes de palette, langage des matériaux, tout ce qui est important pour votre projet. Le pipeline génère des candidats, les évalue en fonction de ces règles, et regroupe les œuvres approuvées dans des ensembles de données reproductibles où chaque enregistrement explique pourquoi il a été inclus.

Ensuite, le poste de travail de production prend le relais : compilez les instructions de génération à partir des informations du projet, exécutez-les via ComfyUI, critiquez les résultats, produisez en lot des feuilles d'expressions et des planches d'environnement, sélectionnez les meilleurs résultats et réintégrez-les en tant que nouveaux candidats. Le cycle se referme : production, sélection, révision, amélioration.

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

Cette dernière commande est essentielle. Les résultats sélectionnés sont réexaminés selon le même processus que tous les autres éléments. Le corpus s'enrichit et les règles restent valables.

## Ce qu'il produit

Sept artefacts de jeu de données et un poste de travail de production complet. Chaque artefact est lié à ses prédécesseurs, ce qui vous permet de retracer tout enregistrement d'entraînement jusqu'à la règle qui l'a approuvé.

| Élément | Description |
|----------|-----------|
| **Snapshot** | Sélection d'enregistrements figée avec empreinte de configuration. Chaque inclusion a une raison explicite. |
| **Split** | Partitionnement entraînement/validation/test où les familles de sujets ne traversent jamais les limites. |
| **Export package** | Ensemble de données autonome : manifeste, métadonnées, images, divisions, description de l'ensemble de données et sommes de contrôle. |
| **Eval pack** | Tâches de vérification respectant les règles constitutionnelles : couverture des aspects, dérive interdite, ancres/références, cohérence des sujets. |
| **Training package** | Disposition prête pour l'entraînement via des adaptateurs (`diffusers-lora`, `generic-image-caption`). La même information, dans un format différent. |
| **Eval scorecard** | Indicateur de réussite/échec par tâche, basé sur l'évaluation des sorties générées par rapport aux ensembles d'évaluation. |
| **Implementation pack** | Exemples de prompts, échecs connus, tests de continuité et instructions de réintégration. |

Le poste de travail de production ajoute :

| Surface | Ce que cela fait |
|---------|-------------|
| **Compiled brief** | Génération déterministe à partir du profil de flux de travail + des informations du projet. |
| **Run** | Artefact d'exécution figé : instruction + graines + résultats ComfyUI + manifeste. |
| **Critique** | Évaluation structurée et multidimensionnelle des résultats par rapport à la référence. |
| **Batch** | Production coordonnée en plusieurs flux (feuilles d'expressions, planches d'environnement, ensembles de silhouettes). |
| **Selection** | Artefact de décision créative : quels résultats ont été choisis, pourquoi et d'où ils proviennent. |
| **Re-ingest** | Les résultats sélectionnés sont renvoyés en tant qu'enregistrements candidats avec une traçabilité complète de la génération. |

## Pourquoi cela existe

Les données d'entraînement sont l'élément le plus important dans tout pipeline d'IA visuelle. Mais la plupart des données d'entraînement ne sont qu'un dossier d'images sans historique, sans trace de jugement et sans lien avec les règles de style qu'elles étaient censées suivre.

Style Dataset Lab établit ce lien de manière explicite. Votre constitution définit les règles. Votre grille d'évaluation définit les dimensions de l'évaluation. Vos enregistrements de curation consignent le jugement. Votre canon de référence prouve le lien. Et votre ensemble de données transmet tout cela sous forme de vérité structurée, consultable et reproductible.

Le résultat pratique : lorsque votre LoRA dérive, vous pouvez demander *pourquoi*. Lorsque votre prochaine phase d'entraînement a besoin de meilleures données, vous savez exactement quels enregistrements sont proches de la limite et quelle règle unique ils ont manquée. Lorsqu'un nouveau membre de l'équipe demande quelle est la langue visuelle du projet, la réponse n'est pas un tableau Figma, mais une constitution consultable avec 1 182 exemples notés.

## Cinq domaines, règles réelles

Ce ne sont pas des modèles génériques. Chaque domaine est fourni avec des règles de constitution, des définitions de catégories, des grilles d'évaluation et un vocabulaire de groupe de qualité professionnelle.

| Domaine | Aspects | Ce qui est évalué |
|--------|-------|-----------------|
| **game-art** | personnage, environnement, accessoire, interface utilisateur, vaisseau, intérieur, équipement | Silhouette à l'échelle du gameplay, interprétation de la faction, usure et vieillissement. |
| **character-design** | portrait, corps entier, vue de face, feuille d'expressions, pose d'action | Proportions, logique des costumes, personnalité, clarté des gestes. |
| **creature-design** | concept, orthographique, étude de détail, action, référence d'échelle, habitat | Anatomie, logique évolutive, distinction de la silhouette. |
| **architecture** | extérieur, intérieur, paysage urbain, détail structurel, ruine, paysage | Structure, cohérence des matériaux, perspective, cohérence de l'époque. |
| **vehicle-mech** | extérieur, cockpit, composant, schéma, feuille de silhouette, variante endommagée | Logique mécanique, langage de conception fonctionnelle, points d'accès, description des dommages. |

## Structure du projet

Chaque projet est autonome. Cinq fichiers de configuration JSON définissent les règles ; le reste est constitué de données.

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

Ce ne sont pas des aspirations. Elles sont appliquées.

- **Les instantanés sont immuables.** L'empreinte de configuration (SHA-256) prouve qu'il n'y a eu aucun changement.
- **Les partitions empêchent les fuites.** Les familles de sujets (par identité, lignée ou suffixe d'ID) ne traversent jamais les limites des partitions.
- **Les manifestes sont des contrats figés.** Hash d'exportation + empreinte de configuration. Si quelque chose change, créez-en un nouveau.
- **Les adaptateurs ne peuvent pas modifier la vérité.** Disposition différente, mêmes enregistrements. Pas d'ajouts, pas de suppressions, pas de reclassements.
- **Les sorties générées sont soumises à une révision.** Pas de contournement. Curatez et intégrez comme tout le reste.

## Star Freight

Le dépôt comprend un exemple de fonctionnement complet : 1182 enregistrements, 5 factions, 7 voies, 24 règles constitutionnelles, 892 ressources approuvées, 2 profils de formation. Un corpus visuel de jeu de rôle de science-fiction, entièrement organisé.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## Formats compatibles

`sdlab` est propriétaire de l'ensemble de données. La conversion de format est gérée par [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) : TRL, LLaVA, Qwen2-VL, JSONL, Parquet, et plus encore. `repo-dataset` effectue la conversion ; il ne décide jamais de l'inclusion.

## Installation

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Nécessite Node.js 20+ et [ComfyUI](https://github.com/comfyanonymous/ComfyUI) installé localement sur le port 8188 pour la génération.

### Essayez-le sans ComfyUI

Vous pouvez explorer toute la surface de non-génération (inspection, curation, instantané, division, exportation) à l'aide du projet Star Freight intégré, sans installer ComfyUI ni télécharger de poids SDXL.

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor` valide chaque configuration de projet (constitution, voies, grille, terminologie) et signale l'éligibilité sans toucher au GPU. Toute commande qui modifie l'état généré accepte l'option `--dry-run` pour prévisualiser l'effet au préalable.

Si vous oubliez `--project`, l'interface de ligne de commande revient au premier projet qu'elle trouve dans le répertoire `projects/` et affiche un avertissement. Utilisez explicitement l'option `--project` pour le supprimer.

### Reprise d'une exécution interrompue

Les longues exécutions peuvent être reprises sans avoir à refaire le travail déjà effectué :

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

Les deux commandes fonctionnent car chaque emplacement écrit son entrée de manifeste de manière atomique lorsqu'il termine son travail. Ainsi, un crash pendant l'exécution n'endommage jamais l'état partiel.

## Dépannage

Modes de défaillance courants et solutions :

**`ECONNREFUSED 127.0.0.1:8188` pour toute commande `sdlab generate` / `sdlab run generate` / `sdlab batch generate`**
ComfyUI n'est pas en cours d'exécution. Démarrez ComfyUI (`python main.py --listen 127.0.0.1 --port 8188`) et vérifiez avec `curl http://127.0.0.1:8188/system_stats`. Pour pointer vers un autre hôte/port, définissez `COMFY_URL=http://host:port`.

**`missing checkpoint` / `LoRA weight not found`**
Votre profil de flux de travail fait référence à un fichier de modèle qui ne se trouve pas dans les dossiers `models/checkpoints/` ou `models/loras/` de ComfyUI. Ouvrez `projects/<project>/workflows/profiles/<profile>.json`, localisez le champ `checkpoint` ou `lora` et téléchargez le fichier de poids référencé ou remplacez-le par un fichier que vous avez déjà. Relancez `sdlab project doctor --project <project>` pour confirmer la correction.

**`sdlab project doctor` errors**
Doctor renvoie des codes d'erreur structurés. Les plus courants sont :
- `E_PROJECT_NOT_FOUND` — le répertoire du projet n'existe pas sous `projects/`. Vérifiez l'orthographe.
- `E_CONFIG_INVALID` — l'un des cinq fichiers de configuration JSON n'a pas réussi la validation du schéma. Le champ `hint` indique le fichier et le champ concernés.
- `E_RECORD_DRIFT` — l'empreinte de configuration d'un enregistrement ne correspond plus à sa source. Réexaminez-le ou réassociez-le comme suggéré dans l'invite.

**`No --project specified, falling back to <name>`**
Un avertissement mineur. Utilisez explicitement l'option `--project <name>` pour sélectionner le projet approprié et supprimer l'avertissement.

**Problèmes liés au rendu / erreurs de mémoire insuffisante (VRAM)**
Consultez le fichier `docs/internal/HANDOFF.md` pour les notes de configuration du rendu. En résumé : réduisez l'intensité du débruitage, diminuez la taille des lots ou utilisez un modèle plus petit dans votre profil de flux de travail.

**Signalement de bogues**
Signalez un problème sur https://github.com/mcp-tool-shop-org/style-dataset-lab/issues en indiquant votre version de sdlab (`sdlab --version`), la version de Node.js (`node -v`), la commande complète et la sortie d'erreur structurée. Un modèle de rapport de bogue préremplit les champs.

## Sécurité

Utilisation locale uniquement. Aucune télémétrie, aucune analyse, aucune requête externe. Les images restent sur votre GPU et votre système de fichiers.

## Licence

Licence MIT.

---

Créé par <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
