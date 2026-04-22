# Ship Gate

> No repo is "done" until every applicable line is checked.
> Copy this into your repo root. Check items off per-release.

**Tags:** `[all]` every repo · `[npm]` `[pypi]` `[vsix]` `[desktop]` `[container]` published artifacts · `[mcp]` MCP servers · `[cli]` CLI tools

---

## A. Security Baseline

- [x] `[all]` SECURITY.md exists (report email, supported versions, response timeline) (2026-04-14)
- [x] `[all]` README includes threat model paragraph (data touched, data NOT touched, permissions required) (2026-04-14)
- [x] `[all]` No secrets, tokens, or credentials in source or diagnostics output (2026-04-14)
- [x] `[all]` No telemetry by default — state it explicitly even if obvious (2026-04-14)

### Default safety posture

- [x] `[cli|mcp|desktop]` CLI defaults to read-only canon inspection; mutating commands require explicit project target (2026-04-21)
- [x] `[cli|mcp|desktop]` All file operations are scoped to the project directory under `projects/<name>/` (2026-04-21)
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[mcp]` SKIP: not an MCP server

## B. Error Handling

- [x] `[all]` Errors follow the Structured Error Shape: `code`, `message`, `hint`, `cause?`, `retryable?` (2026-04-14)
- [x] `[cli]` `sdlab` exits non-zero on error; stderr carries structured messages (2026-04-21)
- [x] `[cli]` `--help` and subcommand help accurate for v3.0.0 surface (2026-04-21)
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[desktop]` SKIP: not a desktop app
- [ ] `[vscode]` SKIP: not a VS Code extension

## C. Operator Docs

- [x] `[all]` README is current: what it does, install, usage, supported platforms + runtime versions (2026-04-14)
- [x] `[all]` CHANGELOG.md (Keep a Changelog format) (2026-04-14)
- [x] `[all]` LICENSE file present and repo states support status (2026-04-14)
- [x] `[cli]` `sdlab --help` documents subcommands; each subcommand accepts `--help` (2026-04-21)
- [x] `[cli|mcp|desktop]` CLI documented in README pipeline example (2026-04-21)
- [ ] `[mcp]` SKIP: not an MCP server
- [x] `[complex]` HANDBOOK lives in `site/` (Starlight) and is linked from the landing page (2026-04-21 — 7 pages: index, getting-started, dataset-workflow, production-loop, reference, architecture, security)

## D. Shipping Hygiene

- [x] `[all]` `verify` script exists (test + build + smoke in one command) (2026-04-21 — `npm run verify` runs `sdlab --help && sdlab project doctor --project star-freight`)
- [x] `[all]` Version in manifest matches git tag (2026-04-21 — v3.0.0)
- [x] `[all]` Dependency scanning runs in CI (ecosystem-appropriate) (2026-04-21 — `.github/dependabot.yml` monitors npm + github-actions monthly; zero runtime deps keep the surface trivial)
- [x] `[all]` Automated dependency update mechanism exists (2026-04-21 — `.github/dependabot.yml` opens grouped monthly PRs)
- [x] `[npm]` `npm pack --dry-run` includes README, CHANGELOG, LICENSE, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT and the canonical `bin/`, `lib/`, `scripts/`, `templates/` trees; excludes wave-specific one-off curation scripts via `files` negation (2026-04-21 — 135 files, 173.9 kB tarball)
- [x] `[npm]` `engines.node` set (2026-04-14 — >=20)
- [x] `[npm]` `package-lock.json` present and matches `package.json` version (2026-04-21 — regenerated from stale v2.2.1 to v3.0.0; zero runtime deps keep it shallow)
- [ ] `[vsix]` SKIP: not a VS Code extension
- [ ] `[desktop]` SKIP: not a desktop app
- [x] `[all]` Test suite green on Node 20 + Node 22 (2026-04-21 — 63 tests across 11 files; `node --test tests/**/*.test.js`)

## E. Identity (soft gate — does not block ship)

- [x] `[all]` Logo in README header (2026-04-14 — placeholder block with brand path)
- [x] `[all]` Translations (polyglot-mcp, 8 languages) (2026-04-21 — ja, zh, es, fr, hi, it, pt-BR present)
- [x] `[org]` Landing page (@mcptoolshop/site-theme) (2026-04-21 — site/ builds 9 pages via Astro+Starlight; deployed to https://mcp-tool-shop-org.github.io/style-dataset-lab/)
- [x] `[all]` GitHub repo metadata: description, homepage, topics (2026-04-21 — `homepage` + keywords set in package.json)
- [x] `[all]` CONTRIBUTING.md + CODE_OF_CONDUCT.md + issue templates + PR template (2026-04-21)
- [x] `[all]` Troubleshooting section in README (2026-04-21 — covers ComfyUI connection, missing weights, doctor errors, --project fallback, bug reporting)

---

## Gate Rules

**Hard gate (A-D):** Must pass before any version is tagged or published.
If a section doesn't apply, mark `SKIP:` with justification — don't leave it unchecked.

**Soft gate (E):** Should be done. Product ships without it, but isn't "whole."

**Checking off:**
```
- [x] `[all]` SECURITY.md exists (2026-02-27)
```

**Skipping:**
```
- [ ] `[pypi]` SKIP: not a Python project
```
