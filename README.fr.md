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

Une chaîne de production pour la création de jeux de données visuels : des règles de base aux invites structurées, en passant par la génération avec ComfyUI, jusqu'aux données d'entraînement sélectionnées et conformes aux règles.

## Qu'est-ce que c'est ?

Une **chaîne de production** pour la création de jeux de données visuels structurés. Vous définissez des règles de style (règles de base), rédigez des invites, générez avec ComfyUI, sélectionnez les données avec un système de notation par dimension, associez les jugements aux règles de base et exportez dans 10 formats via [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset).

Cette chaîne de production est indépendante du jeu. Chaque jeu dispose de son propre répertoire de données sous `games/<nom>/`; les 13 scripts et les modèles vierges sont partagés. Chaque élément produit contient trois informations.

1. **Pixels de l'image** : générés par ComfyUI avec une traçabilité complète (point de contrôle, LoRA, graine, échantillonneur, cfg).
2. **Explication canonique** : pourquoi cet élément est conforme ou non au style, basé sur une constitution du style.
3. **Jugement de qualité** : approuvé/refusé avec des scores par dimension et des règles citées.

## Modèle de sécurité

**Uniquement local.** style-dataset-lab communique avec ComfyUI sur `localhost:8188` et ne fait jamais de requêtes réseau externes. Pas de télémétrie, pas d'analyses, pas de communication avec un serveur distant. La génération d'images se fait entièrement sur votre GPU. Les enregistrements et les données canoniques restent sur votre système de fichiers.

## Ce que le paquet npm contient

`npm install @mcptoolshop/style-dataset-lab` vous donne :

- **13 scripts** -- génération, sélection, comparaison, application des règles de base, style pictural, génération d'identités, génération ControlNet/IP-Adapter, sélection en masse, migration.
- **Modèles vierges** -- constitution de base, grille d'évaluation et ensemble d'exemples d'invites dans le dossier `templates/`.

Le paquet npm **ne contient pas** les données du jeu. Clonez le dépôt si vous souhaitez l'exemple de Star Freight (1 182 enregistrements, 28 séries d'invites, 18 catégories visuelles).

## Installation

```bash
# Get the pipeline scripts + templates
npm install @mcptoolshop/style-dataset-lab

# Or clone the repo for the Star Freight example data
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
npm install
```

Pour démarrer un nouveau jeu à partir des modèles :

```bash
# Copy templates into your game directory
mkdir -p games/my-game/{records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
cp -r templates/canon games/my-game/canon
cp templates/inputs/prompts/example-wave.json games/my-game/inputs/prompts/wave1.json
# Edit the canon and prompts, then generate
```

## Structure du dépôt monorepo

La chaîne de production se trouve dans les dossiers `scripts/` et `templates/`. Chaque jeu se trouve dans le dossier `games/<nom>/` et possède ses propres règles de base, enregistrements et ressources. Les scripts acceptent l'argument `--game <nom>` (par défaut : `star-freight`).

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

## Flux de travail de la chaîne de production

La chaîne de production complète, des règles de base à l'exportation des données d'entraînement :

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

## Ajout d'un nouveau jeu

```bash
# Create structure and copy blank templates
mkdir -p games/my-game/{records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
cp -r templates/canon games/my-game/canon
cp templates/inputs/prompts/example-wave.json games/my-game/inputs/prompts/wave1.json

# Edit your canon/constitution.md and canon/review-rubric.md
# Edit your prompt pack, then run the pipeline with --game my-game
```

## Structure du répertoire par jeu

Chaque répertoire `games/<nom>/` contient :

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

## Configuration de la génération

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

Modes de génération supplémentaires : ControlNet (guidé par la pose/la profondeur), IP-Adapter (guidé par une référence) et paquets d'identité (cohérence des personnages nommés).

## Prérequis

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) en cours d'exécution sur localhost:8188
- Point de contrôle DreamShaper XL Turbo + LoRA ClassipeintXL
- Node.js 20+
- [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) pour l'exportation des données d'entraînement

## Licence

MIT

---

Créé par <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
