# portlight-ships

A `style-dataset-lab` project — domain: **vehicle-mech**.

## Quick commands

```bash
# Validate that the scaffold is healthy
sdlab project doctor --project portlight-ships

# Generate candidates from the example prompt pack
sdlab generate inputs/prompts/example-wave.json --project portlight-ships

# Curate a candidate (approved | rejected | borderline)
sdlab curate <asset_id> approved "reads clean" --project portlight-ships

# Bind approved records to constitution rules
sdlab canon-bind --project portlight-ships

# Create a frozen dataset snapshot
sdlab snapshot create --project portlight-ships
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
