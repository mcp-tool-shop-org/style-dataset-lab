<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.md">English</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/style-dataset-lab/readme.png" width="400">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@mcptoolshop/style-dataset-lab"><img src="https://img.shields.io/npm/v/@mcptoolshop/style-dataset-lab" alt="npm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

# style-dataset-lab

Transformez les éléments visuels approuvés en ensembles de données versionnés, validés, divisés, exportables et destinés à l'évaluation.

## Qu'est-ce que c'est ?

Un **système de production de données visuelles et un pipeline**. Définissez l'apparence de votre projet. Appliquez des règles constitutionnelles. Créez des ensembles de données reproductibles avec des divisions sécurisées contre les fuites. Générez des ensembles d'évaluation pour la vérification future des modèles.

Le pipeline produit quatre éléments :

| Élément | Description |
|----------|-----------|
| **Snapshot** | Sélection de données éligibles, figée et identifiée de manière unique. Chaque inclusion a une justification explicite. |
| **Split** | Partition train/validation/test sécurisée contre les fuites. Les données partageant la même famille de sujets sont toujours regroupées dans la même partition. |
| **Export package** | Ensemble de données autonome : manifeste, métadonnées, images, divisions, description de l'ensemble de données et sommes de contrôle. |
| **Eval pack** | Tâches de vérification respectant les règles constitutionnelles : couverture des aspects, dérive interdite, ancres/références, cohérence des sujets. |

Chaque élément du pipeline contient trois informations :

1. **Traçabilité** – historique complet de la génération (point de contrôle, LoRA, seed, échantillonneur, cfg, timing).
2. **Conformité aux règles constitutionnelles** – quelles règles constitutionnelles cet élément respecte, ne respecte pas ou respecte partiellement.
3. **Évaluation de la qualité** – approuvé/refusé/limite, avec des scores par dimension.

Fonctionne pour les illustrations de jeux, la conception de personnages, la conception de créatures, l'architecture, les concepts de véhicules/robots, et tout domaine où la production visuelle doit rester conforme aux spécifications.

## Démarrage rapide

```bash
# Install the CLI + pipeline
npm install -g @mcptoolshop/style-dataset-lab

# Scaffold a new project
sdlab init my-project --domain character-design

# Validate the project structure
sdlab project doctor --project my-project
```

Domaines disponibles : `game-art`, `character-design`, `creature-design`, `architecture`, `vehicle-mech` ou `generic`.

## Interface en ligne de commande (CLI)

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

Toutes les commandes acceptent `--project <nom>` (par défaut : `star-freight`).

## Modèle du projet

Chaque projet est un répertoire autonome sous `projects/`, avec sa propre constitution, sa configuration et ses données :

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

1. **Définir la constitution** – rédigez votre constitution de style et votre grille d'évaluation.
2. **Générer** – ComfyUI produit des candidats avec une traçabilité complète.
3. **Sélectionner** – approuvez/refusez avec des scores par dimension et des modes de défaillance.
4. **Associer** – liez chaque élément aux règles constitutionnelles avec des verdicts d'acceptation/rejet/partiel.
5. **Instantané** – figez les données éligibles dans une sélection déterministe et identifiée de manière unique.
6. **Diviser** – partitionnez en train/validation/test avec isolement des sujets et équilibre des aspects.
7. **Exporter** – créez un package autonome avec un manifeste, des métadonnées, des images et des sommes de contrôle.
8. **Évaluer** – générez des instruments de test respectant les règles constitutionnelles pour la vérification du modèle.

La conversion de format en aval (TRL, LLaVA, Parquet, etc.) est gérée par [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset). `sdlab` possède la vérité des données ; `repo-dataset` la transforme en formats spécialisés.

## Modèles de domaine

Chaque modèle de domaine est fourni avec des définitions d'aspects, des règles constitutionnelles, des grilles d'évaluation et des structures terminologiques conçues pour ce contexte de production :

| Domaine | Aspects | Préoccupations clés |
|--------|-------|-------------|
| **game-art** | personnage, environnement, accessoire, interface utilisateur, vaisseau, intérieur, équipement | Silhouette à l'échelle du gameplay, différenciation des factions, usure/vieillissement |
| **character-design** | portrait, corps entier, vue de face, feuille d'expressions, pose d'action | Précision des proportions, logique des costumes, expression de la personnalité, clarté des gestes |
| **creature-design** | concept, orthographique, étude de détail, action, référence d'échelle, habitat | Plausibilité anatomique, logique évolutive, distinction des silhouettes |
| **architecture** | extérieur, intérieur, paysage urbain, détail structurel, ruine, paysage | Plausibilité structurelle, cohérence des matériaux, perspective, cohérence de l'époque |
| **vehicle-mech** | extérieur, cockpit, composant, schéma, feuille de silhouette, variante endommagée | Logique mécanique, langage de conception fonctionnelle, points d'accès, description des dommages. |

## Production de l'ensemble de données

Structure complète de l'ensemble de données : instantané, division, exportation, évaluation.

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

Les **instantanés** figent une sélection déterministe d'enregistrements éligibles. Chaque inclusion a une trace de raison. Les empreintes de configuration garantissent la reproductibilité.

Les **divisions** attribuent les enregistrements aux partitions d'entraînement/validation/test, avec une isolation des sujets (aucune famille de sujets n'apparaît dans plusieurs divisions) et une distribution équilibrée par "voie". Un générateur de nombres pseudo-aléatoires (PRNG) initialisé garantit des résultats identiques à partir de la même initialisation.

Les **packages d'exportation** sont autonomes : manifeste, metadata.jsonl, images (liens symboliques ou copies), divisions, fiche de l'ensemble de données (Markdown + JSON), et sommes de contrôle au format BSD. Tout le nécessaire pour reconstruire l'ensemble de données à partir de zéro.

Les **packs d'évaluation** sont des outils de test standardisés, prenant en compte le contexte, avec quatre types de tâches : couverture des "voies", dérive interdite, ancres/références, et continuité des sujets. Ils prouvent que la structure de l'ensemble de données alimente l'évaluation future des modèles, et ne se contente pas de décharger des fichiers.

Exportation vers des formats compatibles via [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) (TRL, LLaVA, Qwen2-VL, JSONL, Parquet, etc.). `repo-dataset` gère la conversion de format ; `sdlab` est responsable de la vérité des données.

## Exemple Star Freight

Clonez le dépôt pour un exemple fonctionnel complet : 1182 enregistrements, 28 séries de prompts, 5 factions, 7 "voies", 24 règles constitutionnelles, et 892 ressources approuvées provenant d'un RPG de science-fiction réaliste.

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

## Migration depuis la version 1.x

La version 2.0 renomme `games/` en `projects/` et `--game` en `--project` :

```bash
# Rename your data directory
mv games projects

# --game still works with a deprecation warning (removed in v3.0)
sdlab bind --game star-freight   # works, prints warning
sdlab bind --project star-freight # canonical form
```

## Modèle de sécurité

**Uniquement local.** Communique avec ComfyUI sur `localhost:8188`. Pas de télémétrie, pas d'analyses, pas de requêtes externes. Les images restent sur votre GPU et votre système de fichiers.

## Prérequis

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) en cours d'exécution sur localhost:8188
- Point de contrôle DreamShaper XL Turbo + LoRA ClassipeintXL
- Node.js 20+
- [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) pour l'exportation des données d'entraînement

## Licence

MIT

---

Créé par <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
