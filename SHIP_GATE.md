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

- [ ] `[cli|mcp|desktop]` SKIP: not a CLI/MCP/desktop app — scripts run locally by the user
- [ ] `[cli|mcp|desktop]` SKIP: not a CLI/MCP/desktop app — scripts operate within the project directory
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[mcp]` SKIP: not an MCP server

## B. Error Handling

- [x] `[all]` Errors follow the Structured Error Shape: `code`, `message`, `hint`, `cause?`, `retryable?` (2026-04-14)
- [ ] `[cli]` SKIP: not a CLI tool — scripts are run via npm run
- [ ] `[cli]` SKIP: not a CLI tool
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[desktop]` SKIP: not a desktop app
- [ ] `[vscode]` SKIP: not a VS Code extension

## C. Operator Docs

- [x] `[all]` README is current: what it does, install, usage, supported platforms + runtime versions (2026-04-14)
- [x] `[all]` CHANGELOG.md (Keep a Changelog format) (2026-04-14)
- [x] `[all]` LICENSE file present and repo states support status (2026-04-14)
- [ ] `[cli]` SKIP: not a CLI tool — no --help flags
- [ ] `[cli|mcp|desktop]` SKIP: not a CLI/MCP/desktop app
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[complex]` SKIP: not complex enough to warrant a HANDBOOK.md

## D. Shipping Hygiene

- [x] `[all]` `verify` script exists (test + build + smoke in one command) (2026-04-14 — npm run inspect serves as verification)
- [x] `[all]` Version in manifest matches git tag (2026-04-14 — v1.0.0)
- [ ] `[all]` Dependency scanning runs in CI (ecosystem-appropriate) — pending CI setup
- [ ] `[all]` Automated dependency update mechanism exists — pending CI setup
- [x] `[npm]` `npm pack --dry-run` includes: dist/, README.md, CHANGELOG.md, LICENSE (2026-04-14 — files field set)
- [x] `[npm]` `engines.node` set (2026-04-14 — >=20)
- [ ] `[npm]` SKIP: no lockfile needed — zero runtime dependencies
- [ ] `[vsix]` SKIP: not a VS Code extension
- [ ] `[desktop]` SKIP: not a desktop app

## E. Identity (soft gate — does not block ship)

- [x] `[all]` Logo in README header (2026-04-14 — placeholder block with brand path)
- [ ] `[all]` Translations (polyglot-mcp, 8 languages)
- [ ] `[org]` Landing page (@mcptoolshop/site-theme)
- [ ] `[all]` GitHub repo metadata: description, homepage, topics

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
