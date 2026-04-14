# Changelog

All notable changes to this project will be documented in this file.

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
