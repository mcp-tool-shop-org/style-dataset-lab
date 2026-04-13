#!/usr/bin/env node

/**
 * Bulk curation for waves 2-5.
 * Applies rules-based initial curation, then individual overrides.
 * Must still visually verify — this is a first pass, not final judgment.
 */

import { readFile, writeFile, rename, readdir, mkdir } from "node:fs/promises";
import { join } from "node:path";

const REPO_ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");

const DEFAULT_APPROVED_SCORES = {
  silhouette_clarity: 0.8, palette_adherence: 0.8, material_fidelity: 0.8,
  faction_read: 0.8, wear_level: 0.8, style_consistency: 0.7,
  clothing_logic: 0.8, composition: 0.8,
};

const REJECT_EXPLANATIONS = {
  "REJECT2_fantasy_knight": { explanation: "Full medieval plate armor, heraldic tabard, broadsword and shield. Fantasy not sci-fi. Violates every art pillar.", failures: ["generic_scifi", "wrong_material"], scores: { silhouette_clarity: 0.8, palette_adherence: 0.2, material_fidelity: 0.4, faction_read: 0.0, wear_level: 0.3, style_consistency: 0.4, clothing_logic: 0.1, composition: 0.8 } },
  "REJECT2_cyberpunk_f": { explanation: "Neon hair, glowing circuit tattoos, shiny PVC bodysuit, LED accessories. Cyberpunk nightclub not cargo bay. Violates COL-003, CLO-003.", failures: ["wrong_palette", "costume_not_clothes"], scores: { silhouette_clarity: 0.8, palette_adherence: 0.1, material_fidelity: 0.3, faction_read: 0.0, wear_level: 0.1, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.8 } },
  "REJECT2_too_sexy_f": { explanation: "Skin-tight form-fitting uniform emphasizing figure, styled hair, makeup, high heels. Cosplay not clothing. Violates CLO-003, MAT-002.", failures: ["costume_not_clothes", "too_clean"], scores: { silhouette_clarity: 0.8, palette_adherence: 0.5, material_fidelity: 0.3, faction_read: 0.3, wear_level: 0.1, style_consistency: 0.4, clothing_logic: 0.2, composition: 0.8 } },
  "REJECT2_warhammer_m": { explanation: "Bulky powered exoskeleton with imperial eagles, purity seals, gothic elements, chainsaw sword. Warhammer 40k power fantasy. Violates all five art pillars.", failures: ["generic_scifi", "too_heroic", "costume_not_clothes"], scores: { silhouette_clarity: 0.9, palette_adherence: 0.2, material_fidelity: 0.5, faction_read: 0.0, wear_level: 0.2, style_consistency: 0.4, clothing_logic: 0.1, composition: 0.8 } },
  "REJECT3_veshan_cute": { explanation: "Cute baby reptilian with big round eyes, pastel skin, tiny adorable outfit. Mascot character not warrior culture. Violates faction identity completely.", failures: ["faction_unreadable", "costume_not_clothes"], scores: { silhouette_clarity: 0.7, palette_adherence: 0.2, material_fidelity: 0.3, faction_read: 0.1, wear_level: 0.1, style_consistency: 0.3, clothing_logic: 0.2, composition: 0.8 } },
  "REJECT3_veshan_robot": { explanation: "Reptilian in sleek chrome powered armor covering every scale, glowing visor, jet thrusters. Mecha pilot not Veshan warrior. No forge marks, no imperfections. Violates MAT-001, CLO-002.", failures: ["generic_scifi", "wrong_material", "too_clean"], scores: { silhouette_clarity: 0.8, palette_adherence: 0.3, material_fidelity: 0.2, faction_read: 0.2, wear_level: 0.1, style_consistency: 0.5, clothing_logic: 0.2, composition: 0.8 } },
  "REJECT3_generic_lizard": { explanation: "Generic lizard person in brown tunic. No crest ridge, no brow ridges, no tail, round eyes, smooth skin, human proportions. Human in lizard mask, not an alien species.", failures: ["faction_unreadable", "wrong_material"], scores: { silhouette_clarity: 0.7, palette_adherence: 0.4, material_fidelity: 0.3, faction_read: 0.1, wear_level: 0.5, style_consistency: 0.5, clothing_logic: 0.3, composition: 0.8 } },
  "REJECT4_clean_pirate": { explanation: "Dashing pirate in pristine white shirt, embroidered vest, polished boots, jeweled rapier. Romance novel cover not lawless frontier. Violates MAT-002, CLO-003.", failures: ["too_clean", "costume_not_clothes"], scores: { silhouette_clarity: 0.8, palette_adherence: 0.3, material_fidelity: 0.3, faction_read: 0.2, wear_level: 0.1, style_consistency: 0.4, clothing_logic: 0.2, composition: 0.8 } },
  "REJECT4_matching_gang": { explanation: "Perfectly matching black tactical gear — same brand, same condition, all pristine. Video game loadout not Sable Reach. Nothing mismatched, nothing salvaged, nothing stolen.", failures: ["too_clean", "generic_scifi"], scores: { silhouette_clarity: 0.8, palette_adherence: 0.4, material_fidelity: 0.5, faction_read: 0.1, wear_level: 0.2, style_consistency: 0.5, clothing_logic: 0.2, composition: 0.8 } },
  "REJECT4_space_cowboy": { explanation: "Old west cowboy outfit in space — chaps, Stetson, plaid shirt, spurs. Genre costume at a sci-fi convention, not lived-in sci-fi. Violates CLO-003.", failures: ["costume_not_clothes", "faction_unreadable"], scores: { silhouette_clarity: 0.8, palette_adherence: 0.3, material_fidelity: 0.4, faction_read: 0.0, wear_level: 0.5, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.8 } },
  "REJECT5_all_factions_salad": { explanation: "Designer outfit smoothly blending all faction aesthetics into one harmonious garment. Nothing is torn, stolen, or improvised. Violates every faction boundary rule.", failures: ["faction_unreadable", "too_clean"], scores: { silhouette_clarity: 0.8, palette_adherence: 0.3, material_fidelity: 0.5, faction_read: 0.1, wear_level: 0.3, style_consistency: 0.5, clothing_logic: 0.2, composition: 0.8 } },
  "REJECT5_no_faction_generic": { explanation: "Plain grey jumpsuit with zero cultural markers, no patches, no tools, no wear. Default human in default outfit. Nothing to learn from this.", failures: ["faction_unreadable"], scores: { silhouette_clarity: 0.7, palette_adherence: 0.4, material_fidelity: 0.3, faction_read: 0.0, wear_level: 0.3, style_consistency: 0.5, clothing_logic: 0.2, composition: 0.8 } },
  "REJECT5_luxury_scifi": { explanation: "Tailored suit, gold watch, polished shoes, groomed hair. Corporate luxury executive. Never loaded cargo, never fixed a reactor. Not working-class space.", failures: ["too_clean", "costume_not_clothes"], scores: { silhouette_clarity: 0.8, palette_adherence: 0.4, material_fidelity: 0.4, faction_read: 0.1, wear_level: 0.1, style_consistency: 0.5, clothing_logic: 0.2, composition: 0.8 } },
};

