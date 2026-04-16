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

Définissez vos règles visuelles. Générez des œuvres. Évaluez chaque image en fonction de ces règles. Livrez les résultats sous forme de données d'entraînement versionnées et auditables.

Style Dataset Lab relie les éléments que vous avez écrits concernant votre style artistique à l'ensemble de données sur lequel vous entraînez réellement votre modèle. Vous définissez une constitution : règles de silhouette, contraintes de palette, langage des matériaux, tout ce qui est important pour votre projet. Le pipeline génère des candidats, les évalue en fonction de ces règles, et regroupe les œuvres approuvées dans des ensembles de données reproductibles où chaque enregistrement explique pourquoi il a été inclus.

La boucle se referme : entraînez un modèle, générez de nouvelles sorties, évaluez-les en fonction des mêmes critères, réintégrez ce qui est validé. L'ensemble de données grandit et les règles restent valables.

## Le pipeline

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

Cette dernière commande est essentielle. Les sorties générées passent par le même processus de révision que tout le reste. La boucle se referme.

## Ce qu'il produit

Sept artefacts versionnés et vérifiés par checksum. Chacun est lié à ses prédécesseurs, ce qui vous permet de retracer tout enregistrement d'entraînement jusqu'à la règle qui l'a approuvé.

| Élément | Description |
|----------|-----------|
| **Snapshot** | Sélection d'enregistrements figée avec empreinte de configuration. Chaque inclusion a une raison explicite. |
| **Split** | Partitionnement entraînement/validation/test où les familles de sujets ne traversent jamais les limites. |
| **Export package** | Ensemble de données autonome : manifeste, métadonnées, images, divisions, description de l'ensemble de données et sommes de contrôle. |
| **Eval pack** | Tâches de vérification respectant les règles constitutionnelles : couverture des aspects, dérive interdite, ancres/références, cohérence des sujets. |
| **Training package** | Disposition prête pour l'entraînement via des adaptateurs (`diffusers-lora`, `generic-image-caption`). La même information, dans un format différent. |
| **Eval scorecard** | Indicateur de réussite/échec par tâche, basé sur l'évaluation des sorties générées par rapport aux ensembles d'évaluation. |
| **Implementation pack** | Exemples de prompts, échecs connus, tests de continuité et instructions de réintégration. |

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

## Sécurité

Utilisation locale uniquement. Aucune télémétrie, aucune analyse, aucune requête externe. Les images restent sur votre GPU et votre système de fichiers.

## Licence

MIT

---

Créé par <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
