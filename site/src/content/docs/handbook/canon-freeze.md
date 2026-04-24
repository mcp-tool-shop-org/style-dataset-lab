---
title: Canon Freeze — Witness Chain
description: sdlab canon freeze stamps the build's witness hash on canon entries; drift is computed mechanically on every subsequent build. Silent unfreeze becomes mechanically impossible — the build IS the auditor.
sidebar:
  order: 9
---

**Silent unfreeze becomes mechanically impossible — the build IS the auditor.**

That's the one-liner for the freeze tool. Every freeze stamps the `generated_from` of the canon-build that witnessed it. Every subsequent `sdlab canon build` computes the current projection hash for each frozen entry's `watch_fields` and diffs against the witness. If the hashes differ, the build reports drift; the operator cannot silently overwrite a hero moment without leaving a mechanical record.

Full scoping decisions (D1–D12) live in `memory/freeze-tooling-research-2026-04-24.md`. This page is the how-to.

## The model in three surfaces

```
canon/<entity>.md                     ← source of truth; the `freeze` block
canon-build/<sha>/manifest.json       ← build-witness; frozen_entries_hashes
canon-build/freeze-events.jsonl       ← append-only audit log
```

Each surface has one reader:

- **Entry frontmatter** — operators read for glance-state, canon-build reads for drift detection.
- **Build manifest** — written by canon-build, read by subsequent builds for drift comparison.
- **Event log** — written by freeze/unfreeze/override commands, read by `sdlab canon drift`.

## The freeze block

Canon schemas at v2.0.0+ carry a `freeze` object. The two legacy fields (`visual_locked_at`, `regen_policy`) were removed in the v2.0.0 schema bump.

```yaml
freeze:
  status: "auto" | "frozen" | "soft-advisory" | "on-canon-change"
  locked_at_build: "<generated_from of the witness build>"
  frozen_by: "mike"
  frozen_reason: "Labor III reference plate approved"
  watch_fields: ["visual.silhouette_cue", "signature_features"]
  overrides:                                    # append-only
    - at: "<build_hash>"
      by: "mike"
      reason: "Palette drift flagged by AI-Eyes eval"
      prior_status: "frozen"
      prior_build_hash: "<previous locked_at_build>"
```

Entries without a `freeze` block behave as `status: auto` — the permissive default. Pentiment's lesson: don't pre-lock. Freeze is additive ceremony, applied when canon stabilizes.

## The four statuses

| Status | Write-time gate | Build-time drift pass |
|---|---|---|
| `auto` | no block | not tracked |
| `frozen` | hard block; requires `sdlab canon unfreeze` | watch-hash stamped; drift surfaced |
| `soft-advisory` | blocks without `--i-know` + `--reason`; bypass logged as `bypass` event | watch-hash stamped; drift surfaced |
| `on-canon-change` | no block (policy lives at build time) | watch-hash stamped; drift surfaced |

`frozen` is for hero moments — the ~5–10 Labor-caliber scenes that cannot be silently regenerated. `soft-advisory` is for near-final iteration ("this is almost right; bounce me if I try to touch it without meaning to"). `on-canon-change` is for entries that should invalidate themselves only when a watched field changes — the build surfaces drift; no write-time block.

## The four commands

```
sdlab canon freeze <entity_id> --project <name> --reason "<text>"
  [--status frozen|soft-advisory] [--watch <fields>] [--build <sha>]

sdlab canon unfreeze <entity_id> --project <name> --reason "<text>"

sdlab canon freeze-status <entity_id> --project <name>

sdlab canon drift --project <name> [--since <build_hash>]
```

### `canon freeze`

Requires an existing canon-build output to witness against (the `locked_at_build` stamp). Rewrites the entry's frontmatter with the freeze block and appends a `freeze` event to `canon-build/freeze-events.jsonl`.

```bash
# First, always build once so there's a witness:
sdlab canon build --project greek-rpg

# Then freeze:
sdlab canon freeze heracles \
  --project greek-rpg \
  --reason "Labor III reference plate approved for LoRA training"
```

`--reason` is REQUIRED. The audit record depends on it.

### `canon unfreeze`

