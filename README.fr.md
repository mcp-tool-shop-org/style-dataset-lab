<p align="center">
  <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.md">English</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
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

Écrivez vos règles visuelles. Générez des œuvres d’art. Évaluez chaque image en fonction de ces règles. Diffusez les résultats sous forme de données d’entraînement versionnées et auditables, puis mettez en œuvre les modèles entraînés dans des flux de travail de production réels et réinjectez les meilleurs résultats dans votre corpus.

Style Dataset Lab relie ce que vous avez écrit concernant votre style artistique à l’ensemble de données à partir duquel vous effectuez réellement l’entraînement, puis boucle le processus jusqu’à la production. Vous définissez une constitution : règles de silhouette, contraintes de palette, langage des matériaux, tout ce qui compte pour votre projet. Le pipeline génère des candidats, les évalue en fonction de ces règles et regroupe les éléments approuvés dans des ensembles de données reproductibles où chaque enregistrement explique pourquoi il a été inclus.

Ensuite, l’atelier de production prend le relais : compilez des briefs de génération à partir des données du projet, exécutez-les dans ComfyUI, critiquez les résultats, produisez en série des feuilles d’expression et des planches d’environnement, sélectionnez les meilleurs résultats et réintégrez-les en tant que nouveaux candidats. La boucle se ferme : produire, sélectionner, examiner, améliorer.

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

Cette dernière commande est essentielle. Les résultats sélectionnés repassent par le même processus d’examen que tous les autres. Le corpus s’enrichit et les règles sont respectées.

## La chaîne d’actifs : exportations 3D en tant que données d’entraînement

`sdlab ingest` accepte les images brutes sans vérification. `sdlab asset ingest` exige un **contrat**.

Lorsqu’un actif 3D passe son étape de validation, le fait de le rendre à partir de N angles vous donne une vue d’ensemble cohérente *par construction* — une propriété que la diffusion par vue ne peut pas garantir. La chaîne d’actifs accepte ces exportations en tant que données d’entraînement traçables :

```bash
# Validate an export's manifest end to end, run the gates, write nothing
sdlab asset ingest ~/exports/dragon_dense --project my-project --dry-run

# Register it: records, candidates, masks, channels, receipt
sdlab asset ingest ~/exports/dragon_dense --project my-project
```

Le répertoire d’exportation contient un manifeste `asset-source.json` (schéma **1.3.0**) qui déclare
ses canaux, ses bandes de palette, ses seuils de validation, le verdict d’acceptation, le registre de style, la manière dont
les rendus ont été créés et leur provenance. sdlab prouve chaque déclaration
par rapport aux octets réels et refuse l’ensemble de l’ingestion en cas de violation — rien n’est enregistré
si le manifeste est incorrect.

**La jonction :** sdlab fournit le mécanisme, l’actif fournit la sémantique. sdlab ne trace jamais de rayons,
ne rend jamais et n’apprend jamais qu’un canal appelé « provenance » est spécial. Il prouve,
mesure, enregistre et regroupe. La signification des chiffres reste avec l’actif.

Ce que le contrat impose :

| étape | ce qui est prouvé |
|---|---|
| **schema** | forme, identifiants, bandes de palette bien formées et un verdict d’acceptation qui est littéralement `"accepted"` |
| **containment** | chaque chemin référencé se résout *à l’intérieur* du répertoire d’exportation (il s’agit d’une entrée non fiable) et existe |
| **encoding** | l’en-tête IHDR d’un PNG correspond à son encodage déclaré ; un en-tête NPY correspond à son dtype et à sa forme déclarés. Un manifeste qui « semble correct » mais qui est en désaccord avec ses octets est la classe d’échec que cette chaîne est conçue pour empêcher |
| **categorical** | les PNG indexés prouvent que PLTE ⊆ palette déclarée ; les canaux filtrés avec `nearest` font l’objet d’un décodage de pixels *exhaustif* ; les NPY catégoriques font l’objet d’une analyse exhaustive des valeurs |
| **gates** | la validation de la palette s’effectue par rendu, à partir des propres bandes et seuils du manifeste — un rendu qui échoue est rejeté de manière audible et signalé, et non admis silencieusement |

