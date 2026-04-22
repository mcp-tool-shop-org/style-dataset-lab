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

Escriba sus reglas visuales. Genere arte. Evalúe cada imagen según esas reglas. Envíe los resultados como datos de entrenamiento versionados y auditables, y luego ponga los modelos entrenados en funcionamiento en flujos de trabajo de producción reales y retroalimente los mejores resultados a su corpus.

Style Dataset Lab conecta lo que ha escrito sobre su estilo artístico con el conjunto de datos con el que realmente entrena. Usted define una constitución: reglas de silueta, restricciones de paleta, lenguaje de materiales, cualquier cosa que sea importante para su proyecto. El proceso genera candidatos, los evalúa según esas reglas y empaqueta el trabajo aprobado en conjuntos de datos reproducibles donde cada registro explica por qué se incluyó.

Luego, el entorno de trabajo de producción toma el control: compile las instrucciones de generación a partir de la "verdad" del proyecto, ejecútelas a través de ComfyUI, evalúe los resultados, genere en masa hojas de expresión y paneles de entorno, seleccione los mejores resultados y reincorpórelos como nuevos candidatos. El ciclo se cierra: producir, seleccionar, revisar, fortalecer.

## El proceso

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

Esa última instrucción es clave. Los resultados seleccionados vuelven a pasar por el mismo proceso de revisión que todo lo demás. El corpus crece y las reglas se mantienen.

## Lo que produce

Siete artefactos de conjunto de datos y un entorno de trabajo de producción completo. Cada artefacto está vinculado a sus predecesores, por lo que puede rastrear cualquier registro de entrenamiento hasta la regla que lo aprobó.

| Artefacto. | Qué es. |
|----------|-----------|
| **Snapshot** | Selección de registros congelada con huella de configuración. Cada inclusión tiene una razón explícita. |
| **Split** | Partición de entrenamiento/validación/prueba donde las familias de sujetos nunca cruzan límites. |
| **Export package** | Conjunto de datos autocontenido: manifiesto, metadatos, imágenes, divisiones, tarjeta del conjunto de datos, sumas de verificación. |
| **Eval pack** | Tareas de prueba conscientes del criterio: cobertura de áreas, desviación prohibida, referencia/oro, continuidad del sujeto. |
| **Training package** | Diseño listo para el entrenamiento a través de adaptadores (`diffusers-lora`, `generic-image-caption`). La misma información, en un formato diferente. |
| **Eval scorecard** | Resultado de aprobación/reprobación por tarea, según la evaluación de las salidas generadas. |
| **Implementation pack** | Ejemplos de indicaciones, fallos conocidos, pruebas de continuidad y guías para la inclusión. |

El entorno de trabajo de producción agrega:

| Superficie | Qué hace |
|---------|-------------|
| **Compiled brief** | Generación determinista a partir de la instrucción del perfil de flujo de trabajo + la "verdad" del proyecto. |
| **Run** | Artefacto de ejecución congelado: instrucción + semillas + resultados de ComfyUI + manifiesto. |
| **Critique** | Evaluación estructurada y multidimensional de los resultados de la ejecución en comparación con el canon. |
| **Batch** | Producción coordinada de múltiples elementos (hojas de expresión, paneles de entorno, paquetes de siluetas). |
| **Selection** | Artefacto de decisión creativa: qué resultados se eligieron, por qué y de dónde provienen. |
| **Re-ingest** | Los resultados seleccionados se devuelven como registros de candidatos con un historial completo de generación. |

## Por qué existe

Los datos de entrenamiento son el activo más valioso en cualquier canal de IA visual. Pero la mayoría de los datos de entrenamiento son una carpeta de imágenes sin historial, sin rastro de evaluación y sin conexión con las reglas de estilo que se suponía que debían seguir.

Style Dataset Lab hace que esa conexión sea explícita. Su constitución define las reglas. Su rúbrica define las dimensiones de la evaluación. Sus registros de curación registran la evaluación. Su canon vinculante prueba la conexión. Y su conjunto de datos transmite todo eso como una verdad estructurada, consultable y reproducible.

El resultado práctico: cuando su LoRA se desvía, puede preguntar *por qué*. Cuando su próxima ronda de entrenamiento necesita mejores datos, sabe exactamente qué registros están cerca de cumplir los requisitos y qué regla específica no cumplieron. Cuando un nuevo miembro del equipo pregunta cuál es el lenguaje visual del proyecto, la respuesta no es una pizarra de Figma, sino una constitución con 1182 ejemplos clasificados y que se puede buscar.

## Cinco dominios, reglas reales

No son plantillas genéricas. Cada dominio viene con reglas de constitución de calidad de producción, definiciones de áreas, rúbricas de evaluación y vocabulario específico.

| Dominio. | Áreas. | Qué se evalúa. |
|--------|-------|-----------------|
| **game-art** | personaje, entorno, accesorio, interfaz de usuario, nave, interior, equipo. | Silueta a escala de juego, identificación de facción, desgaste y envejecimiento. |
| **character-design** | retrato, cuerpo entero, vista de 360 grados, hoja de expresiones, pose de acción. | Proporciones, lógica del atuendo, personalidad, claridad del gesto. |
| **creature-design** | concepto, ortográfico, estudio de detalles, acción, referencia de escala, hábitat. | Anatomía, lógica evolutiva, distinción de silueta. |
| **architecture** | exterior, interior, paisaje urbano, detalle estructural, ruina, paisaje. | Estructura, consistencia de materiales, perspectiva, coherencia de la época. |
| **vehicle-mech** | exterior, cabina, componente, esquema, hoja de silueta, variante de daño. | Lógica mecánica, lenguaje de diseño, puntos de acceso, narrativa de daño. |

