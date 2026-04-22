# Contributing to style-dataset-lab

Thanks for your interest. This repo is the canon-aware dataset pipeline for visual AI projects — it prioritizes determinism, auditability, and a single source of truth per project. Contributions that reinforce those properties are welcome.

## Dev setup

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
npm install        # zero runtime deps; installs dev-only tooling
npm test           # runs the full node --test suite
npm run verify     # sanity smoke: help output + project doctor on star-freight
```

Requires Node.js 20+. ComfyUI is only needed for changes that touch the generation path (`lib/comfyui.js`, `scripts/generate.js`, `scripts/run-generate.js`). Doctrine, snapshot, split, export, and curation paths can all be exercised without a GPU — see the "Try it without ComfyUI" section of the README.

## Coding style

- **ESM only.** Every file uses `import` / `export`. No CommonJS.
- **No TypeScript.** Plain JavaScript. Types live in JSDoc when they help.
- **Built-in test runner.** Tests use `node --test` from Node 20+ — no Jest, Vitest, Mocha.
- **No runtime dependencies.** `package.json` intentionally has zero `dependencies`. Dev-only tooling goes in `devDependencies`; a new runtime dep requires a very good reason.
- **Structured errors.** Errors follow the Structured Error Shape — `code`, `message`, `hint`, optional `cause`, optional `retryable`. See `lib/errors.js` (or equivalent) for helpers.
- **Canon is truth.** Never hand-edit generated artifacts (snapshots, splits, exports, runs, critiques, selections). Edit the upstream config or record and re-run.

## Testing

Every change ships with tests. For bug fixes, add a regression test that would have failed before the fix.

```bash
# Run the full suite
npm test

# Run a single file
node --test tests/path/to/file.test.js
```

CI runs the same suite on Node 20 and Node 22 (see `.github/workflows/ci.yml`).

## PR checklist

Before opening a PR:

- [ ] `npm test` passes locally
- [ ] `npm run verify` passes locally
- [ ] New features have test coverage
- [ ] `CHANGELOG.md` has an entry under `## [Unreleased]`
- [ ] If you touched `package.json`, you regenerated `package-lock.json` (`npm install --package-lock-only`)
- [ ] If you added or changed a config file schema, `schemas/` is updated too
- [ ] Commit message explains *why*, not just *what*

## Shipcheck

Every release passes `npx @mcptoolshop/shipcheck audit` with all hard gates (A–D) green. Before we publish, we also re-read `SHIP_GATE.md` against the current repo state. If your change affects security posture, error handling, operator docs, or shipping hygiene, update `SHIP_GATE.md` in the same PR.

See the [shipcheck docs](https://github.com/mcp-tool-shop-org/shipcheck) for the full quality-gate definition.

## Reporting bugs

File an issue using the bug-report template at https://github.com/mcp-tool-shop-org/style-dataset-lab/issues/new/choose. Minimum repro info:

- `sdlab --version`
- `node --version`
- ComfyUI version (if relevant)
- Project name and relevant config file excerpt
- `sdlab project doctor --project <name>` output
- The failing command and full structured error output

## Code of conduct

Be decent. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — we use the Contributor Covenant.
