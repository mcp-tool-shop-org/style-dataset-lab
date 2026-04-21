# workflows/

This directory is reserved. Workflow profiles are **not** stored here.

## Where workflow profiles live

Workflow profiles (ComfyUI JSON contracts that drive generation and batch production) live in two canonical places:

- **Per-project profiles** — `projects/<name>/workflows/profiles/*.json`. These are the active, in-use profiles for a given project. `sdlab workflow list --project <name>` reads from here.
- **Per-domain profiles** — `templates/domains/<domain>/workflows/profiles/*.json`. These ship with the domain templates and are copied into a new project by `sdlab init` when you pass `--domain`.

## Why this directory exists

It is kept as a placeholder to reserve the name `workflows/` for a future shared-profile pool (if a need for repo-wide, project-agnostic profiles emerges). Until then, treat this directory as intentionally empty — do not add profile JSON here, and do not expect `sdlab` commands to read from it.

If you are writing a new workflow profile, add it to `projects/<your-project>/workflows/profiles/` or, if you want it to ship with a domain template, `templates/domains/<domain>/workflows/profiles/`.
