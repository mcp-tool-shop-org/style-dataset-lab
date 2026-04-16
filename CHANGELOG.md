# Changelog

All notable changes to this project will be documented in this file.

## [2.6.0] - 2026-07-01

### Added

- **Batch production modes (Phase 4D)** — coordinated multi-slot generation with reviewable sheet output
  - `sdlab batch generate --mode <id>` — execute a batch production mode (expression sheets, environment boards, etc.)
  - `sdlab batch show [batch-id]` — list all batches or show batch details
  - `sdlab batch sheet <batch-id>` — re-render batch sheet from saved manifest
  - `--dry-run` flag prepares batch directory and briefs without submitting to ComfyUI
- **Batch modes** (`lib/batch-modes.js`) — load, validate, and list batch mode definitions from `workflows/batch-modes/`
- **Batch compiler** (`lib/batch-compiler.js`) — expand one batch mode into multiple slot briefs with controlled per-slot deltas
- **Batch runs** (`lib/batch-runs.js`) — batch directory creation (`batch_YYYY-MM-DD_NNN`), coordinated slot execution, manifest save/load
- **Batch sheet renderer** (`lib/batch-sheet-render.js`) — HTML review surfaces with CSS grid layout, dark theme, zero dependencies
- **4 starter batch modes** for Star Freight: expression-sheet, environment-board, silhouette-pack, continuity-variants
- **JSON schemas** for batch mode definitions and batch manifests (`schemas/`)
- Doctor validates batch mode definitions (batch_type, subject_mode, slot uniqueness, layout, workflow references)
- Init scaffolds `workflows/batch-modes/` and `batches/` directories
## [3.0.0] - 2026-04-16

### Added

- **Selection + Reintegration (Phase 4E)** — close the production loop from generation back to corpus
  - `sdlab select --run <id> --approve <files>` — select approved outputs from a run
  - `sdlab select --batch <id> --approve <slot:file,...>` — select approved outputs from a batch
  - `sdlab selection show [selection-id]` — list selections or show details
  - `sdlab reingest selected --selection <id>` — re-ingest selected outputs as candidate records
  - `--reason` and `--tags` flags for selection context
  - `--dry-run` and `--json` output support
- **Selection engine** (`lib/selections.js`) — create selection artifacts from runs or batches
  - Selection ID generation (`selection_YYYY-MM-DD_NNN`)
  - Run and batch selection with output validation
  - Chosen files copied into `selections/<id>/chosen/`
  - Manifest, summary.json, and summary.md written per selection
- **Generated provenance** (`lib/generated-provenance.js`) — build provenance blocks for re-ingested records
  - Traces back through run → brief → workflow → seed → config fingerprint
  - Normalizes run and batch source context into a single shape
- **Re-ingest from selections** (`lib/reingest-selected.js`) — create candidate records from selections
  - Records carry `source: generated` provenance with full generation provenance block
  - Images copied to `inbox/generated/`
  - Records tagged: `generated`, `selected`, workflow ID, subject ID
  - No auto-bypass around review — records are staged for normal curation
  - Provenance log written as `provenance.jsonl`
- **JSON schemas** for selections and generated records (`schemas/`)
- Doctor validates new project directories (`selections/`, `inbox/generated/`)
- Init scaffolds `selections/` and `inbox/generated/` directories

### Changed

- **README** rewritten to describe the full production loop: canon → dataset → training → brief → run → critique → batch → select → re-ingest
- **Landing page** updated: new headline, description, 4-tab preview (Start, Dataset, Produce, Close the loop), 7 feature cards including production workflow and selection
- **Handbook** updated: index shows production loop diagram, new [Production Loop](handbook/production-loop/) page with complete end-to-end walkthrough
- **Package metadata** updated: description, keywords (`generation-workflow`, `batch-production`, `reintegration`), version badge
- Version bumped to **v3.0.0** — the repo is now a full production workbench, not just a dataset preparation system
## [2.5.0] - 2026-04-16

### Added

