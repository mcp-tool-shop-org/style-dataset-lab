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

Factoría de conjuntos de datos visuales: genera, organiza y exporta datos de entrenamiento multimodales para el ajuste fino de modelos de lenguaje visual (VLM).

## ¿Qué es esto?

Un conjunto de herramientas para construir **"verdad visual" entrenable**. Cada elemento contiene tres cosas:

1. **Píxeles de la imagen:** generados por ComfyUI con total trazabilidad (punto de control, LoRA, semilla, muestreador, configuración).
2. **Explicación canónica:** por qué este elemento está dentro o fuera del estilo, basado en una constitución de estilo.
3. **Juicio de calidad:** aprobado/rechazado con puntuaciones por dimensión y reglas citadas.

La salida se integra con [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) para producir datos de entrenamiento multimodales en 10 formatos: TRL, LLaVA, Qwen2-VL, Axolotl, LLaMA-Factory, ShareGPT, pares RLHF, DPO, subtitulado y clasificación.

## Modelo de seguridad

**Solo local.** style-dataset-lab se comunica con ComfyUI en `localhost:8188` y nunca realiza solicitudes a la red externa. No hay telemetría, ni análisis, ni conexión a servidores externos. La generación de imágenes se realiza completamente en su GPU. Los registros y los datos canónicos permanecen en su sistema de archivos.

## Estadísticas del conjunto de datos

| Métrica | Valor |
|--------|-------|
| Registros organizados | 1,182 |
| Elementos totales | 2.571 (893 aprobados, 887 variantes con estilo pictórico) |
| Combinaciones de indicaciones | 28 |
| Categorías visuales | 18 (disfraces, barcos, interiores, equipos, entornos, especies, estaciones, señalización, iluminación, carga, arquitectura, criaturas, superficies, vida cotidiana, planetario, daño/reparación, biología alienígena, detalles realistas) |
| Comparaciones por pares | 6 creados por humanos + 71 creados sintéticamente |
| Tipos de rechazo distintos | 30+ |
| Sistema de paquetes de identidad | Personajes con nombre con ADN de facción, rango y anclajes visuales. |
| Formatos de exportación | 10 (a través de `@mcptoolshop/repo-dataset`) |

## Instalación

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Luego, clone un proyecto o inicializa un nuevo espacio de trabajo de conjunto de datos:

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab my-dataset
cd my-dataset
npm install
```

## Flujo de trabajo

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

## Estructura de directorios

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

## Configuración de generación

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

Modos de generación adicionales: ControlNet (guiado por pose/profundidad), IP-Adapter (guiado por referencia) y paquetes de identidad (consistencia de personajes con nombre).

## Requisitos

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) ejecutándose en localhost:8188
- Punto de control DreamShaper XL Turbo + LoRA ClassipeintXL
- Node.js 20+
- [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) para la exportación de entrenamiento.

## Licencia

MIT

---

Creado por <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
