# docs/internal/

These files are **internal session handoffs and working notes**, not product documentation.

Public documentation lives in:
- Top-level `README.md` — install, pipeline, trust properties
- `site/src/content/docs/handbook/` — Starlight handbook (getting-started, reference)
- `SHIP_GATE.md` — current release-readiness gate
- `CHANGELOG.md` — release history

## What's in here

- `HANDOFF.md` — session handoffs between Claude instances during active development. May reference wave numbers, painterly tuning notes, or work-in-progress design decisions.
- `WAVE_PLAN.md` — historical wave plan for the Star Freight production run. Frozen after the wave shipped.
- `WAVE27A_SESSION_STATE.md` — single-session state snapshot. Frozen after the session ended.

## Reading these files

Treat every file here as potentially stale. The canonical state of the repo is whatever is in `SHIP_GATE.md`, `CHANGELOG.md`, and the current code on `main`. If a document in this folder contradicts those, the canonical sources win.

## Why they're tracked in git

Having the handoff history adjacent to the code makes it easier to reconstruct *why* a design decision was made, not just *what* the code does. This directory is not a blog, not a wiki, and not a roadmap — it's an engineering audit trail.

When a wave ships and its session state is no longer useful for ongoing work, it migrates to `F:/DEEP_MEMORY/` (the user's long-term archive) and can be deleted from here.