- **Critique + Refine loop (Phase 4C)** — inspect run outputs and generate focused next-pass briefs
  - `sdlab critique --run <id>` — generate structured critique of a completed run
  - `sdlab critique show --run <id>` — display saved critique (text, JSON, markdown)
  - `sdlab refine --run <id> --pick <file>` — generate refined next-pass brief from critique
  - CLI override flags: `--preserve`, `--push`, `--suppress` for manual delta control
- **Critique engine** (`lib/critique-engine.js`) — brief-driven candidate analysis
  - 10 critique dimensions activated by workflow canon focus and drift guards
  - Per-candidate structured notes: strengths, drift issues, preserve/correct next pass
  - Run-level recommendation: accept_one, refine_from_one, rerun_broader, discard_run
  - Workflow-specific emphasis by output mode (portrait, expression, moodboard, etc.)
- **Refine briefs** (`lib/refine-briefs.js`) — delta-layered brief generation
  - Preserve/push/suppress instructions derived from critique + CLI overrides
  - Prompt refinement: original prompt preserved, delta instructions appended
  - Negative prompt extension: suppress items added without replacing existing negatives
  - Refined briefs point back to parent brief + source run + picked candidate
- **JSON schemas** for critique reports and refined briefs (`schemas/`)
- Critique and refine artifacts stored in run directory: `runs/<id>/critique.json`, `runs/<id>/refine/`

## [2.4.0] - 2026-04-16

### Added

- **ComfyUI runtime adapter (Phase 4B)** — execute compiled briefs through ComfyUI and capture run artifacts
  - `sdlab run generate --brief <id>` — execute a brief through ComfyUI, capture outputs to runs/
  - `sdlab run show <id>` — show run manifest and results
  - `sdlab run list` — list all runs for a project
  - `--dry-run` flag prepares run directory without submitting to ComfyUI
  - `--seed <n>` override for reproducible generation
- **Run management** (`lib/runtime-runs.js`) — run ID generation (`run_YYYY-MM-DD_NNN`), seed plans (fixed/increment/random), run directory preparation, manifest save/load
- **ComfyUI workflow adapter** (`lib/adapters/comfyui-workflows.js`) — builds ComfyUI prompt graphs from compiled briefs, template resolution by output mode
- **ComfyUI runner** (`lib/adapters/comfyui-runner.js`) — orchestrates seed plan → graph build → submit → poll → download → manifest for each image
- **Run summaries** (`lib/run-summary.js`) — generates summary.json and summary.md in each run directory
- **Runtime templates** (`runtime/comfyui/txt2img-standard.json`) — declarative workflow template metadata
- Doctor validates runtime templates (Section 10)
- `runs/` added to project scaffold

## [2.3.0] - 2026-04-15

### Added

- **Production workbench spine (Phase 4A)** — workflow profiles and brief compiler
  - `sdlab workflow list` — list workflow profiles for a project
  - `sdlab workflow show <id>` — show workflow profile details
  - `sdlab brief compile` — compile a deterministic generation brief from project truth
  - `sdlab brief show <id>` — show compiled brief (text, JSON, or markdown)
- **Workflow profiles** — production recipes defining output shape, canon constraints, drift guards, and runtime defaults
  - 6 output modes: portrait_set, expression_sheet, variant_pack, moodboard, silhouette_sheet, turnaround
  - 12 canon focus categories: silhouette, material_language, palette, anatomy, costume_logic, era_logic, scale_logic, lighting, surface_wear, gesture, composition, faction_read
  - Subject mode enforcement: required, optional, forbidden
- **Brief compiler** — merges 6 layers of project truth into a frozen generation contract:
  - Project canon → lane config → subject identity → training asset hints → workflow profile → CLI overrides
  - Structured prompt assembly (no freeform prompt soup)
  - Deterministic output: same inputs produce identical briefs
  - Config fingerprint (SHA-256) for change detection
  - Outputs JSON + human-readable Markdown
