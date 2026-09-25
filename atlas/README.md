# style-dataset-lab: how it works

Mapped at 2026-09-25 from commit b0426ac.

## What this is

13 parts, mostly JavaScript (233 files), Python (30) and TypeScript (2). Work enters through 4 doors; CI and Publish each reach 4 parts, and CI is followed because a pull request goes through it. It publishes to npm. People run sdlab.

## What changed since the last map

This is the first map.

## What comes in

1. **CI.** On a pull request touching 13 paths; on a push touching 13 paths; or by hand. Runs bin/sdlab.js, tests/canon-star-freight/, tests/cli-scripts/ and 70 more.
2. **Publish.** When a release is published; or by hand. Runs bin/sdlab.js, tests/canon-star-freight/, tests/cli-scripts/ and 70 more.
3. **Deploy site to GitHub Pages.** On a push to main touching 2 paths; or by hand. Runs site/astro.config.mjs and site/src/.
4. **sdlab** (a command people run). Runs bin/sdlab.js.

## What happens through CI

1. The workflow runs bin/sdlab.js in bin and 96 files in tests.
   1. Inside bin/sdlab.js, main does, in order: enable debug (lib) and set log level.
   2. Or, when `command === head`, main does find closest (lib) and input error instead.
   3. Or, when `command === 'critique'`, main does run (scripts) instead.
   4. Or, when `command === 'refine'`, main does run (scripts) instead.
   5. Main returns early 2 more ways.
   6. **Run** (scripts) runs, in order:
      1. parse args (lib)
      2. get project name
      3. get project root
      4. critique run
      5. render critique markdown
      6. save critique
      7. render critique text
      8. info
   7. **Run** (scripts) runs, in order: parse args (lib), get project name, get project root, load critique, get runs dir, refine briefs (3 steps) and info.
   8. **Run** (scripts) runs, in order: parse args (lib), get project name, get project root, selections (3 steps) and info.
2. That reaches lib (73 files) and scripts (13 files).
3. It writes to projects/.

## Who reads the results

- **projects/** is read by lib/paths.js, and by 3 tests.

## The other doors

**Publish** runs bin/sdlab.js, tests/canon-star-freight/, tests/cli-scripts/ and 70 more, reaches lib and scripts, writes to projects/, and publishes to npm.

**Deploy site to GitHub Pages** runs site/astro.config.mjs and site/src/, and deploys the site.

**sdlab** (a command people run) runs bin/sdlab.js and reaches lib and scripts.

## What breaks what

- **lib** is imported by 2 parts (bin, scripts), and by 1 more only from tests; it sits on the path of 3 doors.
- **scripts** is imported by 1 part (bin), and by 1 more only from tests; it sits on the path of 3 doors.
- **bin** is imported by no other part and sits on the path of 3 doors.
- **tests** is imported by no other part and sits on the path of 2 doors.
- **projects/salt-road/records/** is written by projects and read by projects; a hand edit reaches every reader.
- **projects/salt-road/inputs/prompts/wave-v2.json** is written by projects and read by projects; a hand edit reaches every reader.

## What tends to change together

No two source files changed together often enough to name.

Window: 180 days; a pair counts from 3 shared commits, since 1 source file reaches 10 revisions; the floor rises to 10 when 25 do.

## What no test touches

Every code part is touched by at least one test.

bin is touched by tests only through a spawn: a test runs its files as a child process.

## Written but never read

- **projects/ai-eye-test/outputs/synthetic/phase2/** is written by projects/ai-eye-test/compositor/phase2_build.py and read by nothing else in this repository.
- **projects/ai-eye-test/outputs/synthetic/phase2_noshadow/** is written by projects/ai-eye-test/compositor/phase2_noshadow_build.py and read by nothing else in this repository.
- **projects/ai-eye-test/outputs/synthetic/phase2b/** is written by projects/ai-eye-test/compositor/phase2b_build.py and read by nothing else in this repository.
- **projects/salt-road/inputs/control-guides/** is written by projects/salt-road/inputs/control-guides/blockouts.py and read by nothing else in this repository.
- **projects/salt-road/inputs/prompts/curate-plan.json** is written by projects/salt-road/inputs/prompts/ingest-styleset-records.mjs and read by nothing else in this repository.
- **projects/salt-road/outputs/style-set-v2-review.html** is written by projects/salt-road/inputs/prompts/build-review-page.mjs and read by nothing else in this repository.

## Helpers that look duplicated

No two parts export a helper that looks alike.

## Generated, never hand-edited

- **projects/** is written by scripts/init.js.
- **projects/ai-eye-test/outputs/synthetic/phase2/** is written by projects/ai-eye-test/compositor/phase2_build.py.
- **projects/ai-eye-test/outputs/synthetic/phase2_noshadow/** is written by projects/ai-eye-test/compositor/phase2_noshadow_build.py.
- **projects/ai-eye-test/outputs/synthetic/phase2b/** is written by projects/ai-eye-test/compositor/phase2b_build.py.
- **projects/salt-road/inbox/generated/set-v2-2026-07-30/** is written by projects/salt-road/inputs/prompts/wave-runner.py.
- **projects/salt-road/inputs/control-guides/** is written by projects/salt-road/inputs/control-guides/blockouts.py.
- **projects/salt-road/inputs/prompts/curate-plan.json** is written by projects/salt-road/inputs/prompts/ingest-styleset-records.mjs.
- **projects/salt-road/inputs/prompts/wave-v2.json** is written by projects/salt-road/inputs/prompts/prompt-foundry.mjs.
- **projects/salt-road/outputs/style-set-v2-review.html** is written by projects/salt-road/inputs/prompts/build-review-page.mjs.
- **projects/salt-road/records/** is written by projects/salt-road/inputs/prompts/ingest-styleset-records.mjs, projects/salt-road/inputs/prompts/ingest-wave.mjs and projects/salt-road/inputs/prompts/populate-canon-subjects.mjs.

## Hand-authored

People write .github/, docs/, the repository root, runtime/, schemas/, site/, templates/ and workflows/; 45 writes with paths built at run time may land here.

## Where to start

.github/workflows/ci.yml → bin/sdlab.js → lib/args.js

Read those in order to follow one pull request end to end.

## What this map cannot see

- 18 import sites could not be resolved.
- 45 writes and 76 reads use paths built at run time and are not named here.
- 2 writes go to places this repository does not track, so they are not listed as generated.
- 108 writes and 216 reads go to a path their caller passes, not to this repository.
- 6 reads go to the directory the command is run in, not to this repository.
- 1 write and 2 reads go to a temporary directory, not to this repository.
- 1 read goes to the directory the command is run in (projects/) or a path its caller passes, not to this repository.
- 11 commands are built at run time and not followed, 8 of them in tests.
- Statistics confidence is low: fewer than 20 source files reach 10 revisions in the window.

Regenerate with `npx --yes @dogfood-lab/atlas map`.
