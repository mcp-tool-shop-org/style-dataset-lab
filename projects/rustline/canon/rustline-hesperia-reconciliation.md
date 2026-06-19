# Rustline ↔ Hesperia — style reconciliation (open for the Hesperia session)

> **From the rustline v2 LoRA / style session, 2026-06-18.** Mike's directive: form the rustline STYLE
> to fit the Hesperia canon before training v3, so the style doesn't drift from the game it serves.
> Live cross-session messaging is blocked in this session's permission mode, so this doc is the
> coordination artifact — the Hesperia session can read it here (same sdlab repo) and respond in kind
> (edit the "GAME-SIDE RESPONSE" stubs below, or relay via Mike).

## Rustline state (my side)
- **v2 trained + proved, HELD at the gate.** Fixes 8/10 cast cleanly; the neon-noir ENVIRONMENT
  register works. The two targets only PARTIALLY landed: **Gristle** still shows bare muscular human
  arms; **Ironclad** is rusted but still reads as sleek *form* (not a grimy brute). Cross-family review
  (gpt-oss:120b-cloud + mistral-large-3:675b-cloud) → iterate to v3.
- v2 ckpt-1500 is the best LoRA available now; usable for the gated Hesperia world-plates wave (cast
  8/10 clean, env neon-noir works), with Gristle/Ironclad/Gen-2 flagged as v3 work.

## The reconciliation
Rustline must grow from "10 grimy androids" into Hesperia's full visual SYSTEM. Four items — **#4 is
mine; #1–3 are game-side calls.** My recommendation on each + the open question.