Les enregistrements sont enregistrés **sans curation** (`judgment: null`) avec `provenance.source: "asset"`, en conservant
le bloc d’acceptation tel quel, les hachages par fichier, la caméra et la direction dérivée, les mesures de validation, le registre de style déclaré et, par image, la trame et la graine de génération. Ils sont ensuite
soumis au même processus de curation que tous les autres enregistrements.

L’ingestion signale également ce qu’un manifeste *n’a pas* déclaré — un registre de style inconnu, une
absence de `identity.subject_name`, une absence de provenance de la génération — sous forme de **notifications** plutôt que
d’échecs. Elles sont incluses dans le reçu et affichées dans l’interface en ligne de commande. Un écart dont personne n’est informé est un écart que personne ne peut combler ; et comme un manifeste peut *déclarer* que ses rendus sont des dérivations déterministes sans graine propre, la chaîne ne signale jamais un écart sur une exportation qui est correcte.

Contrat complet, l’échelle de validation et la justification de chaque champ :
[docs/asset-lane-design.md](docs/asset-lane-design.md).

## Création de contenu canonique

Avant que le pipeline de l’ensemble de données ne s’exécute, l’espace de noms `sdlab canon *` transforme le magasin d’entités canoniques de votre projet en les trois projections que l’entraînement et la production utilisent réellement, et verrouille les entrées qui ne doivent pas dériver.

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

Un modèle local peut également rédiger le contenu canonique, mais il ne peut pas le décider. `sdlab canon draft <class_id> --endpoint <url> --brief "<text>" --out <path>` demande à un serveur en boucle uniquement, compatible OpenAI, une entrée canonique et des invites, et les écrit avec `status: "draft"`, `judgment: null` et le modèle de rédaction estampillé sur chaque sortie. Un brouillon ne peut pas être figé tant qu’une personne ne l’a pas approuvé : la porte de gel refuse toute entrée rédigée par un modèle sans l’approbation d’un humain, une justification et le hachage du brouillon exact qui a été approuvé.

`canon build` est adressable par contenu — sa sortie est indexée par un `canon_sha` et mise en cache, de sorte qu’une reconstruction canonique inchangée se fait instantanément. `canon freeze` atteste de chaque gel par rapport à une version spécifique et ajoute une `freeze-events.jsonl` à un historique d’audit : les `frozen` entrées refusent purement et simplement la régénération, les `soft-advisory` entrées refusent par défaut (contournement avec `--i-know`). `canon drift` recalcule le hachage de chaque entrée surveillée et signale tout ce qui a été déplacé depuis la dernière reconstruction propre.

Flux de travail complet dans le manuel : [Création de contenu canonique](handbook/canon-build/), [Gel de contenu canonique](handbook/canon-freeze/) et [Empilement de deux LoRA](handbook/two-lora-stacking/).

## Ce qu’il produit

Sept artefacts d’ensemble de données et un atelier de production complet. Chaque artefact est lié à ses prédécesseurs, ce qui vous permet de retracer tout enregistrement d’entraînement jusqu’à la règle qui l’a approuvé.

| Artefact | Ce que c’est |
|----------|-----------|
| **Snapshot** | Sélection d’enregistrements figés avec une empreinte de configuration. Chaque inclusion a une raison explicite. |
| **Split** | Partition train/val/test où les familles de sujets ne traversent jamais les frontières. |
| **Export package** | Ensemble de données autonome : manifeste, métadonnées, images, partitions, fiche d’informations de l’ensemble de données, sommes de contrôle. |
| **Eval pack** | Tâches de test tenant compte du canon : couverture des pistes, dérive interdite, ancrage/or, continuité du sujet. |
| **Training package** | Configuration prête pour l’entraînement via des adaptateurs (`diffusers-lora`, `generic-image-caption`). Même vérité, format différent. |
| **Eval scorecard** | Évaluation par tâche : succès/échec, basée sur les résultats générés et comparés aux ensembles d’évaluation. |
| **Implementation pack** | Exemples d’instructions, exemples d’échecs connus, tests de continuité et instructions pour la réintégration. |

