# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

## [3.4.0] - 2026-08-04

**Dogfood swarm.** A full health pass (bugs/security, then proactive hardening, then user-facing copy) followed by three new commands. Tests **400 → 791**. Every fix carries a test proven to fail against the unfixed code.

The through-line: this package had never been exercised outside its own repo checkout, where the workspace root and the package root happen to be the same directory. Most of what follows falls out of that.

### Added

- **`sdlab ingest <dir>`** — bring externally-generated images into a project as bare, uncurated candidate records. There was previously no path in: `reingest generated` requires a trained LoRA's manifest and `reingest selected` requires a selection only the production loop can mint. Records land with `judgment: null`, `canon: null` and `provenance.source: "external"` — it never invents a judgment, a score, or a caption.
- **`sdlab sheet [<dir>]`** — an HTML contact sheet over any directory of candidates, for visual triage before full-resolution review. Shows record id, curation status and prompt per tile; degrades to filename for images with no record yet. Images are referenced by relative path, so a 99-image sheet is ~110 KB and stays openable.
- **`sdlab measure <target>`** — deterministic palette and texture measurement attached to records as numbers. Ported from the validated salt-road audit instruments. **Measurement, not verdict**: it never sets `judgment` or `overall_fit`. Requires Python 3.9+ with Pillow/numpy/scipy; without them it fails with a clear structured error rather than degrading silently.
- **Judgment-provenance reporting** in `sdlab eligibility audit` — distinguishes judgments a person made from judgments a bulk script minted, read-only, without modifying any record.
- `--resume` on `generate:identity`, `generate:controlnet` and `generate:ipadapter`, including the seed-advances-on-skip discipline that makes a resumed run reproduce what an uninterrupted one would have produced.

### Fixed

- **`sdlab init` wrote user projects into `node_modules/`.** `REPO_ROOT` resolved from the module's own location, so for anyone installing from npm rather than cloning, every project — canon, records, judgments, snapshots, exports — landed inside the installed package, where the next `npm ci` silently destroyed it. Replaced with a workspace resolver (`SDLAB_ROOT` → walk up from cwd for `projects/` → module root if it is the checkout → cwd) that refuses any root inside `node_modules`. A separate package root now serves `templates/` and `runtime/`, which ship in the tarball and are not workspace content.
- **`--project` accepted a traversing value.** `--project ../../some-sibling-repo` resolved outside the sandbox and was accepted; ~26 scripts then wrote beneath it. `getProjectRoot()` now rejects separators and `..`, and every script routes through it.
- **`sdlab project doctor` printed a failure and exited 0** on a missing project — and `npm run verify` and the CI smoke step both gate on that exit code.
- **Subject leakage with an audit that certified it clean.** The split's subject-family fallback split one subject across two families (`_v1` suffix vs `v2` infix, case-sensitively), and the leakage audit re-read the same family map the assignment used, so it could not detect that class at all — while the dataset card printed "Subject leakage: None (verified)". Added an independent stem cross-check; the card now withholds "verified" unless both checks pass and the guessed-family share is immaterial. A split predating the cross-check now says so instead of claiming verification it never received.
- **`training-package build` produced an empty package and exited 0 on Windows** without Developer Mode: no symlink guard, and a bare `catch { continue; }` in all three adapters dropped image, caption and metadata row together.
- **`eval-run score` returned `overall_verdict: "pass"` for a missing eval pack** — `[].every()` is vacuously true, so a moved or deleted pack scored zero tasks as a pass.
- **Pinning parity between the JS and Python runners.** Float formatting diverged (`0.00005` vs `5e-05`), an explicit `null` LoRA weight defaulted differently, and the Python bridge hardcoded `sampler`/`scheduler`/`shift` **inside its own pinning receipt** — asserting values it never read.
- The freeze gate failed open on a malformed `status` (a capital `F` silently disabled protection). Captions fell back into curation metadata. `checksums.txt` was written and never verified. No `fetch` in the ComfyUI client carried a timeout. `--dry-run` created directories. `run generate` wrote its manifest only at the end, so an interrupted long run left no record at all and did not appear in `run list`.
- `migrate-records.js` was excluded from the npm tarball while still dispatched and documented — every npm user running `sdlab migrate` got `Cannot find module`. `runtime/` did not ship at all. 30 KB of Python bytecode did.
- Three scripts that fabricated curation rationales from a filename-prefix regex were deleted.