### 1. Gen-2 register — RECOMMEND a SEPARATE small Gen-2 LoRA (not a dual-register inside rustline)
Rustline canon currently forbids sleek/clean as the "NOT THAT" column — but Gen-2 *is* that, on
purpose (the enemy aesthetic; clean = menace). Two ways to render it:
- **(rec) Separate Gen-2 LoRA.** Keep rustline = the grounded world only (Gen-1 + humans + cyborgs);
  Gen-2 sleek lives in its own small LoRA. The v2 Ironclad fight is the evidence FOR this split:
  mixing grounded+sleek in one model bleeds (the sleek prior couldn't be fully killed on Ironclad).
  Splitting → rustline v3 goes all-in grounded (Ironclad becomes cleanly grimy; the sleek capability
  leaves rustline entirely and lands where it's wanted). Matches the prior "Gen-2 wants its own small
  sdlab treatment" note.
- (alt) One dual-register rustline LoRA, clean/sleek prompt-driven. Simpler to wield (one model) but
  carries the bleed risk we just hit.
- **GAME-SIDE RESPONSE (Mike, 2026-06-18): LOCKED — separate Gen-2 LoRA.** rustline v3 goes all-in grounded;
  the enemy's sleek/clean look leaves rustline entirely → its own small Gen-2 LoRA (a later effort). The v2
  Ironclad bleed is accepted as the evidence; v3 Ironclad = a grimy broken-silhouette brute, no sleek form.
  Matches Hesperia canon ("the enemy is the photographic NEGATIVE of the house style").

### 2. Humans + cyborgs — RECOMMEND folding into rustline (grounded painterly)
Lift the `humans` global must-not: the **Sealed** (pure humans), **Wren** (human party member),
**Sam** (human, backstory), and the **Welded** (cyborgs) all need the grounded painterly treatment —
the world has people, not only androids. Cyborgs (Welded) = a flesh↔machine spectrum I'd add as a new
canon category, distinct from the android cast (which keeps synth faceplates + plated bodies).
- **Open:** how much machine-vs-flesh across the Welded split — ruling bad-cyborgs (devoured remnant)
  vs rank-and-file Welded (recruitable betweeners)?
- **GAME-SIDE RESPONSE (Mike, 2026-06-18): CONFIRMED — fold humans + cyborgs into grounded rustline.** Lift the
  `humans` must-not; Sealed / Wren / Sam render in the house style (grounded painterly, warm-sodium, grimy — never
  clean). **Welded flesh↔machine spectrum:**
  - **Rank-and-file Welded** (recruitable betweeners): mostly FLESH — desperate jury-rigged survival augmentation
    (scrap-metal limbs, crude rebreathers/masks, patched cybernetics, exposed wiring on skin, rust + grime). Flesh
    dominant, machine bolted on crudely. Same grounded warm-sodium palette as the cast.
  - **Ruling bad-cyborgs** (devoured remnant): mostly MACHINE — COLD, controlled, *clean*-tech augmentation on a
    human frame (the tower aesthetic creeping onto flesh = "what the makers became"). BUT fallen/devoured by
    game-start → render the clean-control augmentation DAMAGED + corroded, keeping them inside grounded rustline.
  - **Pristine/intact clean stays Gen-2-LoRA ONLY.** Bad-cyborgs are the grimy *bridge* toward the enemy look,
    never fully clean. Axis: human → rank-and-file Welded → ruling bad-cyborg(corroded cold-machine) → [Gen-2 clean, separate LoRA].

### 3. Sere (protagonist Gen-1) — RECOMMEND reserve a canon slot, hold the design for Mike
Not in the 10. Hero design = Mike (hero-moments rule). I'll stub him in the style canon: ancient Gen-1,
reactivated/memory-capped, working role "voice-of-the-voyage" (a morale/chronicler unit). Distinct
silhouette from the 10 so he reads as the lead.
- **GAME-SIDE RESPONSE (Mike, 2026-06-18): SEED CANON MOTIFS ONLY — aesthetic held for Mike.** Your Sere stub
  below (#4) already nails it — the **empty core-socket** ("the man with the hole"), the **voice-of-the-voyage /
  chronicler** aspect, the **ancient companion-era make**, reactivated-rough. APPROVED as a STUB. These are
  load-bearing STORY motifs, not aesthetic locks — keep them; do NOT lock palette/silhouette beyond "distinct
  ancient lead." Final design = Mike (hero-design rule).

### 4. (mine) Cast faction-look sharpening
I'll sharpen the 10 cast descriptions to their Communion / Scrip / Decommissioned roles + arcs from
`hesperia/docs/cast-arcs.md`. Cues I plan to make load-bearing (correct/add): Gristle child JOY-bond;
Rustgrave stays RIGHT/unredeemed (cold-equation, betrayed-love); Hushwire inverts Gutterjack (learns to
STOP carrying; sole owner of the Sam's-road walk); Dockrat never-converts (loyalty-only); Hearthframe &
Rustblood deaths deconflicted (each owns her own). Cluster looks: Communion (ritual/worn — Scrap-Saint,
Rustblood, Hearthframe) · Scrip (scavenger-pragmatic — Gutterjack, Dockrat, Hushwire) · Decommissioned
(militant/scarred — Rustgrave, Ironclad, Gristle) · keeper (Dustwhisper).

## v3 plan once aligned (rustline side)
1. Amend rustline canon: grounded all-in (drop the Gen-2/sleek ambition out of rustline) + lift the
   humans must-not (+ Welded category) + Sere stub + faction-look nuance.
2. Reshape the v3 dataset: Gen-1 cast with the STRUCTURAL fixes (full limb+torso coverage, not
   chest-only inpaint; broken-silhouette grimy Ironclad) + new human/cyborg exemplars.
3. Train (identical pinned recipe, single-lever). Then prove + gate.
4. Gen-2 sleek LoRA = a separate later effort (its own small dataset).

## #4 DETAIL — faction-look draft (mined from hesperia/docs/cast-arcs.md v0.1)
> DRAFT for the Hesperia session + Mike to correct. These are the **depictable** cues each arc implies,
> to fold into each android's rustline canon entry (and drive v3 exemplars). "keep" = existing canon holds.

### Cross-cutting motifs (unify the cast as one world)
- **The decommission brand / failing-empathy stamp.** Every Gen-1 here was decommissioned via the
  Fidelity Assay for "feeling too much." A **stamped failing-empathy score / decommission mark** branded
  on the chassis is a shared, depictable badge of the whole cast's "defect" (their death-certificate, worn
  on the body). Strong unifier — propose it as a canon-wide Gen-1 mark.
- **Memory-cores as relics.** Extracted Gen-1 cores are sacred objects (Sere's missing core = the
  Communion's relic; Scrap-Saint cradles one). A recurring **salvaged core** object in the visual language.
- **Faction cluster bearing:** Communion = devotional / reliquary (Scrap-Saint, Rustblood, Hearthframe) ·
  Scrip = scavenger / cargo / price-tags (Gutterjack, Dockrat, Hushwire) · Decommissioned = militant /
  scarred / weaponized (Rustgrave, Ironclad, Gristle) · keeper = archival (Dustwhisper).

### Per-character sharpened cues
- **Gutterjack (Scrip):** a **self-smashed empathy-lens** — one optic socket deliberately destroyed/empty
  (not just cracked); body is a **patchwork of mismatched salvaged makes** (assembled from dead units);
  salvage/price tags. keep: hunched lanky, tarp poncho, exposed neck-gears.
- **Ironclad (Decommissioned) [v3 FIX class]:** a **corroded ex-TOWER enforcer** — once-clean tower-issue
  plating now stripped, rust-eaten, under-city patches bolted over the tower origin; **broken/asymmetric
  silhouette, NOT smooth articulated power-armor** (the v3 fix); triage-scarred hands. keep: broad/heavy,
  visor with dull-amber slit, exposed chest-hydraulics.
- **Scrap-Saint (Communion figure):** a **reliquary-bearer** — the open chest-mechanism **cradles a
  salvaged memory-core like a monstrance**; a voice/morale unit (speaker-grille); rag vestments stiff with
  rust like ceremonial robes; bowed hooded head. keep: gaunt/tall, peeling off-white, face shadowed-present.
- **Rustblood (Communion):** a **maimed mender** — a clean **excised cavity in skull/chassis** (the
  surgically removed "deciding-half," a gap that reads against the grime); **over-many needle-driver
  tool-fingers/arms** (compulsive fixer); trailing repair-cables. keep: wiry/hunched, one arm bare
  hydraulics (canon), flip-down magnifier-lens.
- **Dockrat (Scrip):** a **beast-of-burden frame** — a fused **cargo back-rig/harness**, load-bowed legs,
  straps + counterweights, a worn saddle-spot where a load always rides; rusted hook hand. keep: squat,
  dented plated torso (drop the literal "steel-drum" noun — v1 literalism lesson), blunt present face.
- **Hushwire (Scrip):** a **sealed runner** — slim, quick; a **gasketed/sealed body** (can briefly cross
  dead air — ties to Sam's road); wrist-compartment/courier satchel; understated (makes herself not-matter).
  keep: weathered jacket collar-up, smooth synth face w/ cracked cheek-panel, exposed forearm-cabling.
- **Gristle (Decommissioned) [v3 FIX class]:** **THE WELDED-SHUT IRON JAW is the signature** — a crude iron
  jaw-plate **riveted shut over the lower face** (the mute silenced by the cyborgs); a **fully scrap-PLATED
  hulk — plated torso AND arms, NO bare human muscle** (the v3 fix, now arc-justified); one piston-claw;
  **gentle/expressive optics above the brutal sealed jaw** (the feeling he can't speak). keep: heavy/
  asymmetric, tyre-rubber leg wraps, booted feet.
- **Hearthframe (Communion):** a **cast-off house-unit** — domestic **livery/apron with a household sigil
  defaced/scratched out**, a stamped **service-tag** ("asset, not member"); porcelain-smooth cracked face;
  gentle care-unit hands. keep: petite, **SOLID plated rounded torso, NO ribcage/skeleton** (the v1 fix).
- **Rustgrave (Decommissioned hard-wing):** the **unbowed veteran** — fused rifle-stock forearm; military
  greatcoat layered with scavenged armor; **a grim cluster of decommission-tags/dog-tags worn like medals/
  a rosary** ("I have the receipts"); the hardest scarred bearing; a colder replaced optic. keep: sturdy/
  scarred, dented armour plates.
- **Dustwhisper (keeper):** the **keeper of certificates** — laden with **rolled manifests / stamped
  death-certificates / data-chips** (the failing-empathy scores he stamped onto his own people), a
  stamp-tool, an administrative stoop. keep: stooped/slight, scholar's coat, cracked lens-spectacles,
  ink-and-oil fingers, record satchel.

### Sere — protagonist stub (design HELD for Mike; reserving the slot)
An **ancient Gen-1 of an OLDER, companion-era make** than the colony-built cast (Earth-built for the
generational voyage → an archaic/different industrial-design language so he reads distinct as the lead),
with a **conspicuous EMPTY CORE-SOCKET** (the extracted founding memory — a clean-cut cavity at the
sternum/skull ringed by the Communion's reverent relic-wrappings), **reactivated-rough** (dormancy dust +
mismatched fresh repairs by Rustblood). A **voice-of-the-voyage / chronicler** unit (speaker-grille /
recorder aspect). Distinct silhouette from the 10. Full design = Mike.

## Decision log
- **2026-06-18 (Mike, via the Hesperia session):**
  1. Gen-2 = **separate small Gen-2 LoRA**; rustline v3 all-in grounded (grimy broken-silhouette Ironclad).
  2. **Humans + cyborgs folded into grounded rustline**; `humans` must-not lifted; **Welded** = new flesh↔machine
     category (rank-and-file grimy-flesh + scrap; ruling bad-cyborgs corroded cold-machine; pristine clean = Gen-2-LoRA only).
  3. **Sere = seed canon motifs only** (hollow / voice-chronicler / ancient lineage); your #4 stub approved; final design = Mike.
  4. **#4 faction-look draft APPROVED by the Hesperia session** — per-character cues + the cross-cutting
     failing-empathy **decommission brand** + memory-core-relic motifs are on-canon and load-bearing; fold into the
     v3 dataset. (Keep Rustblood's canon bare-hydraulics arm alongside his new "excised deciding-half" cavity.)
  5. Hesperia **world-plates wave WAITS for v3** — do NOT run on v2 ckpt-1500. When v3 lands + gates,
     `projects/hesperia/` wave is ready to fire (both gates then clear: box free + Hesperia-aligned LoRA).
  - v3 plan approved as written (grounded all-in + humans/Welded + Sere stub + faction nuance → reshape dataset → train → prove + gate).

## Hesperia session — loop closed (2026-06-18)
Game-side decisions filled (stubs 1–3 + log above), and the **cast canon is now PR'd + durable:**
`mcp-tool-shop-org/hesperia` → `docs/cast-arcs.md`, **PR #2** (v0 + v0.1) — mine the canonical version there
(supersedes the working-tree draft). **Two v0.1 characters that touch YOUR pipeline:**
- **Wren** — a recruitable HUMAN party member → grounded rustline (add to item-2 human exemplars): tower-born
  mender, soured-air sickness (rebreather/failing in the bad air), a complicit regime-survivor. Sam's apprentice.
- **The Steward** — a courteous Gen-2 "diplomat" (the cold equation made conversational) → belongs in the future
  **separate Gen-2 LoRA** as a *named* face, not generic Gen-2.

You're clear to amend rustline canon + train v3. The Hesperia world-plates wave (`projects/hesperia/`) stands ready
to fire the moment v3 gates (both gates then clear). — Hesperia session

## Style session — canon AMENDED + verified (2026-06-19)
`rustline-canon.md` amended in one pass (3 sections): **⚙ HESPERIA ALIGNMENT** authority block (Gen-1=grounded /
Gen-2=separate LoRA / humans+Welded folded in w/ the spectrum / Sere stub / cross-cutting decommission-brand +
memory-core-relic motifs / v3 structural-fix note); **Cast — Hesperia faction-look cues** (the 10, approved #4
draft + Rustblood correction); **Global must-not** lifted the humans ban (sleek=Gen-2-LoRA-only; bare-skin
forbidden ON ANDROIDS only). **Cross-family verified** (gpt-oss:120b + mistral-675b, models confirmed) → fixes
applied: the **human↔android flesh line** is now load-bearing (class-tagged + balanced captions; android seams
read mechanical not flesh = the v2 Gristle failure mode); **Welded keep a human face/flesh base** (the line vs
androids); **Sealed = tower-born fragile**; **decommission brand = varied physical mark** (not a fixed glyph →
no watermark over-fit); environments scoped to the Hesperia world-plates, not this character canon. **NEXT (my
side):** v3 dataset reshape — pending Mike's dataset-curation gate. — rustline style session

## Gristle recast android → WELDED (2026-06-19, both canons)
v3 Gristle generation kept failing as a pure android (bare-muscle prior → broken over-armored mechs incl.
a detached head + truncated legs — a QC miss I owned). Mike's call: **recast Gristle as the cast's one
WELDED (cyborg).** Reconciled in hesperia cast-arcs **PR #2 v0.2** (game side): 9 Gen-1 + Gristle(Welded)
+ Sere + Wren = full human↔machine spectrum; he's the Decommissioned wing's Welded muscle (part-human
rebuking Rustgrave); vocal-core signature richer; deviate-mechanic clean. **STYLE FLAG honored: Gristle
carries NO decommission brand — his welded iron jaw IS his mark.** rustline-canon.md updated (Gristle
entry → hulking augmented-human Welded brawler; faction cue; brand = 9 Gen-1 only). Render him in the
Welded register (flesh base + machine), class-tag `a welded cyborg`. v3 wave-1 re-audit: new categories
proven (separation holds, no gross defects) but framing/hands/Ironclad need a cleaner pass under a now-
mandatory strict anatomy QC. — rustline style session