L’environnement de production ajoute :

| Surface | Ce que cela fait |
|---------|-------------|
| **Compiled brief** | Instruction de génération déterministe à partir du profil de flux de travail + de la vérité du projet. |
| **Run** | Artefact d’exécution figé : résumé + graines + ComfyUI résultats + manifeste. |
| **Critique** | Évaluation structurée multidimensionnelle des résultats d’exécution par rapport au canon. |
| **Batch** | Production coordonnée multi-slots (feuilles d’expression, tableaux d’environnement, ensembles de silhouettes). |
| **Selection** | Artefact de décision créative : quels résultats ont été choisis, pourquoi et d’où ils proviennent. |
| **Re-ingest** | Les résultats sélectionnés sont renvoyés sous forme d’enregistrements candidats avec une traçabilité complète de la génération. |

## Pourquoi cela existe

Les données d’entraînement sont l’artefact le plus important dans tout pipeline d’IA visuelle. Mais la plupart des données d’entraînement ne sont qu’un dossier d’images sans historique, sans suivi des évaluations et sans lien avec les règles de style qu’elles étaient censées suivre.

Style Dataset Lab établit explicitement le lien. Votre constitution définit les règles. Votre grille d’évaluation définit les dimensions d’évaluation. Vos enregistrements de curation enregistrent l’évaluation. Votre liaison au canon prouve le lien. Et votre ensemble de données conserve tout cela sous une forme structurée, interrogeable et reproductible.

Le résultat pratique : lorsque votre LoRA dévie, vous pouvez demander *pourquoi*. Lorsque votre prochain cycle d’entraînement a besoin de meilleures données, vous savez exactement quels enregistrements sont presque ratés et quelle règle unique ils ont violée. Lorsqu’un nouveau membre de l’équipe demande quelle est la langue visuelle du projet, la réponse n’est pas un tableau Figma, mais une constitution consultable avec 1 182 exemples notés.

## Prouvé en production

Il ne s’agit pas d’un pipeline de démonstration. Deux vrais modèles LoRA de style ont été déployés de bout en bout grâce à celui-ci, en utilisant la même boucle canon → curation → entraînement → déploiement, aux extrémités opposées du spectre de la curation.

- **[Tallow Fen](handbook/case-study-tallow-fen/)** (conception de créatures) : un canon de bestiaire créé à partir de zéro, **~34 % d’approbation** sur 293 enregistrements évalués (169 rejetés : la porte rejette sévèrement). Déployé `tallow_fen_style_v3.safetensors` @ 1.5 sur `qwen-image`.
- **[Rustline](handbook/case-study-rustline/)** (conception de concepts) : canon dense et préformé, **~96 % d’approbation** sur 180 enregistrements. Déployé `rustline_v3ckpt_1500.safetensors` @ 1.0 sur `qwen-image`, réutilisé en aval par un deuxième projet.

Même pipeline, deux profils de production : la porte de curation est réelle (elle rejette sévèrement les sujets ouverts) et un canon discipliné donne de bons résultats.

## Cinq domaines, règles réelles

Pas de modèles de base. Chaque domaine est livré avec des règles de constitution de qualité de production, des définitions de pistes, des grilles d’évaluation et un vocabulaire de groupe.

| Domaine | Pistes | Ce qui est évalué |
|--------|-------|-----------------|
| **game-art** | personnage, environnement, accessoire, interface utilisateur, vaisseau, intérieur, équipement | Silhouette à l’échelle du jeu, lisibilité de la faction, usure et vieillissement |
| **character-design** | portrait, corps entier, rotation, feuille d’expression, pose d’action | Proportions, logique du costume, personnalité, clarté du geste |
| **creature-design** | concept, orthographique, étude de détails, action, référence d’échelle, habitat | Anatomie, logique évolutive, distinction de la silhouette |
| **architecture** | extérieur, intérieur, paysage urbain, détail structurel, ruine, paysage | Structure, cohérence des matériaux, perspective, cohérence de l’époque |
| **vehicle-mech** | extérieur, cockpit, composant, schéma, feuille de silhouette, variante de dommage | Logique mécanique, langage de conception, points d’accès, récit des dommages |

