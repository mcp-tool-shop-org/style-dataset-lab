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

Convierta el material visual aprobado en conjuntos de datos versionados, respaldados por revisiones, divisiones, paquetes de exportación y paquetes de evaluación.

## ¿Qué es esto?

Una **línea de producción de conjuntos de datos y un canon visual**. Defina cómo se verá su proyecto. Seleccione cuidadosamente de acuerdo con las reglas establecidas. Cree paquetes de conjuntos de datos reproducibles con divisiones seguras contra fugas de información. Genere paquetes de evaluación para la verificación futura del modelo.

La línea de producción genera cuatro elementos:

| Elemento | ¿Qué es? |
|----------|-----------|
| **Snapshot** | Selección de registros elegibles, congelada y con huella digital. Cada inclusión tiene un registro explícito de la razón. |
| **Split** | Partición segura contra fugas de información para entrenamiento/validación/prueba. Los registros que comparten una misma familia siempre se incluyen en la misma división. |
| **Export package** | Conjunto de datos autónomo: manifiesto, metadatos, imágenes, divisiones, descripción del conjunto de datos y sumas de verificación. |
| **Eval pack** | Tareas de verificación que respetan el canon: cobertura de categorías, desviación prohibida, referencia/estándar, coherencia temática. |

Cada elemento en la línea de producción contiene tres cosas:

1. **Origen** -- historial completo de generación (punto de control, LoRA, semilla, muestreador, configuración, tiempo de ejecución)
2. **Cumplimiento del canon** -- qué reglas establecidas cumple, no cumple o cumple parcialmente este elemento.
3. **Evaluación de calidad** -- aprobado/rechazado/límite con puntuaciones por dimensión.

Funciona para arte de juegos, diseño de personajes, diseño de criaturas, arquitectura, conceptos de vehículos/mecánica y cualquier dominio donde la producción visual deba mantenerse dentro de los parámetros establecidos.

## Comienzo rápido

```bash
# Install the CLI + pipeline
npm install -g @mcptoolshop/style-dataset-lab

# Scaffold a new project
sdlab init my-project --domain character-design

# Validate the project structure
sdlab project doctor --project my-project
```

Dominios disponibles: `game-art`, `character-design`, `creature-design`, `architecture`, `vehicle-mech` o `generic`.

## Interfaz de línea de comandos (CLI)

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

Todos los comandos aceptan `--project <nombre>` (por defecto: `star-freight`).

## Modelo del proyecto

Cada proyecto es un directorio autónomo dentro de `projects/` con su propio canon, configuración y datos:

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

## Línea de producción

```
canon → generate → curate → bind → snapshot → split → export → eval
  |        |          |        |        |         |        |       |
rules   ComfyUI   judgment  rules   frozen    subject  package  verify
                                    selection isolation
```

1. **Definir el canon** -- escriba su constitución de estilo y rúbrica de revisión.
2. **Generar** -- ComfyUI genera candidatos con un origen completo.
3. **Seleccionar** -- apruebe/rechace con puntuaciones por dimensión y modos de fallo.
4. **Vincular** -- vincule cada elemento a las reglas establecidas con veredictos de cumplimiento/incumplimiento/parcial.
5. **Captura** -- congele los registros elegibles en una selección determinista y con huella digital.
6. **Dividir** -- particione en entrenamiento/validación/prueba con aislamiento temático y equilibrio de categorías.
7. **Exportar** -- cree un paquete autónomo con manifiesto, metadatos, imágenes y sumas de verificación.
8. **Evaluar** -- genere instrumentos de prueba que respeten el canon para la verificación del modelo.

La conversión de formato a formatos posteriores (TRL, LLaVA, Parquet, etc.) se gestiona mediante [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset). `sdlab` es responsable de la veracidad del conjunto de datos; `repo-dataset` lo convierte en formatos especializados.

## Plantillas de dominio

Cada plantilla de dominio incluye definiciones de categorías, reglas establecidas, rúbricas de puntuación y estructuras de terminología diseñadas para ese contexto de producción:

| Dominio | Categorías | Preocupaciones clave |
|--------|-------|-------------|
| **game-art** | personaje, entorno, accesorio, interfaz de usuario, nave, interior, equipo | Silueta a escala de juego, diferenciación de facciones, desgaste/envejecimiento |
| **character-design** | retrato, cuerpo entero, vista de 360 grados, hoja de expresiones, pose de acción | Precisión de las proporciones, lógica del vestuario, interpretación de la personalidad, claridad de los gestos |
| **creature-design** | concepto, ortográfico, estudio de detalles, acción, referencia de escala, hábitat | Plausibilidad anatómica, lógica evolutiva, distinción de siluetas |
| **architecture** | exterior, interior, paisaje urbano, detalle estructural, ruina, paisaje | Plausibilidad estructural, consistencia de materiales, perspectiva, coherencia de la época |
| **vehicle-mech** | exterior, cabina, componente, esquema, hoja de siluetas, variante de daño | Lógica mecánica, lenguaje de diseño funcional, puntos de acceso, descripción de daños. |

## Producción del conjunto de datos

Estructura completa del conjunto de datos: instantánea, división, exportación, evaluación.

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

Las **instantáneas** congelan una selección determinista de registros elegibles. Cada inclusión tiene un registro de la razón. Las huellas de configuración garantizan la reproducibilidad.

Las **divisiones** asignan los registros a particiones de entrenamiento/validación/prueba, con aislamiento de sujetos (ninguna familia de sujetos aparece en múltiples divisiones) y distribución equilibrada por "carril". Un generador de números pseudoaleatorios con semilla garantiza resultados idénticos a partir de la misma semilla.

Los **paquetes de exportación** son autocontenidos: manifiesto, metadata.jsonl, imágenes (enlaces simbólicos o copias), divisiones, tarjeta del conjunto de datos (Markdown + JSON) y sumas de verificación en formato BSD. Todo lo necesario para reconstruir el conjunto de datos desde cero.

Los **paquetes de evaluación** son instrumentos de prueba que tienen en cuenta el canon y que incluyen cuatro tipos de tareas: cobertura de "carriles", deriva prohibida, anclaje/referencia y continuidad del sujeto. Demuestran que la estructura del conjunto de datos está alimentando futuras evaluaciones de modelos, y no solo se están volviendo a depositar archivos.

Exportación a formatos posteriores a través de [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) (TRL, LLaVA, Qwen2-VL, JSONL, Parquet, y más). `repo-dataset` se encarga de la conversión de formatos; `sdlab` es responsable de la integridad del conjunto de datos.

## Ejemplo de Star Freight

Clona el repositorio para obtener un ejemplo de funcionamiento completo: 1182 registros, 28 oleadas de indicaciones, 5 facciones, 7 "carriles", 24 reglas constitucionales y 892 activos aprobados de un RPG de ciencia ficción.

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

## Migración desde la versión 1.x

La versión 2.0 cambia el nombre de `games/` a `projects/` y `--game` a `--project`:

```bash
# Rename your data directory
mv games projects

# --game still works with a deprecation warning (removed in v3.0)
sdlab bind --game star-freight   # works, prints warning
sdlab bind --project star-freight # canonical form
```

## Modelo de seguridad

**Solo local.** Se comunica con ComfyUI en `localhost:8188`. No hay telemetría, ni análisis, ni solicitudes externas. Las imágenes permanecen en tu GPU y sistema de archivos.

## Requisitos

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) ejecutándose en localhost:8188
- Checkpoint DreamShaper XL Turbo + LoRA ClassipeintXL
- Node.js 20+
- [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) para la exportación del entrenamiento.

## Licencia

MIT

---

Creado por <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a