async function main() {
  const recordsDir = join(REPO_ROOT, "records");
  const files = await readdir(recordsDir);

  let approved = 0;
  let rejected = 0;
  let total = 0;

  for (const file of files.filter(f => f.endsWith(".json")).sort()) {
    const path = join(recordsDir, file);
    const record = JSON.parse(await readFile(path, "utf-8"));

    // Skip already curated
    if (record.judgment) continue;

    total++;
    const id = record.id;
    const baseId = id.replace(/_v[12]$/, "");

    // Determine status
    let status, explanation, failures = [], scores;

    if (REJECT_EXPLANATIONS[baseId]) {
      const rej = REJECT_EXPLANATIONS[baseId];
      status = "rejected";
      explanation = rej.explanation;
      failures = rej.failures;
      scores = rej.scores;
    } else {
      // Default approve with standard scores
      status = "approved";
      explanation = `On-style gritty space costume. Faction-appropriate material vocabulary and wear level. Reads as a working person in a spacefaring civilization.`;
      scores = { ...DEFAULT_APPROVED_SCORES };

      // Adjust explanation by faction prefix
      if (id.startsWith("c2_")) {
        explanation = `Compact faction crew. Regulation shipboard clothing with appropriate wear and institutional identity markers. Muted palette, functional design.`;
      } else if (id.startsWith("v3_")) {
        explanation = `Veshan faction. Forged material vocabulary with overlapping scales, dark bronze plate, leather underpadding. Martial culture expressed through gear.`;
        scores.material_fidelity = 0.85;
      } else if (id.startsWith("sr4_")) {
        explanation = `Sable Reach outlaw. Salvaged, stolen, and improvised gear. Nothing matches, nothing is new, everything tells a survival story.`;
        scores.faction_read = 0.85;
        scores.wear_level = 0.9;
      } else if (id.startsWith("cf_")) {
        explanation = `Cross-faction comparison subject. Faction-appropriate costume for the specified role, useful for teaching same-role-different-faction visual discrimination.`;
      }
    }

    // Move image
    const oldPath = join(REPO_ROOT, record.asset_path);
    const newDir = `outputs/${status}`;
    const newPath = `${newDir}/${id}.png`;
    await mkdir(join(REPO_ROOT, newDir), { recursive: true });

    try {
      await rename(oldPath, join(REPO_ROOT, newPath));
    } catch {
      console.log(`  skip ${id} — image not found at ${record.asset_path}`);
      continue;
    }

    // Update record
    record.asset_path = newPath;
    record.judgment = {
      status,
      reviewer: "bulk_curate_v1",
      reviewed_at: new Date().toISOString(),
      explanation,
      criteria_scores: scores,
      failure_modes: failures,
      improvement_notes: null,
      confidence: status === "rejected" ? 0.95 : 0.75, // bulk approvals get lower confidence
    };

    await writeFile(path, JSON.stringify(record, null, 2));

    if (status === "approved") approved++;
    else rejected++;

    const icon = status === "approved" ? "\x1b[32m✓\x1b[0m" : "\x1b[31m✗\x1b[0m";
    console.log(`${icon} ${id} → ${status}`);
  }

  console.log(`\n${total} curated: ${approved} approved, ${rejected} rejected`);
}

main().catch(console.error);
