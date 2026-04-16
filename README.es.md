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

Escriba sus reglas visuales. Genere arte. Evalúe cada imagen según esas reglas. Entregue los resultados como datos de entrenamiento versionados y auditables.

Style Dataset Lab conecta lo que ha escrito sobre su estilo artístico con el conjunto de datos con el que realmente entrena. Usted define una constitución: reglas de silueta, restricciones de paleta, lenguaje de materiales, cualquier cosa que sea importante para su proyecto. El proceso genera candidatos, los evalúa según esas reglas y empaqueta el trabajo aprobado en conjuntos de datos reproducibles donde cada registro explica por qué se incluyó.

El ciclo se cierra: entrena un modelo, genera nuevas salidas, evalúalas según el mismo criterio y vuelve a incluir lo que cumple los requisitos. El conjunto de datos crece y las reglas se mantienen.

## El proceso

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

Esa última instrucción es clave. Las salidas generadas vuelven a pasar por el mismo proceso de revisión que todo lo demás. El ciclo se cierra.

## Lo que produce

Siete artefactos versionados y con sumas de verificación. Cada uno tiene un enlace a sus predecesores para que pueda rastrear cualquier registro de entrenamiento hasta la regla que lo aprobó.

| Artefacto. | Qué es. |
|----------|-----------|
| **Snapshot** | Selección de registros congelada con huella de configuración. Cada inclusión tiene una razón explícita. |
| **Split** | Partición de entrenamiento/validación/prueba donde las familias de sujetos nunca cruzan límites. |
| **Export package** | Conjunto de datos autocontenido: manifiesto, metadatos, imágenes, divisiones, tarjeta del conjunto de datos, sumas de verificación. |
| **Eval pack** | Tareas de prueba conscientes del criterio: cobertura de áreas, desviación prohibida, referencia/oro, continuidad del sujeto. |
| **Training package** | Diseño listo para el entrenamiento a través de adaptadores (`diffusers-lora`, `generic-image-caption`). La misma información, en un formato diferente. |
| **Eval scorecard** | Resultado de aprobación/reprobación por tarea, según la evaluación de las salidas generadas. |
| **Implementation pack** | Ejemplos de indicaciones, fallos conocidos, pruebas de continuidad y guías para la inclusión. |

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

## Seguridad

Solo funciona localmente. No hay telemetría, ni análisis, ni solicitudes externas. Las imágenes permanecen en tu GPU y sistema de archivos.

## Licencia

MIT

---

Creado por <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a
