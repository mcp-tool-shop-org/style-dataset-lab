# Changelog

All notable changes to this project will be documented in this file.

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