### Changed

- Error hints across `doctor`'s ~38 failure sites now carry a concrete next action, and `INPUT_UNKNOWN_PROJECT` names both causes (wrong directory vs missing project) rather than assuming the second.
- `sdlab critique` no longer presents its automatic `Next:` suggestion as a considered judgment when nothing has been reviewed — every candidate is stamped `usable` by default and nothing changes it, so the ranking was drift-count tiebreaking, not assessment.
- `sdlab init` scaffolds a per-project `.gitignore`; generated contact sheets and re-ingest staging images are ignored.

## [3.3.0] - 2026-07-06

**Provenance hardening.** This release closes the three weakest workflow-standards scores (PIN_PER_STEP, EXTERNAL_VERIFIER, UNCERTAINTY_GATED_HUMANS) so shipped, production LoRA work is byte-for-byte reproducible and the verifier/human-gate muscles are in place. No breaking changes — every new field is additive and optional; legacy manifests and records load unchanged.

### Added

- **PIN_PER_STEP — run-manifest pinning contract** (`lib/run-manifest.js`, the single source of truth): every generation writer now records a `pinning` block so a wave is byte-for-byte replayable —
  - **`comfy_workflow_sha`** — SHA-256 of the exact ComfyUI graph submitted (per-item seed + prompt normalized out, so one hash pins the whole wave's pipeline skeleton). The JS runners (`generate.js`, `comfyui-runner.js`) and the Python bridge (`scripts/qwen_generate.py`) produce a **byte-identical** hash for the same graph.
  - **Model + LoRA content identity** — `unet`/`clip`/`vae`/`checkpoint` and each LoRA upgraded from a bare filename to `{name, size_bytes, sha256}`. `sha256` is opt-in via `--hash-models` (best-effort, resolved under the ComfyUI models dir, cached by `(name, size, mtime)` so multi-GB checkpoints aren't re-hashed every wave); `size_bytes` is always recorded when the file resolves. Unresolvable files record `sha256: null` with a `hash_note` — a hash is never fabricated.
  - **`seed_policy`** — records the intent behind seed selection (`base+increment`, `explicit-per-item`, `fixed`, `random`), not just the values.
  - New `--hash-models` flag on `sdlab generate` and `sdlab run generate` (and `scripts/qwen_generate.py`).
- **EXTERNAL_VERIFIER — judge/generator provenance** (`lib/verifier.js`): curate and critique records now carry **`judged_by_model`** (`human` / `rule-based:sdlab-critique-v1`) and **`generator_model`** (derived as `<base>:<model>`, e.g. `qwen-image:qwen_image_fp8_e4m3fn`), and a **WARN fires when the two are the same model** — the self-verification failure mode. (Today's rule-based critique engine is a different artifact class from the generator, so the warning does not fire; the fields + warning install the muscle for when an LLM critique mode enters the loop.)
- **UNCERTAINTY_GATED_HUMANS —**
  - **`sdlab critique --triage`** surfaces only the candidates that need a human — `off-model` OR ≥ `--drift-threshold` (default 3) drift issues — so attention gates on uncertainty rather than on every item. The full `critique.json` is unchanged; triage is a view over it.
  - **Contrastive freeze-gate refusals** — the freeze bypass prompt now leads with the default action and the system's reasoning (`Default: REFUSE — "<id>" is <status> frozen by <by> on <date>, reason: "<why>". Override with --i-know --reason ONLY if your change does not touch the watched fields [...]`), and `curate <id> borderline` prints a contrastive HOLD advisory.

### Changed

- **Manifest `SCHEMA_VERSION` 2.2.0 → 2.3.0** — the ComfyUI run manifest now stamps `schema_version` and carries the `pinning` block. Readers still `checkManifestVersion()`-warn (never throw) on mismatch, so pre-3.3.0 manifests load fine.

### Tests & coverage

- **400 tests, 0 failing** (368 → 400: +32 for pinning, verifier fields, triage, and contrastive freeze wording). Coverage: statements **63.53%** / branches **75.77%** / functions **69.04%**.



The **canon authoring** release. A new `sdlab canon *` namespace turns a project's canon entity store into the projections training actually consumes, and wraps a witness-backed freeze spine around entries that must not drift — plus first-class Flux and Qwen-Image training paths.

### Added

- **Canon authoring namespace (`sdlab canon *`)** — the headline of this release:
  - **`sdlab canon build`** (#16) — builds three canonical projections from a project's canon entity store: `dataset.jsonl` (for training adapters), `prompts/<id>.j2` (Jinja2 templates for ComfyUI invocation), and `context/<id>.md` (narrative blocks for Role OS dispatch). Output keyed by `<canon_sha>` with a content-addressable cache under `canon-build/.cache/`. Flags: `--full`, `--no-cache`, `--dry-run`, `--only <ids>`, `--json`, `--quiet`.
  - **`sdlab canon freeze` / `unfreeze` / `freeze-status`** (#17) — witness-chain freeze tooling. `freeze` stamps a freeze block on an entry (witnessed against a canon-build output via `locked_at_build`), writing both the entry frontmatter and an append-only `canon-build/freeze-events.jsonl`. Statuses: `frozen` (regen refused; unfreeze ceremony required) and `soft-advisory` (refused by default, bypassable with `--i-know`). `--reason` is required on freeze/unfreeze — the audit record depends on it. `freeze-status` is a read-only glance at an entry's state.
  - **`sdlab canon drift`** (#19) — for every frozen / on-canon-change entry, recomputes the watch-field hash and compares against the hash stamped in the latest canon-build manifest; reports drifted entries and overrides since a given build.
- **Canon schema system** (#18) — Star Freight Grounded canon shipped as worked example data (28 entities across 5 entry schemas), demonstrating the entity format `canon build` consumes.
- **`flux-natural-language` caption strategy** (#11) — natural-language captions for Flux.1-dev LoRA training, alongside the existing SDXL trigger-word strategy.
- **Two-LoRA stack training contract** (#15) — threads the `is_style_lora` boolean through profiles and adapters (world/style LoRAs → `true`, per-character subject LoRAs → `false`), driving trainer regularization for the two-LoRA stacking pattern.
- **Flux training targets** — Flux-target training profiles (#12) and Flux-target ComfyUI workflow profiles (#13) for Star Freight, plus the **`ai-toolkit` adapter** for Flux LoRA training (#14): emits `dataset/<partition>/<record_id>.{png,txt}` + `metadata/<partition>.jsonl` + an `ai-toolkit-config.yaml` that Ostris [ai-toolkit](https://github.com/ostris/ai-toolkit) consumes directly. Flux-only — rejects non-Flux profiles with `ADAPTER_TARGET_FAMILY_MISMATCH`; emits `is_style` from the profile's `is_style_lora`. Registered in `ADAPTER_REGISTRY` beside `generic-image-caption` and `diffusers-lora`.
- **Qwen-Image native generation** (#24) — native non-anime Qwen-Image generation path with a `gpu_model` override.
- **Qwen DiT LoRA chain** (#25) — DiT LoRA chaining in both Qwen runners, with tallow-fen style-LoRA dataset wiring.

### Fixed

- **Caption prompt bleed** (#9) — routed captions through the shared research-backed builder so prompt fragments no longer bleed across records.
- **Freeze witness-chain drift** (#19) — the drift CLI reads `.watch_hash` from the rich freeze stamp, and `freeze-status` surfaces resolved `watch_fields`.

### Changed

- Training adapter registry now exposes three adapters — `generic-image-caption`, `diffusers-lora`, `ai-toolkit`; the handbook reference and README document the `ai-toolkit` Flux-only precondition.
- `projects/`: rustline and tallow-fen production style datasets added as worked examples (repo-clone content; not shipped in the npm package).

### Dependencies

- **`yaml@^2.8.3`** added as a runtime dependency for the ai-toolkit YAML config (#14), kept current in the range (#23). CI: `actions/checkout` 6→7 (#30), `codecov/codecov-action` 5→7 (#31).

### Tests & coverage

- **368 tests, 0 failing.** Coverage: statements **60.36%** / branches **75.5%** / functions **68.35%**.

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
