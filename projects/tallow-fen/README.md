# tallow-fen

A `style-dataset-lab` project — domain: **creature-design**. An original
**non-anime painterly** bog bestiary, generated natively on the studio's
verified **Qwen-Image** base (`project.json` → `defaults.base: "qwen-image"`).
No anime models, ever — see `memory/feedback_no_anime.md`.

## Quick commands

```bash
# Validate that the scaffold is healthy
sdlab project doctor --project tallow-fen

# Generate the first wave on Qwen-Image (start E:/AI/training/_watchdog.ps1 first)
sdlab generate inputs/prompts/tallow-fen-wave1.json --project tallow-fen

# Curate a candidate (approved | rejected | borderline)
sdlab curate <asset_id> approved "reads clean" --project tallow-fen

# Bind approved records to constitution rules
sdlab canon-bind --project tallow-fen

# Create a frozen dataset snapshot
sdlab snapshot create --project tallow-fen
```

## Project layout

- `project.json` — defaults (checkpoint, width, height, sampler)
- `constitution.json` — machine-readable style rules
- `canon/` — human-authored style reference (constitution.md, review-rubric.md)
- `inputs/prompts/` — generation prompt packs
- `outputs/candidates/` — raw generated PNGs
- `outputs/approved/` · `outputs/rejected/` · `outputs/borderline/` — curated outputs
- `records/` — provenance + judgment records (one JSON per candidate)
- `snapshots/` · `splits/` · `exports/` — frozen dataset artifacts

## Docs

- Handbook: https://mcp-tool-shop-org.github.io/style-dataset-lab/
- CLI reference: `sdlab --help` (or `sdlab <cmd> --help` for any command)

## TODO

- [ ] Fill in `canon/constitution.md` with your style rules
- [ ] Encode those rules in `constitution.json` for canon-bind
- [ ] Add at least one prompt pack under `inputs/prompts/`
- [ ] Run `sdlab project doctor` and fix any warnings