## Estructura del proyecto

Cada proyecto es independiente. Cinco archivos de configuración JSON definen las reglas; todo lo demás es datos.

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

Estas no son meras aspiraciones. Se aplican de forma obligatoria.

- **Las instantáneas son inmutables.** La huella digital de la configuración (SHA-256) demuestra que nada ha cambiado.
- **Las divisiones evitan fugas de información.** Las familias de sujetos (por identidad, linaje o sufijo de ID) nunca cruzan los límites de la partición.
- **Los manifiestos son contratos inalterables.** Exporta el hash + la huella digital de la configuración. Si algo cambia, crea uno nuevo.
- **Los adaptadores no pueden modificar la información.** Diferente diseño, mismos registros. No hay adiciones, ni eliminaciones, ni reclasificaciones.
- **Las salidas generadas se revisan antes de ser utilizadas.** No hay excepciones. Se curan y se vinculan como todo lo demás.

## Star Freight

El repositorio incluye un ejemplo de funcionamiento completo: 1182 registros, 5 facciones, 7 rutas, 24 reglas constitucionales, 892 activos aprobados, 2 perfiles de entrenamiento. Un canon visual de un RPG de ciencia ficción realista, completamente curado.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## Formatos de salida

`sdlab` es el propietario del conjunto de datos. La conversión de formatos la gestiona [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset): TRL, LLaVA, Qwen2-VL, JSONL, Parquet, y más. `repo-dataset` se encarga de la renderización; nunca decide qué incluir.

## Instalación

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Requiere Node.js 20+ y [ComfyUI](https://github.com/comfyanonymous/ComfyUI) en localhost:8188 para la generación.

### Pruébelo sin ComfyUI

Puede explorar toda la superficie de no generación (inspección, curación, instantánea, división, exportación) utilizando el proyecto Star Freight incluido, sin instalar ComfyUI ni descargar ningún peso de SDXL.

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor` valida cada configuración del proyecto (constitución, canales, rúbrica, terminología) e informa sobre la elegibilidad sin tocar la GPU. Cualquier comando que modifique el estado generado acepta `--dry-run` para previsualizar el efecto primero.

Si olvida `--project`, la CLI recurre al primer proyecto que encuentra en `projects/` e imprime una advertencia; use `--project` explícitamente para silenciarla.

### Reanudación de una ejecución interrumpida

Las largas ejecuciones de generación se pueden reanudar sin tener que volver a realizar el trabajo completado:

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

Ambos comandos funcionan porque cada ranura escribe su entrada de manifiesto de forma atómica al finalizar; un fallo durante la ejecución nunca corrompe el estado parcial.

## Solución de problemas

Modos de fallo comunes y soluciones:

**`ECONNREFUSED 127.0.0.1:8188` en cualquier `sdlab generate` / `sdlab run generate` / `sdlab batch generate`**
ComfyUI no se está ejecutando. Inicie ComfyUI (`python main.py --listen 127.0.0.1 --port 8188`) y confirme con `curl http://127.0.0.1:8188/system_stats`. Para apuntar a un host/puerto diferente, establezca `COMFY_URL=http://host:port`.

**`missing checkpoint` / `LoRA weight not found`**
Su perfil de flujo de trabajo nombra un archivo de modelo que no está en la carpeta `models/checkpoints/` o `models/loras/` de ComfyUI. Abra `projects/<project>/workflows/profiles/<profile>.json`, localice el campo `checkpoint` o `lora` y, ya sea descargue el peso referenciado o reemplácelo por uno que ya tenga. Vuelva a ejecutar `sdlab project doctor --project <project>` para confirmar la solución.

**`sdlab project doctor` errores**
Doctor devuelve códigos de error estructurados. Algunos comunes:
- `E_PROJECT_NOT_FOUND` — el directorio del proyecto no existe en `projects/`. Verifique la ortografía.
- `E_CONFIG_INVALID` — uno de los cinco archivos de configuración JSON no pasó la validación del esquema. El campo `hint` indica el archivo y el campo incorrectos.
- `E_RECORD_DRIFT` — la huella digital de la configuración de un registro ya no coincide con su origen. Re-curate o re-asocie según lo sugerido en la pista.

**`No se especificó --project, se utiliza el valor predeterminado <name>`**
Una advertencia leve. Utilice `--project <name>` explícitamente para seleccionar el proyecto correcto y eliminar la advertencia.

**Problemas de memoria de VRAM relacionados con el estilo "painterly"**
Consulte el archivo `docs/internal/HANDOFF.md` para obtener información sobre la configuración del estilo "painterly". En resumen: reduzca la intensidad del desenfoque, disminuya el tamaño del lote o cambie a un modelo más pequeño en su perfil de trabajo.

**Informar de errores**
Registre un problema en https://github.com/mcp-tool-shop-org/style-dataset-lab/issues, incluyendo la versión de sdlab (`sdlab --version`), la versión de Node (`node -v`), el comando completo y la salida de error estructurada. Una plantilla para la presentación de informes de errores precompleta los campos.

## Seguridad

Solo funciona localmente. No hay telemetría, ni análisis, ni solicitudes externas. Las imágenes permanecen en tu GPU y sistema de archivos.

## Licencia

MIT

---

Creado por <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a
