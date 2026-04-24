---
title: Canon Build — Three Projections
description: sdlab canon build turns a typed canon entity store into three projections (dataset.jsonl + prompts/*.j2 + context/*.md), feeding training adapters, ComfyUI workflows, and Role OS drafting from one canonical source.
sidebar:
  order: 8
---

`sdlab canon build` is the bridge between a project's typed canon entity store and the three places canon is consumed:

- `dataset.jsonl` → training adapters (generic-image-caption, diffusers-lora, ai-toolkit)
- `prompts/<entity_id>.j2` → ComfyUI workflow profiles at generation time
- `context/<entity_id>.md` → Role OS dispatch for dialogue / encounter drafting roles

Full scoping decisions (D1–D9) live in `memory/three-projection-build-research-2026-04-24.md`. This page is the how-to.

## The canon → projection pipeline

```
canon/<type>/*.md
   └── parse ─► emitter ─► { caption, prompt, context }
                              │        │         │
                              ▼        ▼         ▼
                   dataset.jsonl  prompts/*.j2  context/*.md
```

Each canon entry produces exactly one row, one prompt template, and one context file. The same build run stamps all three with the canon commit SHA (or a `content-sha-...` fallback when the canon directory isn't under git), so every downstream consumer can answer "which canon state produced this artifact?"

## Configure

Create `projects/<name>/canon-build/config.json`:

```json
{
  "project_id": "greek-rpg",
  "canon_root": "F:/AI/greek-rpg/canon",
  "schema_dir": "F:/AI/greek-rpg/canon/schemas",
  "entity_dirs": {
    "monster.schema.json":   "monsters",
    "character.schema.json": "characters",
    "deity.schema.json":     "deities",
    "location.schema.json":  "locations",
    "relic.schema.json":     "relics"
  },
  "schema_to_lane": {
    "monster.schema.json":   { "source": "constant", "value": "creature" },
    "character.schema.json": { "source": "field", "field": "visual.art_lane" },
    "deity.schema.json":     { "source": "field", "field": "visual.art_lane" },
    "location.schema.json":  { "source": "field", "field": "visual.art_lane" },
    "relic.schema.json":     { "source": "field", "field": "visual.art_lane" }
  },
  "context_limits": {
    "default":  { "max_lines": 300 },
    "location": { "max_lines": 450 }
  },
  "profile_id": "character-style-lora-flux"
}
```

- `schema_to_lane.<name>.source: "field"` reads an entry's lane from its frontmatter (typically `visual.art_lane`).
- `schema_to_lane.<name>.source: "constant"` pins every entry of that schema to a fixed lane. Monster entries use this because `monster.schema.json` was drafted before the lane pattern landed.
- `profile_id` selects the training profile used for caption rendering — the build delegates to the profile's `caption_strategy` and `trigger_override`, preserving the captions-are-load-bearing invariant.

## Run

```bash
sdlab canon build --project greek-rpg
```

Output lands at `projects/greek-rpg/canon-build/<canon_sha>/`:

```
<canon_sha>/
  dataset/
    all.jsonl                      # union of all rows
    creature-train.jsonl           # one per (lane × partition)
    portrait-train.jsonl
    ...
  prompts/
    nemean-lion.j2
    heracles.j2
    ...
  context/
    nemean-lion.md
    heracles.md
    ...
  manifest.json                    # per-entity hashes + stats + audit
```

Frequently-used flags:

- `--full` — ignore cache hits; rebuild every entity
- `--no-cache` — neither read nor write the cache this run
- `--dry-run` — walk + resolve + plan; write nothing (exits 0 on success)
- `--only heracles,nemean-lion` — limit the build to specific ids
- `--json` — emit a machine-readable result summary

## Projection contracts

### `dataset.jsonl`

One row per entity × approved reference plate × lane. Key fields:

| Field | Source |
|---|---|
| `schema_version` | `canon-build-dataset-1.0` |
| `generated_from` | git SHA of canon, or `content-sha:...` fallback |
| `entity_id` | entry's `id` field |
| `schema_kind` | `monster` / `character` / `deity` / `location` / `relic` |
| `lane` | resolved per D3 (`visual.art_lane` or constant) |
| `partition` | `train` / `val` / `test` (MVP: always `train`) |
| `asset_path` | `visual.reference_plate_uri` when present; else null |
| `caption` | rendered via `captions.js` using the profile's strategy |
| `trigger` | `trigger_override` or profile-derived |
| `entry_hash` | cache key — sha256(entry body \|\| schema_version \|\| build_config \|\| project_fingerprint) |

Training adapters read these rows directly. Per-character LoRAs set `entity_id_scope: "<id>"` on their profile and the adapter filters the row stream to just that subject (D8).

### `prompts/<entity_id>.j2`

Jinja2 templates emitted once per entity; rendered at workflow-invocation time inside the ComfyUI adapter (future slice). Template variables supplied by the adapter at render time:

| Variable | Meaning |
|---|---|
| `trigger` | World LoRA trigger (stacked workflow profile's default) |
| `character_trigger` | per-character LoRA trigger, optional |
| `canon.*` | namespace object carrying the entity's schema-projected fields |
| `negative_base` | pre-rendered negative-prompt string from `forbidden_inputs` |

The template separates positive and negative halves with a literal `---` line; the ComfyUI adapter splits on it after rendering.

### `context/<entity_id>.md`

Per-entity narrative block for Role OS drafting. Carries provenance frontmatter (`entity_id`, `schema_kind`, `generated_from`, `entry_hash`) plus H2 sections populated from the schema's narrative fields. Default line cap is 300; location entries typically need 450 and can override via `context_limits.location.max_lines`.

## Incremental rebuild

The build is diff-based by default. An entity's cache key is the SHA-256 of:

- the canon entry body,
- the schema's `version` (or SHA-fallback),
- the build config JSON,
- the project config fingerprint (from `snapshot.js` — same fingerprint `snapshot` already uses).

A cache hit bypasses the emitter; a cache miss runs it and populates the cache. `--full` ignores the cache entirely.

Any schema file change, config file change, or project fingerprint change triggers a full rebuild automatically — the per-entity hash changes because one of its inputs did. Schema evolution is the most common real-world case: bumping `version: "1.0.0"` → `"1.0.1"` invalidates every entry that schema validates.

## Caption-bleed guard

The emitter for each schema reads **only frontmatter fields** when building the caption and the Jinja prompt template. The entry's Markdown body feeds **only** `context/<id>.md`. This wall is enforced in the emitter code and pinned by a cross-schema test that checks for body vocabulary leaking into captions.

Never add a caption strategy that reads `entry.body` — it reintroduces exactly the prompt-bleed antipattern `feedback_captions_are_load_bearing.md` was written to prevent.

## Bridge to the two-LoRA contract

- World LoRA training: profile's `eligible_lanes` filters dataset rows by `row.lane`.
- Per-character LoRA training: profile's `entity_id_scope` filters rows to `row.entity_id === entity_id_scope`. Same dataset, different filter.
- `training_hyperparameters` (rank/alpha/steps) threading is unchanged — the build is agnostic to hyperparameters; the adapter reads them at package time.
- `trigger_override` flows through `captions.js` unchanged; the build passes the training profile in and captions are rendered by the existing strategies.

## Out of scope (tracked for future slices)

- **Validation against JSON Schema.** The build reads schemas for version resolution but doesn't yet validate entries. A `--validate` flag + structured `SCHEMA_VALIDATION_FAILED` error is a follow-up.
- **Partitioning.** Everything ships to `train` today. A split mechanism for canon-build datasets is a separate slice.
- **ComfyUI render-time integration.** The `.j2` templates are emitted but not yet consumed by the ComfyUI adapter; that's the next bridge.
- **Cross-reference validation.** Dangling `target_id` references in narrative.relationships are not yet caught by the build.

## References

- Research deliverable + D1–D9 decisions: `memory/three-projection-build-research-2026-04-24.md`
- Architecture lineage: G-KMS paper (entity store → projections), Urdr "world bible as data"
- Pinned by tests: `tests/lib-canon-build/`, `tests/lib-pipeline/rows.test.js`, `tests/lib-pipeline/training-profiles.test.js`
