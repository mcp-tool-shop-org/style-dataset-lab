# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Added — ai-toolkit adapter for Flux LoRA training (Flux slice 3)

- **`lib/adapters/ai-toolkit.js`** (new): Ostris ai-toolkit training package. Produces `dataset/<partition>/<record_id>.{png,txt}` + `metadata/<partition>.jsonl` + `ai-toolkit-config.yaml` at package root. The YAML config is populated from the profile and training manifest: `config.name = "{profile_id}-{source_export_id}"`, `model.name_or_path` from `profile.base_model_recommendations[0]`, `model.is_flux: true`, `model.quantize: true` (16GB-VRAM ceiling), `train.noise_scheduler: "flowmatch"`, `optimizer: "adamw8bit"`, `dtype: "bf16"`, multi-res `[512, 768, 1024]`, sample prompt seeded with the profile-derived style trigger.
- **Precondition:** the adapter requires `profile.target_family === 'flux'` and throws `ADAPTER_TARGET_FAMILY_MISMATCH` (input error, exit 1) otherwise. SDXL callers should use `diffusers-lora`.
- **Registered** in `ADAPTER_REGISTRY` so `listAdapters()`, `isRegisteredAdapter()`, `loadAdapter()`, and profile validation all pick it up automatically.
- **Flux profiles updated:** `character-style-lora-flux` and `environment-mood-lora-flux` now list `ai-toolkit` in their `adapter_targets`.
- **Runtime dep:** `yaml@^2.8.3` added for YAML emission.
- 8 new tests (`ai-toolkit-adapter.test.js` + 3 new cases in `training-adapters.test.js`). Tests 153 → 165.

## [3.1.0] - 2026-04-22

### Added — `--resume` for `generate` and `batch generate`

- **`sdlab generate --resume`** — skip subjects whose record JSON and output PNG are already on disk. Seeds remain stable: skipped slots still advance the seed counter so resumed runs are bit-identical to a fresh run that reaches the same point. Final summary now reports `(N errors, M resumed)`.
- **`sdlab batch generate --resume <batch_id>`** — re-runs only failed/missing slots in an existing batch, keeps the same `batch_id`, and inherits `mode_id`/`subject_id`/`theme`/`asset_ref` from the prior manifest. Surfaces "(C/T slots already complete)" in the header. Throws `BATCH_NOT_FOUND` for a bad id and `BATCH_NO_PROGRESS` for pre-checkpoint manifests that can't be partially resumed.
- **Manifest format:** `slots[].status` is now persisted (`'ok'` or `'error'`) so resume can distinguish failures from successes. Older manifests fall back to "selected_output truthy = success" for compatibility.
- New helpers: `buildCompletedSlotMap()`, `openBatchDirForResume()` in `lib/batch-runs.js`.
- 7 new tests in `tests/lib-pipeline/batch-resume.test.js`.

### Fixed — Deterministic SaveImage node selection (PB-003)

- **`lib/comfyui-output.js`** (new): `pickOutputImage(outputs, { preferNodeId })` selects the canonical SaveImage output deterministically. Previously, `comfyui-runner.js` and `generate.js` used `Object.values(outputs)` and broke on the first node with images — first-wins ordering depends on ComfyUI's execution scheduler, not the workflow graph.
- **Selection precedence:** explicit `preferNodeId` (from the workflow builder's `saveNodeId` or a brief's `expected_outputs.save_node_id`) → highest numeric node id (typical "final save" convention) → first iteration entry (only for non-numeric ids).
- `lib/adapters/comfyui-runner.js` and `scripts/generate.js` both updated to thread `saveNodeId` through to the picker.
- Run output records now include `comfy_node_id` so the chosen save node is auditable from the manifest.
- 9 new tests in `tests/lib-pipeline/comfyui-output.test.js`.

### Added — CI coverage reporting

