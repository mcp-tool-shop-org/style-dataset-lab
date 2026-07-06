<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.md">English</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
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

Escribe tus reglas visuales. Genera arte. Evalúa cada imagen según esas reglas. Entrega los resultados como datos de entrenamiento auditables y versionados, y luego utiliza los modelos entrenados en flujos de trabajo de producción reales, e introduce las mejores salidas nuevamente en tu corpus.

Style Dataset Lab conecta lo que has definido sobre tu estilo artístico con el conjunto de datos del cual realmente estás entrenando, y luego cierra el ciclo a lo largo de todo el proceso de producción. Defines una constitución: reglas de silueta, restricciones de paleta, lenguaje de materiales, o cualquier cosa que sea importante para tu proyecto. El flujo de trabajo genera candidatos, los evalúa según esas reglas y empaqueta el trabajo aprobado en conjuntos de datos reproducibles donde cada registro explica por qué se incluyó.

Luego, el entorno de trabajo de producción toma el control: compila resúmenes de generación a partir de la información del proyecto, ejecútalos a través de ComfyUI, evalúa las salidas, produce en lote hojas de expresión y paneles de entorno, selecciona los mejores resultados y vuelve a introducirlos como nuevos candidatos. El ciclo se cierra: producir, seleccionar, revisar, mejorar.

## El flujo de trabajo

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

Ese último comando es el punto clave. Las salidas seleccionadas vuelven a pasar por el mismo proceso de revisión que todo lo demás. El corpus crece y las reglas se mantienen.

## Creación del canon

Antes de que se ejecute el flujo de trabajo del conjunto de datos, el espacio de nombres `sdlab canon *` convierte el almacén de entidades del canon de tu proyecto en los tres proyecciones que realmente utiliza el entrenamiento y la producción, y bloquea las entradas que no deben modificarse.

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

`canon build` es direccionable por contenido: su salida se identifica mediante un `canon_sha` y se almacena en caché, de modo que una reconstrucción del canon sin cambios se realiza instantáneamente. `canon freeze` registra cada congelación frente a una compilación específica y la agrega a un registro de auditoría `freeze-events.jsonl`: las entradas `frozen` rechazan explícitamente la regeneración, las entradas `soft-advisory` la rechazan por defecto (se puede omitir con `--i-know`). `canon drift` vuelve a calcular el hash de cada entrada observada y marca cualquier cosa que haya cambiado desde la última compilación limpia.

Flujo de trabajo completo en el manual: [Canon build](handbook/canon-build/), [Canon freeze](handbook/canon-freeze/) y [Two-LoRA stacking](handbook/two-lora-stacking/).

## Qué produce

Siete artefactos del conjunto de datos y un entorno de trabajo de producción completo. Cada artefacto se vincula a sus predecesores para que puedas rastrear cualquier registro de entrenamiento hasta la regla que lo aprobó.

| Artefacto | Qué es |
|----------|-----------|
| **Snapshot** | Selección de registros congelados con huella digital de configuración. Cada inclusión tiene una razón explícita. |
| **Split** | Partición de entrenamiento/validación/prueba donde las familias de sujetos nunca cruzan los límites. |
| **Export package** | Conjunto de datos autónomo: manifiesto, metadatos, imágenes, divisiones, tarjeta del conjunto de datos, sumas de comprobación. |
| **Eval pack** | Tareas de prueba con conocimiento del canon: cobertura de carriles, desviación prohibida, ancla/oro, continuidad del sujeto. |
| **Training package** | Diseño listo para el entrenamiento a través de adaptadores (`diffusers-lora`, `generic-image-caption`). La misma información, diferente formato. |
| **Eval scorecard** | Aprobación/rechazo por tarea basada en la evaluación de las salidas generadas con respecto a los paquetes de evaluación. |
| **Implementation pack** | Ejemplos de indicaciones, fallas conocidas, pruebas de continuidad y orientación para volver a introducir datos. |

El entorno de trabajo de producción agrega:

| Superficie | Qué hace |
|---------|-------------|
| **Compiled brief** | Instrucción de generación determinista a partir del perfil del flujo de trabajo + la información del proyecto. |
| **Run** | Artefacto de ejecución congelado: resumen + semillas + salidas de ComfyUI + manifiesto. |
| **Critique** | Evaluación estructurada multidimensional de las salidas de ejecución con respecto al canon. |
| **Batch** | Producción coordinada en múltiples ranuras (hojas de expresión, paneles de entorno, paquetes de silueta). |
| **Selection** | Artefacto de decisión creativa: qué salidas se eligieron, por qué y de dónde provienen. |
| **Re-ingest** | Las salidas seleccionadas se devuelven como registros candidatos con el origen completo de la generación. |

## Por qué existe esto

Los datos de entrenamiento son el artefacto más importante en cualquier flujo de trabajo de IA visual. Pero la mayoría de los datos de entrenamiento son una carpeta de imágenes sin historial, sin rastro de evaluación y sin conexión con las reglas de estilo que se suponía que debían seguir.

Style Dataset Lab hace que la conexión sea explícita. Tu constitución define las reglas. Tu rúbrica define las dimensiones de puntuación. Tus registros de curación registran el juicio. El enlace del canon prueba la conexión. Y tu conjunto de datos lleva todo eso adelante como información estructurada, consultable y reproducible.

El resultado práctico: cuando tu LoRA se desvía, puedes preguntar *por qué*. Cuando tu próxima ronda de entrenamiento necesita mejores datos, sabes exactamente qué registros son casi correctos y cuál es la única regla que no cumplieron. Cuando un nuevo miembro del equipo pregunta cuál es el lenguaje visual del proyecto, la respuesta no es un panel de Figma, sino una constitución consultable con 1182 ejemplos calificados.

## Cinco dominios, reglas reales

No son plantillas genéricas. Cada dominio se entrega con reglas de constitución de grado de producción, definiciones de carriles, rúbricas de puntuación y vocabulario de grupo.

| Dominio | Carriles | Qué se evalúa |
|--------|-------|-----------------|
| **game-art** | personaje, entorno, accesorio, interfaz de usuario, nave, interior, equipo | Silueta a escala de juego, identificación de facción, desgaste y envejecimiento |
| **character-design** | retrato, cuerpo completo, rotación, hoja de expresión, pose de acción | Proporciones, lógica del disfraz, personalidad, claridad del gesto |
| **creature-design** | concepto, ortográfico, estudio de detalles, acción, referencia de escala, hábitat | Anatomía, lógica evolutiva, distinción de la silueta |
| **architecture** | exterior, interior, paisaje urbano, detalle estructural, ruina, paisaje | Estructura, consistencia del material, perspectiva, coherencia de la época |
| **vehicle-mech** | exterior, cabina, componente, esquema, hoja de silueta, variante de daño | Lógica mecánica, lenguaje de diseño, puntos de acceso, narrativa de daños |

## Estructura del proyecto

Cada proyecto es independiente. Cinco archivos de configuración JSON definen las reglas; todo lo demás son datos.

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

## Propiedades de confianza

Estas no son aspiracionales. Se aplican rigurosamente.

- **Las instantáneas son inmutables.** La huella digital de la configuración (SHA-256) demuestra que nada ha cambiado.
- **Las divisiones evitan fugas.** Las familias de sujetos (por identidad, linaje o sufijo de ID) nunca cruzan los límites de las particiones.
- **Los manifiestos son contratos congelados.** Hash de exportación + huella digital de la configuración. Si algo cambia, cree uno nuevo.
- **Los adaptadores no pueden modificar la verdad.** Diseño diferente, mismos registros. Sin adiciones, sin eliminaciones, sin reclasificaciones.
- **Las salidas generadas vuelven a entrar mediante revisión.** No hay atajos. Curar y vincular como todo lo demás.

## Star Freight

El repositorio incluye un ejemplo completo y funcional: 1.182 registros, 5 facciones, 7 rutas, 24 reglas de constitución, 892 activos aprobados, 2 perfiles de entrenamiento. Un canon visual de ciencia ficción con toques ásperos, totalmente curado.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## Formatos posteriores