## Structure du projet

Chaque projet est autonome. Cinq fichiers de configuration JSON définissent les règles ; tout le reste est des données.

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

- **Les instantanés sont immuables.** L’empreinte de configuration (SHA-256) ne prouve aucun changement. Les identifiants sont attribués de manière atomique, de sorte que deux exécutions simultanées ne peuvent pas se mélanger dans un seul répertoire.
- **Les divisions empêchent les fuites, et la vérification qui le confirme est indépendante.** Les familles de sujets (par identité, lignée ou identifiant normalisé) ne traversent jamais les limites des partitions, et une deuxième vérification redéfinit l’identité du sujet à partir de zéro plutôt que de relire la carte utilisée par la division elle-même. Une carte de jeu de données n’indique « fuite : aucune (vérifiée) » que lorsque les deux vérifications ont été exécutées et ont réussi ; une division antérieure à la deuxième vérification indique exactement cela.
- **Les manifestes sont des contrats figés.** Hachage d’exportation + empreinte de configuration, et `validate` recalcule le hachage de chaque fichier `checksums.txt` répertorié, de sorte que le remplacement d’une image dans une exportation terminée est détecté, y compris pour les manifestes créés avant l’existence de cette vérification.
- **Les exécutions définissent leur graphe exact.** Chaque génération enregistre `comfy_workflow_sha` + hachages du contenu du modèle/LoRA + politique de graines, de sorte qu’une vague peut être rejouée octet par octet. Les exécuteurs JS et Python sont maintenus à un hachage identique octet par octet par un test qui les lance tous les deux. Le hachage du modèle est facultatif (`--hash-models`) et n’est jamais fabriqué ; un fichier non résolvable enregistre `sha256: null` avec une note.
- **Aucun modèle ne vérifie sa propre sortie.** Les évaluations enregistrent `judged_by_model` et `generator_model` ; un avertissement est déclenché si elles sont identiques.
- **Une évaluation indique qui l’a créée.** `eligibility audit` distingue les évaluations écrites par une personne des évaluations générées par un script en masse, de sorte qu’une justification qui décrit une catégorie plutôt qu’une image ne peut pas être considérée comme une curation.
- **La mesure n’est pas un verdict.** `sdlab measure` associe des nombres à un enregistrement. Elle ne définit jamais une évaluation, une adéquation ou une approbation, et lorsqu’une mesure est indéfinie pour une image, elle enregistre `null` plutôt qu’un nombre plausible.
- **Une publication peut prouver d’où provient chaque image.** `sdlab verify --project <name>` parcourt la chaîne hors ligne pour chaque enregistrement : le propriétaire et la licence de l’enregistrement, l’entrée du canon à laquelle il était lié (par hachage), la licence de chaque modèle et LoRA qui l’a créé (ID SPDX, URL de la licence, date de lecture et hachage du fichier), et le hachage du flux de travail dans le manifeste de l’exécution. Un lien manquant fait échouer la vérification plutôt que de la valider.
- **Les adaptateurs ne peuvent pas modifier la vérité.** Disposition différente, mêmes enregistrements. Pas d’ajouts, pas de suppressions, pas de reclassification.
- **Les sorties générées sont réintroduites via la révision.** Pas de contournement. Curater et lier comme tout le reste. Les images générées en externe entrent de la même manière via `sdlab ingest`, sans curation préalable.
- **Les échecs sont visibles.** Un enregistrement manquant, une image impossible à placer ou une légende qui ne peut pas être créée interrompt une exportation ou un ensemble d’entraînement plutôt que de le réduire discrètement.

## Star Freight

Le dépôt comprend un exemple de fonctionnement complet : 1 182 enregistrements, 5 factions, 7 lignes, 24 règles de constitution, 892 ressources approuvées, 2 profils d’entraînement. Un canon visuel de RPG de science-fiction réaliste, entièrement curaté.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## Formats en aval

`sdlab` possède le jeu de données. La conversion de format est gérée par [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) : TRL, LLaVA, Qwen2-VL, JSONL, Parquet et plus encore. `repo-dataset` effectue le rendu ; il ne décide jamais de l’inclusion.