- **`c8`** added as a `devDependency`; new `npm run coverage` script runs the full test suite under c8 with text + lcov + text-summary reporters (covering `lib/**/*.js`).
- **CI**: Node 22 matrix entry now runs `npm run coverage` and uploads `coverage/lcov.info` to Codecov via `codecov/codecov-action@v5` (`continue-on-error: true` so a Codecov outage never blocks the PR).
- **README**: CI and Codecov badges added beside the npm/license badges.
- **`.gitignore`**: `coverage/` and `.nyc_output/` excluded.
- Baseline coverage at this commit: **statements 40.6% / branches 70.7% / functions 54.0%** — meaningful coverage on `lib/snapshot.js`, `lib/split.js`, `lib/log.js`, `lib/args.js`, `lib/runtime-runs.js`; adapters and selection layers still uncovered (deferred to future passes).

### Fixed — Mobile nav on landing + handbook (SB-SDL-007)

- **`site/src/layouts/SiteLayout.astro`**: header was `hidden md:flex` for both the link nav and the npm/GitHub buttons, leaving phones with the brand mark and nothing else. Added a hamburger toggle (`md:hidden`) that opens a drawer containing all the same links plus npm/GitHub. Implemented as a `<details>`/`<summary>` so it works without any JavaScript or framework dependency.
- The desktop nav and the GitHub button still render unchanged at `md:` and up.

### Changed — Training adapter registry (DB-007)

- **`lib/training-adapters.js`** (new): explicit `ADAPTER_REGISTRY` with `loadAdapter()`, `listAdapters()`, `isRegisteredAdapter()`. Replaces the hand-maintained adapter list embedded in a `lib/training-packages.js` error string.
- **`lib/training-packages.js`**: dropped its private `loadAdapter()`; now imports from the registry. Unknown adapters throw `ADAPTER_NOT_REGISTERED` (input error, exit 1) with the available-adapter list always in sync. Registered-but-missing modules throw `ADAPTER_MODULE_LOAD_FAILED` (distinct from a typo).
- **`lib/training-profiles.js`**: `validateProfile()` now rejects profiles whose `adapter_targets[]` cite an unregistered adapter — surfaces typos at profile load time instead of at package-build time.
- 8 new tests in `tests/lib-pipeline/training-adapters.test.js`.

To add a new adapter (e.g. `kohya-lora`, `onedtrainer`): write `lib/adapters/<id>.js` exporting `buildPackage(opts)` and add a one-line entry to `ADAPTER_REGISTRY`. The error message, profile validation, and (eventually) CLI completion all pick it up automatically.

## [3.0.1] - 2026-04-21

### Fixed — Dogfood swarm health pass (Stage A: bugs & security)

- **Four Laws enforcement** (`lib/snapshot.js`, `lib/split.js`, `lib/export.js`):
  - Export now inherits `snapshot.config_fingerprint` instead of recomputing; throws `FINGERPRINT_DRIFT` on mismatch (Law 4).
  - Deterministic majority-lane per family with lexicographic tie-break, recorded in `audit.family_lane_decisions` (Law 3).
  - Unassigned-family fallback now throws instead of silently landing in train.
  - `existsSync` guards across snapshot/split/export/eval/training-manifest/training-package/impl-pack prevent ID collisions from overwriting frozen artifacts (Law 1).
  - `included.jsonl` entries now carry `rules_checked`, `profile_id`, and `config_fingerprint` for explainable inclusion (Law 2).
- **Security hardening**: path-traversal rejection on `record.asset_path` and all user-supplied `--source`/`--guide`/`--anchor`/`--ref`/`--outputs`/`--prompt-file`/`--packet-file`/`--domain` flags; URL validation on ComfyUI endpoints; safe filename regex at selection boundaries.
- **CLI structured errors**: ~25 scripts converted from raw `throw new Error` to `inputError`/`runtimeError` so exit codes are correct (1 = user error, 2 = runtime).
- **Pipeline correctness**: brief fingerprint uses recursive `canonicalize()` — deterministic across nested key reordering; override precedence fixed (`||` → `??` so legit zero/empty overrides are preserved); negative-prompt dedup switched from substring to token-exact match; adapter output filenames keyed by `record.id` to prevent basename collisions silently dropping records.
- **Re-ingest**: now actually copies images to `outputs/candidates/` instead of writing records that point at missing files.
- **Curate ordering**: `curate.js` moves image first, then updates record; bulk-curate trio gained `--dry-run` and standard error handling.