Lifts `status` back to `auto`. Preserves the `overrides[]` history append-only — freeze-then-unfreeze-then-re-freeze leaves a visible timeline. `--reason` is REQUIRED on unfreeze too; shipping studios (Sabotage's Completionist NPC swap, Hades II's ending rewrite, Pentiment's Father Thomas re-design) most often regretted NOT capturing why an unfreeze happened.

### `canon freeze-status`

Read-only glance at an entry's freeze state.

### `canon drift`

The audit command. Recomputes watch-hashes for every non-auto entry and compares against the latest build's stamps. Reports drifted entries and overrides since a reference build.

```
Drift report for greek-rpg
  latest build:    sha256:abc123...
  latest built_at: 2026-04-24T18:00:00Z

  auto entries:            12
  frozen entries (clean):  8
  frozen entries (drift):  1

Drifted frozen entries:
  character:heracles (frozen)
    witness hash:  7db1eb9577593... (from build abc123)
    current hash:  6fa02152e243a...
    watch fields:  visual.silhouette_cue, signature_features

Overrides since last build (1):
  unfreeze   perseus by mike — "Re-tune for Flux anchor retraining"
```

## Where the gate fires

### Hard enforcement (refuses to write on a frozen entry)

- **`sdlab curate`** — the point where a candidate gets promoted to `outputs/approved/`. Refuses if a canon entry's `visual.reference_plate_uri` already owns the target path and that entry is frozen.

### Advisory enforcement (early friendly-bounce, saves GPU cycles)

- **`sdlab generate:identity`** — when `--subject <id>` matches a frozen entry.
- **`sdlab generate:controlnet`** — when `--subject <id>` matches a frozen entry.
- **`sdlab generate:ipadapter`** — when `--subject <id>` matches a frozen entry.

All three advisory gates accept `--i-know` + `--reason` to bypass a `soft-advisory` entry. A frozen entry cannot be bypassed; run `sdlab canon unfreeze` first.

### No gate (by design)

- **`sdlab generate`** (prompt-pack-driven) — produces candidates that aren't canon-bound yet. The gate fires at `curate` when the candidate is promoted.
- **`sdlab reingest generated`** — writes records to `records/` with `gen_` prefix. Canon binding happens later at `curate` + `canon-bind`.
- **`sdlab painterly`** — writes to `outputs/painterly/`, never directly overwrites `outputs/approved/`.
- **`sdlab canon-bind`** — writes canon assertions to records, never touches reference plates.

## Watch fields

The `watch_fields` on an entry's freeze block (or the per-schema default in `canon-build/config.json`'s `freeze_watch_defaults`) declare which fields the witness chain hashes. Change ANY of them and the drift pass surfaces it on the next build.

Per-schema default pattern:

```json
{
  "freeze_watch_defaults": {
    "monster.schema.json":   ["signature_features", "anatomy_descriptor", "forbidden_inputs", "scale_indicator", "human_element"],
    "character.schema.json": ["visual", "signature_features", "forbidden_inputs"],
    "deity.schema.json":     ["visual", "signature_features"],
    "location.schema.json":  ["visual.era_markers", "visual.material_language", "visual.scale_logic", "signature_features"],
    "relic.schema.json":     ["visual", "materials", "relic_type", "signature_features"]
  }
}
```

Entry-level `watch_fields` overrides the schema default. A hero-moment entry that wants laser-focused drift detection can restrict the watch set to one field; an entry that wants broad coverage can widen it.

## The witness chain in practice

1. `sdlab canon build` emits a manifest with `generated_from: "sha256:A"`.
2. `sdlab canon freeze heracles --reason "..."` stamps `freeze.locked_at_build: "sha256:A"` onto the entry's frontmatter AND appends a `freeze` event to `freeze-events.jsonl`. The event includes `build_hash: "sha256:A"`.
3. Someone (you, or an LLM crew member) edits `heracles.md`, changing `visual.silhouette_cue`.
4. Next `sdlab canon build` run. Build computes the current watch-hash for heracles's `watch_fields`. Compares to `manifest.frozen_entries_hashes.heracles.watch_hash` from the prior build. They differ. Build prints:

   ```
   drift detected on 1 frozen entry since the previous build:
     character:heracles (frozen)
   Run `sdlab canon drift` for the full report.
   ```

5. Running `sdlab canon drift` surfaces the specific watch_fields that changed and the override history for the entry.

The operator can't *not* know: the build itself reports it. To legitimately change a frozen entry, you run `sdlab canon unfreeze heracles --reason "<why>"`, edit, then `sdlab canon freeze heracles --reason "<why re-frozen>"`. The overrides[] log records both steps; future-you can reconstruct the decision chain from the jsonl alone.

## Bridge to canon-build

- Every `sdlab canon build` runs the drift pass as its final step. Drift is reported but does NOT fail the build — the build succeeds, the operator decides.
- The canon-build cache key does NOT include freeze state. Freeze is write-side policy; caching is read-side optimization. A cache hit on a frozen entry re-uses its projection (correct) and doesn't skip the drift pass (the drift pass reads entry frontmatter directly).
- Per-entity content hashes (three-projection D4 cache keys) are independent from watch-hashes (freeze D1 drift keys). Change a non-watched field: cache invalidates but no drift. Change a watched field: cache invalidates AND drift.

## Out of scope (tracked for future slices)

- **Chapter-level cascade.** Freezing "Chapter 1" doesn't auto-freeze its entries today. Convention-only; enforceable cascade is a separate slice.
- **Role OS dispatch on soft-advisory.** The `soft-advisory` state could emit a Role OS notification; v1 is a CLI warning + `--i-know` requirement.
- **Build-time enforcement on `on-canon-change` drift.** Currently drift is informational. A future flag (`sdlab canon build --strict-drift`) could exit non-zero on detected drift, useful in CI.
- **`sdlab canon freeze-repair`** — rewrite frontmatter from the event log to resolve audit desync. Ships if `FREEZE_AUDIT_DESYNC` shows up in practice.
- **Cross-entity cascade rules.** Freezing a deity doesn't propagate to dependent monsters; this is an open design question.

## References

- Research deliverable + D1–D12 decisions: `memory/freeze-tooling-research-2026-04-24.md`
- Studio prior art: Sabotage's Sea of Stars "Content Lock" milestone; Supergiant's Hades v1.0 cutover; Pentiment's refused early asset lock; articy:draft's narrative version control.
- Tool prior art: Terraform `prevent_destroy`, Kubernetes finalizers, MLflow aliases, Perforce `+l` filetype locking, Git LFS locks, npm `deprecate`.
- Canon schemas: all five greek-rpg schemas at v2.0.0 carry the `freeze` block.