- **3 starter workflows for Star Freight**: character-portrait-set, expression-sheet, environment-moodboard
- **10 domain template workflows** across 5 domains (game-art, character-design, creature-design, architecture, vehicle-mech)
- **New library modules:** `lib/workflow-profiles.js`, `lib/brief-compiler.js`, `lib/brief-render.js`
- **Doctor validates workflow profiles** — checks schema, lane references, subject mode, runtime defaults
- **Init scaffolds `workflows/profiles/` and `briefs/`** directories and copies domain workflow templates

### Key properties

- Workflow profiles are NOT training profiles — they drive generation, not training
- Briefs are frozen contracts — the creative runtime boundary between planning and execution
- Subject constraints are hard when subject_mode = required (fail loudly if missing)
- Drift guards appear as explicit warnings, never hidden in metadata

## [2.2.0] - 2026-04-16

### Added

- **Training + implementation spine** -- complete model-asset pipeline from export package to trained asset
  - `sdlab training-profile list/show` -- training profile management (what kind of model asset to produce)
  - `sdlab training-manifest create/validate/show/list` -- frozen training contracts with export hash and config fingerprint
  - `sdlab training-package build/show/list` -- trainer-ready packages with adapter boundary
  - `sdlab eval-run create/score/show/list` -- score generated outputs against eval packs, produce scorecards
  - `sdlab implementation-pack build/show/list` -- prompt examples, known failures, subject continuity, reingest guide
  - `sdlab reingest generated/audit` -- re-ingest accepted generated outputs as new records with provenance
- **Adapter system** for trainer-specific packaging:
  - `generic-image-caption` -- image folders + metadata JSONL
  - `diffusers-lora` -- image + caption .txt sidecars for diffusers fine-tuning
- **Two starter training profiles** for Star Freight: `character-style-lora`, `environment-mood-lora`
- **New library modules:** `lib/training-profiles.js`, `lib/training-manifests.js`, `lib/training-packages.js`, `lib/eval-runs.js`, `lib/implementation-packs.js`, `lib/reingest.js`, `lib/adapters/generic-image-caption.js`, `lib/adapters/diffusers-lora.js`

### Key properties

- Training manifests are frozen -- if config, export, or profile changes, a new manifest is required
- Adapters transform layout but never mutate inclusion or split truth
- Generated outputs re-enter through normal review (no bypass)
- Every eval run links back to a training manifest and eval pack (no orphans)

## [2.1.0] - 2026-04-16

### Added

- **Dataset spine** -- complete snapshot-to-export pipeline with proof at every stage
  - `sdlab snapshot create/list/show/diff` -- frozen, deterministic record selections with config fingerprinting
  - `sdlab eligibility audit` -- training eligibility evaluation with explicit reason traces
  - `sdlab split build/list/show/audit` -- subject-isolated, lane-balanced train/val/test splitting
  - `sdlab card generate` -- dataset card generation (markdown + JSON twin)
  - `sdlab export build/list` -- self-contained export packages with manifest, metadata, images, splits, checksums
  - `sdlab eval-pack build/list/show` -- canon-aware eval packs (4 task types)
- **New library modules:**
  - `lib/snapshot.js` -- snapshot creation, loading, diffing
  - `lib/eligibility.js` -- eligibility evaluation with reason traces and exclusion categorization
  - `lib/split.js` -- subject isolation (identity/lineage/suffix), mulberry32 PRNG, lane-balanced splitting, leakage audit
  - `lib/card.js` -- dataset card rendering from snapshot + split + config
  - `lib/export.js` -- export package builder with checksums and reproducibility manifest
  - `lib/eval-pack.js` -- four eval task types (lane coverage, forbidden drift, anchor/gold, subject continuity)
- **Selection, split, and export profiles** in `lib/config.js` with sensible defaults
- **Detection functions** (`detectLane`, `detectGroup`) extracted from canon-bind into `lib/config.js` for reuse

### Key properties

- Snapshots are frozen -- once created, never silently changes
- Inclusion is explainable -- every record has a reason trace
- Splits preserve canon truth -- no subject family appears in multiple partitions
- Exports are reproducible -- rebuildable from snapshot ref + split ref + config fingerprint

