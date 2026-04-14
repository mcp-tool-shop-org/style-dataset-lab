<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.md">English</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/style-dataset-lab/readme.png" width="400">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@mcptoolshop/style-dataset-lab"><img src="https://img.shields.io/npm/v/@mcptoolshop/style-dataset-lab" alt="npm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

# style-dataset-lab

Una canalización de producción para la creación de conjuntos de datos visuales: desde reglas establecidas hasta indicaciones estructuradas, pasando por la generación con ComfyUI, hasta la creación de datos de entrenamiento curados y sujetos a reglas.

## ¿Qué es esto?

Una **canalización** para la creación de conjuntos de datos visuales de entrenamiento estructurados. Se definen reglas de estilo (establecidas), se crean indicaciones, se genera contenido con ComfyUI, se realiza una curación con puntuación por dimensión, se asocian juicios a las reglas establecidas y se exporta en 10 formatos a través de [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset).

La canalización es independiente del juego. Cada juego tiene su propio directorio de datos dentro de `games/<nombre>/`; los 13 scripts y las plantillas vacías se comparten. Cada activo generado contiene tres elementos:

1. **Píxeles de la imagen** -- generados por ComfyUI con información completa de origen (checkpoint, LoRA, semilla, sampler, cfg).
2. **Explicación de la regla establecida** -- la razón por la cual la imagen es o no está de acuerdo con el estilo definido, basada en una constitución de estilo.
3. **Juicio de calidad** -- aprobado/rechazado con puntuaciones por dimensión y reglas citadas.

## Modelo de seguridad

**Solo local.** style-dataset-lab se comunica con ComfyUI en `localhost:8188` y nunca realiza solicitudes a la red externa. No hay telemetría, ni análisis, ni conexión a servidores externos. La generación de imágenes se realiza completamente en su GPU. Los registros y los datos de la regla establecida permanecen en su sistema de archivos.

## ¿Qué incluye el paquete npm?

`npm install @mcptoolshop/style-dataset-lab` le proporciona:

- **13 scripts** -- para generar, curar, comparar, asociar a la regla establecida, generar imágenes con estilo pictórico, generar identidades, generar imágenes con ControlNet/IP-Adapter, curación masiva, migración.
- **Plantillas vacías** -- una constitución de inicio, una rúbrica de revisión y un paquete de ejemplos de indicaciones en `templates/`.

El paquete npm **no** incluye datos del juego. Clone el repositorio si desea el ejemplo de Star Freight (1182 registros, 28 oleadas de indicaciones, 18 categorías visuales).

## Instalación

```bash
# Get the pipeline scripts + templates
npm install @mcptoolshop/style-dataset-lab

# Or clone the repo for the Star Freight example data
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
npm install
```

Para comenzar un nuevo juego a partir de las plantillas:

```bash
# Copy templates into your game directory
mkdir -p games/my-game/{records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
cp -r templates/canon games/my-game/canon
cp templates/inputs/prompts/example-wave.json games/my-game/inputs/prompts/wave1.json
# Edit the canon and prompts, then generate
```

## Estructura del monorepositorio

La canalización se encuentra en `scripts/` y `templates/`. Cada juego se encuentra en `games/<nombre>/` con su propia regla establecida, registros y activos. Los scripts aceptan `--game <nombre>` (por defecto, `star-freight`).

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

## Flujo de trabajo de la canalización

La canalización completa, desde la regla establecida hasta la exportación para el entrenamiento:

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

## Añadir un nuevo juego

```bash
# Create structure and copy blank templates
mkdir -p games/my-game/{records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
cp -r templates/canon games/my-game/canon
cp templates/inputs/prompts/example-wave.json games/my-game/inputs/prompts/wave1.json

# Edit your canon/constitution.md and canon/review-rubric.md
# Edit your prompt pack, then run the pipeline with --game my-game
```

## Estructura del directorio por juego

Cada directorio `games/<nombre>/` contiene:

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

## Configuración de la generación

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

Modos de generación adicionales: ControlNet (guiado por pose/profundidad), IP-Adapter (guiado por referencia) y paquetes de identidad (consistencia de personajes nombrados).

## Requisitos

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) ejecutándose en localhost:8188
- Checkpoint DreamShaper XL Turbo + LoRA ClassipeintXL
- Node.js 20+
- [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) para la exportación del entrenamiento.

## Licencia

MIT

---

Creado por <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a