### Added — Dogfood swarm humanization pass (Stage B/C)

- **ComfyUI progress**: `submitAndWait` emits heartbeats every 15 s (queued → generating → completed); bails fast on `execution_error` or unknown status shapes instead of timing out silently.
- **Atomic manifest writes**: run/batch manifests use temp-file + rename; `checkpointRunManifest` saves progress after every slot so a crash no longer orphans GPU work.
- **`schema_version` enforcement**: every manifest (`snapshot`, `split`, `export`, `eval-pack`, `eval-run`, `training-manifest`, `training-package`, `implementation-pack`) now stamps `schema_version: '2.2.0'` with warn-on-mismatch loaders.
- **Export truthfulness**: tracks `expected`/`actual`/`failed` counts with per-record reasons and stderr warnings (no more silent-skip under `catch {}`).
- **Snapshot resilience**: malformed record JSON lands in `errors[]` instead of aborting the snapshot.
- **Split audit**: `deviation_from_target` per lane + `overall_deviation_score` in audit output.
- **Eval scorecards**: `sample_record_ids` up to 5 per failure bucket so operators can investigate.
- **CLI help**: `sdlab <cmd> --help` now works for 15 top commands via `HELP_TEXT` registry.
- **Did-you-mean**: hand-rolled Levenshtein suggestion for typo'd commands and flags.
- **`--project` fallback**: loud 2-line stderr warning when falling back to `star-freight` (silence with `SDLAB_QUIET_FALLBACK=1`).
- **Signal handling**: `SIGINT` (130), `SIGTERM` (143), `uncaughtException`, `unhandledRejection` handlers at `main()` so Ctrl+C surfaces a clean message.
- **ETA**: generate and batch-generate print ETA every 5 items with rolling averages.
- **`result()`/`success()` helpers**: artifact paths always print regardless of `--quiet`.
- **`sdlab init`**: scaffolded projects now get a `README.md` with quick commands, layout, and TODO sections.
- **Per-domain example waves**: all 5 domain templates ship `inputs/prompts/example-wave.json` with subjects matching their lane `id_patterns`.
- **Troubleshooting section**: README covers ComfyUI connection failure, missing weights, doctor errors, `--project` fallback, and bug reporting.
- **Install as primary CTA**: landing page leads with a copy-to-clipboard install command; `og:image`/`twitter:card` meta added via `SiteLayout`.

### Changed

- Moved `HANDOFF.md`, `WAVE_PLAN.md`, `WAVE27A_SESSION_STATE.md` to `docs/internal/` with a README explaining the archive.
- `lib/deprecation.js`: `--game` deprecation target bumped from "v3.0" (lying, package is 3.0) to "v4.0".
- Handbook `reference.md` and `architecture.md` rewritten against the v3.0 CLI surface (`--project`, `projects/<name>/`); `--game` demoted to a Legacy section.
- One-off Star Freight wave-curate scripts excluded from the npm tarball via `files`-field negations (137 → 135 files, 179.3 → 173.9 kB).

### Infrastructure

- **Test suite**: 0 → 98 tests across 12 files (`tests/lib-pipeline/`, `tests/lib-dataset/`, `tests/cli-scripts/`).
- **CI**: added `pull_request` trigger; `publish.yml` now runs `npm ci` + `npm run verify` + `npm test` + tag-vs-version guard before `npm publish`; `permissions: contents: read` and `persist-credentials: false` across all workflows; npm cache on every `setup-node`.
- **`package-lock.json`** regenerated from stale v2.2.1 to v3.0.1.
- **Governance**: added `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `.github/ISSUE_TEMPLATE/{bug_report,feature_request}.md`, `.github/PULL_REQUEST_TEMPLATE.md`.
- **Dependabot**: groups restricted to `minor`/`patch` so breaking majors get individual PRs.

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

## [2.6.0] - 2026-04-16

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
