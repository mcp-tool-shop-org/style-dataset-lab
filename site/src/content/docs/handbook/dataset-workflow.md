---
title: Dataset Workflow
description: End-to-end dataset production — from curated records to versioned export packages and eval packs.
sidebar:
  order: 2
---

This page walks through one complete dataset production path: from an existing project with curated, canon-bound records to a versioned export package and eval pack.

## Prerequisites

Before starting, you need a project with:

- Curated records (at least some `approved` with per-dimension scores)
- Canon binding (`sdlab bind` has been run, producing pass/fail/partial assertions)
- A valid project config (`sdlab project doctor` passes)

If you don't have curated records yet, see [Getting Started](./getting-started/) first.

## Step 1: Check eligibility

Before creating a snapshot, audit which records qualify for inclusion.

```bash
sdlab eligibility audit --project my-project
```

This evaluates every record against the default selection profile:

- Requires human judgment (no un-reviewed records)
- Requires `approved` status
- Requires canon binding (at least one assertion)
- Requires minimum 50% pass ratio

The audit shows your eligibility rate and breaks down exclusion reasons. Near-miss records (1 failing check) are highlighted as improvement opportunities.

## Step 2: Create a snapshot

A snapshot freezes a deterministic selection of eligible records at a point in time.

```bash
sdlab snapshot create --project my-project
```

What this produces:

- `snapshots/<id>/snapshot.json` -- manifest with config fingerprint, counts, selection profile
- `snapshots/<id>/included.jsonl` -- one line per included record with reason trace
- `snapshots/<id>/excluded.jsonl` -- one line per excluded record with exclusion reasons
- `snapshots/<id>/summary.json` -- lane and faction distribution

**Key property:** the same project config and records always produce the same snapshot. The config fingerprint (SHA-256 of all 5 config files) proves this.

Use `sdlab snapshot list` and `sdlab snapshot diff <a> <b>` to track changes over time.

## Step 3: Build a split

A split assigns snapshot records to train/val/test partitions.

```bash
sdlab split build --project my-project
```

Two laws govern splitting:

1. **Subject isolation** -- records sharing a subject family always land in the same split. Family is determined by `identity.subject_name`, lineage chain, or ID suffix stripping.
2. **Lane balance** -- families are grouped by primary lane, shuffled with a seeded PRNG, and assigned to maintain target ratios per lane.

Default profile: 80/10/10 split, seed 42, subject-isolated strategy.

Verify the split:

```bash
sdlab split audit <split-id> --project my-project
```

The audit checks for subject leakage (must be zero) and reports lane balance across partitions.

## Step 4: Generate a dataset card

```bash
sdlab card generate --project my-project
```

This produces `dataset-card.md` and `dataset-card.json` in the project root, documenting:

- Selection criteria and eligibility profile
- Split strategy and partition sizes
- Lane balance table
- Quality gates (constitution rules, rubric dimensions)
- Provenance chain

## Step 5: Build an export package

An export package is a self-contained dataset directory.

```bash
sdlab export build --project my-project
```

Output structure:

```
exports/<id>/
  manifest.json      # snapshot ref, split ref, profile, checksums
  metadata.jsonl     # one record per line (full provenance + judgment + canon)
  images/            # symlinks to approved images (use --copy for real copies)
  splits/
    train.jsonl
    val.jsonl
    test.jsonl
  dataset-card.md
  dataset-card.json
  checksums.txt      # BSD format: SHA256 (<path>) = <hash>
  summary.json
```

The manifest stores everything needed to rebuild: snapshot ref, split ref, export profile, and config fingerprint. This is a reproducibility contract.

Use `sdlab export list` to see all packages.

## Step 6: Build an eval pack

Eval packs are canon-aware test instruments for future model verification.

```bash
sdlab eval-pack build --project my-project
```

Four task types:

| Task | Purpose | Records |
|------|---------|---------|
| **Lane coverage** | Best approved records per lane (highest pass ratio) | Representative set |
| **Forbidden drift** | Rejected/borderline records with violated rules | What the model must NOT produce |
| **Anchor/gold** | Highest pass-ratio records per faction | Gold standard references |
| **Subject continuity** | Same-subject record groups | Identity consistency testing |

Use `sdlab eval-pack show <id>` to inspect the pack contents.

## Step 7: Hand off to repo-dataset (optional)

`sdlab` defines the dataset. [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) renders it into specialized training formats.

```bash
# From the export package, produce format-specific outputs
repo-dataset visual generate ./projects/my-project --format trl
repo-dataset visual generate ./projects/my-project --format llava
```

This boundary matters: `sdlab` decides what is in the dataset and how it is split. `repo-dataset` never makes inclusion decisions -- it only converts the canonical package into downstream formats.

## Full example: Star Freight

```bash
# Clone the repo
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab

# Validate the project
sdlab project doctor --project star-freight

# Run the full dataset spine
sdlab snapshot create --project star-freight
sdlab split build --project star-freight
sdlab split audit <split-id> --project star-freight
sdlab export build --project star-freight
sdlab eval-pack build --project star-freight
sdlab card generate --project star-freight
```

Star Freight results: 839/1,182 eligible (71%), 667 train / 88 val / 84 test, zero subject leakage, 417 isolated families, 78 eval records across 4 task types.

## Custom profiles

Override defaults by creating profile JSON files in your project:

- `selection-profiles/<name>.json` -- eligibility criteria
- `split-profiles/<name>.json` -- split ratios, seed, strategy
- `export-profiles/<name>.json` -- metadata fields, image strategy

Then pass `--profile <name>` to the relevant command.
