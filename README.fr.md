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

Fabrique de jeux de données visuels : génère, organise et exporte des données d'entraînement multimodales pour l'affinage des modèles de langage visuels (VLM).

## Qu'est-ce que c'est ?

Une boîte à outils pour créer une **vérité visuelle entraînable**. Chaque élément contient trois informations :

1. **Pixels de l'image** : générés par ComfyUI avec une traçabilité complète (point de contrôle, LoRA, graine, échantillonneur, cfg).
2. **Explication canonique** : pourquoi cet élément est conforme ou non au style, basé sur une constitution du style.
3. **Jugement de qualité** : approuvé/refusé avec des scores par dimension et des règles citées.

La sortie est intégrée à [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) pour produire des données d'entraînement multimodales dans 10 formats : TRL, LLaVA, Qwen2-VL, Axolotl, LLaMA-Factory, ShareGPT, paires RLHF, DPO, légende et classification.

## Modèle de sécurité

**Uniquement local.** style-dataset-lab communique avec ComfyUI sur `localhost:8188` et ne fait jamais de requêtes réseau externes. Pas de télémétrie, pas d'analyses, pas de communication avec un serveur distant. La génération d'images se fait entièrement sur votre GPU. Les enregistrements et les données canoniques restent sur votre système de fichiers.

## Statistiques du jeu de données

| Métrique | Valeur |
|--------|-------|
| Enregistrements organisés | 1,182 |
| Nombre total d'éléments | 2 571 (893 approuvés, 887 variantes picturales) |
| Séquences de prompts | 28 |
| Catégories visuelles | 18 (costumes, bateaux, intérieurs, équipements, environnements, espèces, stations, signalisation, éclairage, cargaison, architecture, créatures, surfaces, vie quotidienne, planétaire, dommages/réparations, biologie extraterrestre, détails de vie) |
| Comparaisons par paires | 6 réalisées par des humains + 71 synthétiques |
| Types de refus distincts | 30+ |
| Système de paquets d'identité | Personnages nommés avec ADN de faction, grade et ancres visuelles. |
| Formats d'exportation | 10 (via @mcptoolshop/repo-dataset) |

## Installation

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Clonez ensuite un projet ou initialisez un nouvel espace de travail de jeu de données :

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab my-dataset
cd my-dataset
npm install
```

## Flux de travail

```bash
# 1. Start ComfyUI
# (point it at your checkpoint + LoRA setup)

# 2. Generate candidates from a prompt pack
npm run generate -- inputs/prompts/wave1.json
npm run generate -- inputs/prompts/wave1.json --dry-run

# 3. Generate identity-packet characters
npm run generate:identity -- inputs/identity-packets/wave27a-identity-spine.json

# 4. Generate painterly variants of approved assets
npm run painterly -- <asset_id>

# 5. Curate -- approve, reject, or mark borderline
npm run curate -- <asset_id> approved "explanation" --scores "silhouette:0.9,palette:0.8"
npm run curate -- <asset_id> rejected "explanation" --failures "too_clean,wrong_material"

# 6. Bind canon explanations to assets
npm run canon-bind -- <asset_id>

# 7. Record pairwise comparisons
npm run compare -- <asset_a> <asset_b> a "A has better faction read because..."

# 8. Export training data via repo-dataset
npm run export
npm run inspect
npm run validate
```

## Structure des répertoires

```
canon/                  Style constitution, review rubric, identity gates, species canon
inputs/
  prompts/              Prompt packs per wave (JSON: subjects, variations, defaults)
  references/           IP-Adapter reference images
  control/              ControlNet control images
  control-guides/       ControlNet guide overlays
  identity-packets/     Named character identity spines (faction DNA, rank, visual anchors)
outputs/
  candidates/           Raw generations (gitignored)
  approved/             Curated approved (gitignored)
  rejected/             Curated rejected (gitignored)
  borderline/           Curated borderline (gitignored)
  painterly/            Painterly-style variants (gitignored)
records/                Per-asset JSON (provenance + judgment + canon binding)
comparisons/            A-vs-B preference judgments
exports/                repo-dataset output (gitignored)
scripts/                generate, curate, compare, canon-bind, painterly, identity gen
workflows/              Reusable ComfyUI workflow templates
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
