# Scorecard

Real gate results from `npx @mcptoolshop/shipcheck audit`, run against this repo
state for the **v3.2.0** release. Not estimates — the verdict below is the
verbatim audit output.

**Repo:** style-dataset-lab
**Date:** 2026-07-06
**Version:** 3.2.0
**Type tags:** [npm] [cli]

## Audit verdict

```
Checked:   30
Unchecked: 0
Skipped:   10   (non-applicable: MCP / desktop / VS Code items)
Pass rate: 100%

All hard gates pass. Ship it.
```

## Hard gates (A–D) — block release

Every applicable item passes; nothing unchecked.

| Gate | Result | Applicable items (all pass) |
|------|--------|------------------------------|
| **A. Security** | ✅ PASS | `SECURITY.md`, README threat model, no secrets/credentials, no telemetry, read-only default, all file ops scoped to `projects/<name>/` |
| **B. Error Handling** | ✅ PASS | Structured error shape (`code`/`message`/`hint`/`cause?`/`retryable?`), non-zero exits with structured stderr, accurate `--help` across the CLI surface |
| **C. Operator Docs** | ✅ PASS | Current README, Keep-a-Changelog `CHANGELOG.md`, `LICENSE`, per-subcommand `--help`, Starlight handbook linked from the landing page |
| **D. Shipping Hygiene** | ✅ PASS | `npm run verify`, manifest version == git tag, CI dependency scanning (dependabot), clean `npm pack`, `engines.node >=20`, lockfile matches `package.json`, tests green on Node 20 + 22 |

## Soft gate (E) — identity

| Gate | Result | Applicable items (all pass) |
|------|--------|------------------------------|
| **E. Identity** | ✅ PASS | README logo, 7 README translations, landing page (Astro + Starlight), GitHub metadata, `CONTRIBUTING`/`CODE_OF_CONDUCT`/issue + PR templates, README troubleshooting |

## Supporting facts (this release)

- Test suite: **368 tests, 0 failing** (`npm test`, Node 22).
- Coverage: statements **60.36%** / branches **75.5%** / functions **68.35%** (`npm run coverage`).
- `npm audit`: **0 vulnerabilities** (dev + production).

Item-level checklist with historical check dates lives in
[`SHIP_GATE.md`](./SHIP_GATE.md); the empty template shape is
[`SCORECARD.template.md`](./SCORECARD.template.md).