## [2.0.0] - 2026-04-15

### Breaking changes

- **`games/` renamed to `projects/`** -- all project data now lives under `projects/<name>/`
- **`--game` renamed to `--project`** -- `--game` still works with a deprecation warning (will be removed in v3.0)
- **Canon-bind loads from config files** -- rules, lanes, rubric, and terminology are now per-project JSON, not hardcoded

### Added

- **`sdlab` CLI** -- unified command-line interface (`bin/sdlab.js`)
  - `sdlab init <name> --domain <domain>` -- scaffold projects from domain templates
  - `sdlab project doctor` -- validate project config and structure
  - `sdlab bind`, `sdlab curate`, `sdlab generate`, etc. -- all pipeline commands
- **Shared library** (`lib/`) -- 6 modules replacing duplicated code across 13 scripts
  - `lib/args.js` -- unified argument parser with `--project` and deprecated `--game` support
  - `lib/paths.js` -- centralized path resolution
  - `lib/comfyui.js` -- ComfyUI HTTP client (extracted from 5 scripts)
  - `lib/config.js` -- per-project JSON config loader
  - `lib/records.js` -- record I/O utilities
  - `lib/deprecation.js` -- one-shot deprecation warnings
- **Per-project config files** -- 5 JSON files per project:
  - `project.json` -- identity, domain, generation defaults
  - `constitution.json` -- rules with rationale templates
  - `lanes.json` -- subject lanes with regex detection patterns
  - `rubric.json` -- scoring dimensions, thresholds, failure-to-rule mappings
  - `terminology.json` -- group vocabulary with separate `id_detection_order` and `prompt_detection_order`
- **5 domain starter templates** -- game-art, character-design, creature-design, architecture, vehicle-mech
- **Training profile placeholders** in domain templates (eligible lanes, thresholds, export format)

### Changed

- Canon-bind is now fully config-driven -- loads rules, lanes, dimensions, thresholds, group vocabulary, and rationale templates from per-project JSON files
- Missing config files cause hard failure with actionable error messages (no silent fallback)
- All 10 CLI-exposed scripts refactored to export `run(argv)` for CLI dispatch
- Net code reduction: ~305 lines removed from deduplication

### Migration

1. Rename `games/` to `projects/`
2. Use `--project` instead of `--game` (or keep `--game` with deprecation warning)
3. For canon-bind: add 5 JSON config files to your project (use `sdlab init` as reference)

Star Freight config files are included as the canonical example.

## [1.2.0] - 2026-04-14

- Added `templates/` with blank constitution, review rubric, and example prompt pack
- npm package now ships scripts + templates only (zero game data)
- Fixed game data leak in v1.0.0/v1.1.0 npm packages (games/ was included in tarball)
- All docs reframed around the pipeline (canon, prompts, generate, curate, bind, compare, export)
- README, handbook, and landing page updated for v1.2.0

## [1.1.0] - 2026-04-14

- Monorepo restructure: each game lives in `games/<name>/` with isolated canon, records, and assets
- All scripts accept `--game <name>` flag (default: `star-freight`)
- Existing Star Freight data moved to `games/star-freight/`
- Translations added (7 languages: ja, zh, es, fr, hi, it, pt-BR)

## [0.5.0] - 2026-04-14

- Identity packet system for waves 27A, 27B, and 28
- Painterly pipeline for stylized asset generation

## [0.4.0] - 2026-03-28

- Wave 26: station identities
- Pairwise comparison tooling for quality ranking

## [0.3.0] - 2026-03-15

- Wave 25: alien species generation
- Negative prompt fix (`human` in negative for alien anatomy)
- Wave 25b: regeneration pass for failed outputs

## [0.2.0] - 2026-02-20

- Waves 11-24: expanded category coverage
- Canon binding system linking outputs to design intent

## [0.1.0] - 2026-01-10

- Initial scaffold and ComfyUI integration
- Waves 1-10: character costumes (gritty space theme)
- First export: 570 training units in TRL format
