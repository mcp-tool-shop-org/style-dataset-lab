# ferrochrome

A `style-dataset-lab` project — domain: **character-design**.

## Quick commands

```bash
# Validate that the scaffold is healthy
sdlab project doctor --project ferrochrome

# Generate candidates from the example prompt pack
sdlab generate inputs/prompts/example-wave.json --project ferrochrome

# Curate a candidate (approved | rejected | borderline)
sdlab curate <asset_id> approved "reads clean" --project ferrochrome

# Bind approved records to constitution rules
sdlab canon-bind --project ferrochrome

# Create a frozen dataset snapshot
sdlab snapshot create --project ferrochrome
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