`sdlab` es el propietario del conjunto de datos. La conversión de formato la gestiona [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset): TRL, LLaVA, Qwen2-VL, JSONL, Parquet y más. `repo-dataset` renderiza; nunca decide qué incluir.

## Instalación

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Requiere Node.js 20+ y [ComfyUI](https://github.com/comfyanonymous/ComfyUI) en localhost:8188 para la generación.

### Pruébalo sin ComfyUI

Puedes explorar toda la funcionalidad que no implica la generación (inspección, curación, instantánea, división, exportación) utilizando el proyecto Star Freight incluido sin instalar ComfyUI ni descargar ningún peso de SDXL.

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor` valida cada configuración del proyecto (constitución, rutas, rúbrica, terminología) e informa sobre la elegibilidad sin tocar la GPU. Cualquier comando que modifique el estado generado acepta `--dry-run` para previsualizar el efecto primero.

Si olvidas `--project`, la CLI recurre al primer proyecto que encuentra en `projects/` e imprime una advertencia; pasa `--project` explícitamente para silenciarla.

### Reanudando una ejecución interrumpida

Las ejecuciones de generación largas se pueden reanudar sin rehacer el trabajo completado:

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

Ambos comandos funcionan porque cada ranura escribe su entrada de manifiesto atómicamente al finalizar; un fallo a mitad de la ejecución nunca corrompe el estado parcial.

## Solución de problemas

Modos de fallo comunes y soluciones:

**`ECONNREFUSED 127.0.0.1:8188` en cualquier `sdlab generate` / `sdlab run generate` / `sdlab batch generate`**
ComfyUI no se está ejecutando. Inicia ComfyUI (`python main.py --listen 127.0.0.1 --port 8188`) y confirma con `curl http://127.0.0.1:8188/system_stats`. Para apuntar a un host/puerto diferente, establece `COMFY_URL=http://host:port`.

**`missing checkpoint` / `LoRA weight not found`**
El perfil de flujo de trabajo especifica un archivo de modelo que no está en la carpeta `models/checkpoints/` o `models/loras/` de ComfyUI. Abre `projects/<project>/workflows/profiles/<profile>.json`, localiza el campo `checkpoint` o `lora` y, ya sea descarga el peso referenciado o cámbialo por uno que ya tengas. Vuelve a ejecutar `sdlab project doctor --project <project>` para confirmar la solución.

**Errores de `sdlab project doctor`**
Doctor devuelve códigos de error estructurados. Algunos comunes:
- `E_PROJECT_NOT_FOUND`: el directorio del proyecto no existe en `projects/`. Verifica la ortografía.
- `E_CONFIG_INVALID`: uno de los cinco archivos de configuración JSON falló la validación del esquema. El campo `hint` indica el archivo y el campo incorrectos.
- `E_RECORD_DRIFT`: la huella digital de la configuración de un registro ya no coincide con su origen. Vuelve a curar o vuelve a vincular según lo que sugiera la pista.

**`No --project specified, falling back to <name>`**
Una advertencia leve. Pasa `--project <name>` explícitamente para seleccionar el proyecto correcto y silenciar la advertencia.

**Problemas de memoria VRAM / "Painterly"**
Consulta `docs/internal/HANDOFF.md` para obtener las notas sobre el ajuste del ruido "painterly". En resumen: reduce la intensidad del ruido, disminuye el tamaño del lote o cambia a un punto de control más pequeño en tu perfil de flujo de trabajo.

**Informar errores**
Crea un problema en https://github.com/mcp-tool-shop-org/style-dataset-lab/issues con tu versión de sdlab (`sdlab --version`), la versión de Node (`node -v`), el comando completo y la salida de error estructurada. Una plantilla de informe de errores rellena previamente los campos.

## Seguridad

Solo local. Sin telemetría, sin análisis, sin solicitudes externas. Las imágenes permanecen en tu GPU y sistema de archivos.

## Licencia

MIT

---

Creado por <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