## Installation

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Nécessite Node.js 20+ et [ComfyUI](https://github.com/comfyanonymous/ComfyUI) sur localhost : 8188 pour la génération.

### Essayez-le sans ComfyUI

Vous pouvez explorer l’ensemble des fonctionnalités sans génération (inspection, curation, instantané, division, exportation) en utilisant le projet Star Freight inclus sans installer ComfyUI ni télécharger de poids SDXL.

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor` valide chaque configuration de projet (constitution, lignes, rubriques, terminologie) et signale l’éligibilité sans toucher au GPU. Toute commande qui modifie l’état généré accepte `--dry-run` pour prévisualiser l’effet en premier.

Si vous oubliez `--project`, l’interface de ligne de commande revient au premier projet qu’elle trouve sous `projects/` et affiche un avertissement ; passez `--project` explicitement pour le désactiver.

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

**`ECONNREFUSED 127.0.0.1:8188` sur n’importe quel `sdlab generate` / `sdlab run generate` / `sdlab batch generate`**
ComfyUI ne fonctionne pas. Démarrez ComfyUI (`python main.py --listen 127.0.0.1 --port 8188`) et confirmez avec `curl http://127.0.0.1:8188/system_stats`. Pour pointer vers un autre hôte/port, définissez `COMFY_URL=http://host:port`.

**`missing checkpoint` / `LoRA weight not found`**
Votre profil de flux de travail nomme un fichier de modèle qui ne se trouve pas dans le dossier `models/checkpoints/` ou `models/loras/` de ComfyUI. Ouvrez `projects/<project>/workflows/profiles/<profile>.json`, localisez le champ `checkpoint` ou `lora`, et téléchargez soit le poids référencé, soit remplacez-le par un poids que vous avez déjà. Réexécutez `sdlab project doctor --project <project>` pour confirmer la correction.

**Erreurs `sdlab project doctor`**
Doctor renvoie des codes d’erreur structurés. Les plus courants :
- `E_PROJECT_NOT_FOUND` : le répertoire du projet n’existe pas sous `projects/`. Vérifiez l’orthographe.
- `E_CONFIG_INVALID` : l’un des cinq fichiers de configuration JSON n’a pas réussi la validation du schéma. Le champ `hint` indique le fichier et le champ concernés.
- `E_RECORD_DRIFT` : l’empreinte de configuration d’un enregistrement ne correspond plus à sa source. Recurez ou reliez comme le suggère l’indice.

**`No --project specified, falling back to <name>`**
Un avertissement léger. Passez `--project <name>` explicitement pour sélectionner le bon projet et désactiver l’avertissement.

**Problèmes de mémoire VRAM / Painterly**
Consultez `docs/internal/HANDOFF.md` pour les notes de réglage du décrépitage « painterly ». En résumé : réduisez la force du décrépitage, réduisez la taille du lot ou passez à un point de contrôle plus petit dans votre profil de flux de travail.

**Signalement des bogues**
Créez un problème à l’adresse https://github.com/mcp-tool-shop-org/style-dataset-lab/issues avec votre version sdlab (`sdlab --version`), votre version de Node (`node -v`), la commande complète et la sortie d’erreur structurée. Un modèle de rapport de bogue préremplit les champs.

## Sécurité

Par défaut, il est local. Pas de télémétrie, pas d’analyses et aucune requête externe de l’interface de ligne de commande `sdlab` : les images restent sur votre GPU et votre système de fichiers, et `canon draft` refuse tout point de terminaison qui n’est pas en boucle locale.

La seule exception est l’option d’adhésion. `scripts/colab/` contient des kits de lancement pour exécuter un rendu ou une étape d’entraînement LoRA sur votre propre compte Google Colab. Ils ne téléchargent que les fichiers que vous leur indiquez, s’exécutent dans les limites de dépenses définies à partir du solde actuel de votre compte Colab et arrêtent leur propre session à la fermeture. Ces kits sont **expérimentaux** : ils n’ont pas encore été entièrement testés de bout en bout.

## Licence

MIT

---

Créé par <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
