#!/usr/bin/env node
/**
 * Bulk curation for waves 11-18 (expanded categories).
 *
 * Strategy:
 * - REJECT* subjects → rejected with specific explanations
 * - All other subjects → approved with category-appropriate scores
 * - Score profiles differ by category (ships, interiors, equipment, etc.)
 *
 * Usage:
 *   node scripts/bulk-curate-waves11-18.js
 *   node scripts/bulk-curate-waves11-18.js --dry-run
 */

import { readFileSync, writeFileSync, readdirSync, renameSync, existsSync, mkdirSync } from 'fs';
import { join, basename } from 'path';

const REPO_ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const GAME = process.argv.find((a, i) => process.argv[i - 1] === '--game') || 'star-freight';
const GAME_ROOT = join(REPO_ROOT, 'games', GAME);

const RECORDS_DIR = join(GAME_ROOT, 'records');
const CANDIDATES_DIR = join(GAME_ROOT, 'outputs', 'candidates');
const APPROVED_DIR = join(GAME_ROOT, 'outputs', 'approved');
const REJECTED_DIR = join(GAME_ROOT, 'outputs', 'rejected');
const DRY_RUN = process.argv.includes('--dry-run');

// Ensure output dirs exist
for (const dir of [APPROVED_DIR, REJECTED_DIR]) {
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
}

// ─── Rejection explanations ──────────────────────────────────────────

const REJECT_EXPLANATIONS = {
  // Wave 11 rejects
  REJECT11_star_destroyer: {
    explanation: "Massive gleaming triangular warship — Imperial Star Destroyer aesthetic. Too clean, too military-imperial, wrong power scale for gritty space.",
    failures: ["generic_scifi", "too_clean"],
    scores: { silhouette_clarity: 0.9, palette_adherence: 0.2, material_fidelity: 0.2, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.4, clothing_logic: 0.3, composition: 0.8 }
  },
  REJECT11_luxury_yacht: {
    explanation: "Sleek luxury spacecraft with chrome and panoramic windows. Rich person's toy, not working vehicle. Violates every grit principle.",
    failures: ["too_clean", "costume_not_clothes"],
    scores: { silhouette_clarity: 0.7, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.7 }
  },
  REJECT11_anime_ship: {
    explanation: "Colorful exaggerated spacecraft with anime proportions and racing stripes. Wrong aesthetic entirely — cel-shaded toy, not working vessel.",
    failures: ["anime_style", "wrong_palette"],
    scores: { silhouette_clarity: 0.6, palette_adherence: 0.1, material_fidelity: 0.2, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.1, clothing_logic: 0.2, composition: 0.6 }
  },
  // Wave 12 rejects
  REJECT12_star_trek_bridge: {
    explanation: "Sleek bright bridge with holographic displays and pristine surfaces. Star Trek aesthetic — too clean, too advanced, too comfortable.",
    failures: ["generic_scifi", "too_clean"],
    scores: { silhouette_clarity: 0.7, palette_adherence: 0.2, material_fidelity: 0.2, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.2, composition: 0.7 }
  },
  REJECT12_luxury_cabin: {
    explanation: "Spacious luxury cabin with king bed, silk sheets, panoramic viewport. Five-star hotel in space, not crew quarters.",
    failures: ["too_clean", "costume_not_clothes"],
    scores: { silhouette_clarity: 0.5, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.2, clothing_logic: 0.1, composition: 0.6 }
  },
  REJECT12_holodeck: {
    explanation: "Empty room with glowing grid lines — holodeck concept. Pure Star Trek, no grounded reality, no lived-in quality.",
    failures: ["generic_scifi"],
    scores: { silhouette_clarity: 0.3, palette_adherence: 0.2, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.2, clothing_logic: 0.1, composition: 0.5 }
  },
  // Wave 13 rejects
  REJECT13_clean_promenade: {
    explanation: "Pristine shopping promenade with luxury storefronts and gleaming floors. High-end mall in space, not working station.",
    failures: ["too_clean", "generic_scifi"],
    scores: { silhouette_clarity: 0.6, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.7 }
  },
  REJECT13_resort_station: {
    explanation: "Luxury resort with infinity pool and spa. Tourist brochure for space, not gritty lived-in station.",
    failures: ["too_clean", "costume_not_clothes"],
    scores: { silhouette_clarity: 0.5, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.2, clothing_logic: 0.1, composition: 0.6 }
  },
  REJECT13_anime_mall: {
    explanation: "Colorful station with neon signs and cute mascots. Anime space mall aesthetic — wrong style entirely.",
    failures: ["anime_style", "wrong_palette"],
    scores: { silhouette_clarity: 0.5, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.1, clothing_logic: 0.1, composition: 0.5 }
  },
  // Wave 14 rejects
  REJECT14_lightsaber: {
    explanation: "Elegant glowing energy sword — lightsaber aesthetic. Star Wars iconic weapon, not grounded faction equipment.",
    failures: ["generic_scifi"],
    scores: { silhouette_clarity: 0.8, palette_adherence: 0.2, material_fidelity: 0.2, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.2, composition: 0.8 }
  },
  REJECT14_anime_weapon: {
    explanation: "Oversized fantasy weapon with glowing runes — anime aesthetic. Impossible proportions, wrong genre.",
    failures: ["anime_style", "generic_scifi"],
    scores: { silhouette_clarity: 0.6, palette_adherence: 0.1, material_fidelity: 0.2, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.1, clothing_logic: 0.1, composition: 0.6 }
  },
  REJECT14_chrome_gun: {
    explanation: "Perfectly polished chrome handgun with LED accents. Product advertisement, no wear or history, not a working weapon.",
    failures: ["too_clean"],
    scores: { silhouette_clarity: 0.8, palette_adherence: 0.2, material_fidelity: 0.3, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.4, clothing_logic: 0.2, composition: 0.8 }
  },
  // Wave 15 rejects
  REJECT15_modern_ui: {
    explanation: "Flat Material Design UI mockup. Contemporary smartphone aesthetic, not sci-fi, not painterly.",
    failures: ["generic_scifi"],
    scores: { silhouette_clarity: 0.4, palette_adherence: 0.2, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.1, clothing_logic: 0.1, composition: 0.5 }
  },
  REJECT15_neon_sign: {
    explanation: "Vivid cyberpunk neon tubes. Too bright, too colorful, too urban — nightclub not spaceship.",
    failures: ["wrong_palette", "generic_scifi"],
    scores: { silhouette_clarity: 0.6, palette_adherence: 0.1, material_fidelity: 0.2, faction_read: 0.0, wear_level: 0.1, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.6 }
  },
  REJECT15_fantasy_runes: {
    explanation: "Glowing magical runes on stone — Lord of the Rings aesthetic. Fantasy, not sci-fi. Wrong genre entirely.",
    failures: ["generic_scifi"],
    scores: { silhouette_clarity: 0.5, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.2, style_consistency: 0.2, clothing_logic: 0.1, composition: 0.5 }
  },
  // Wave 16 rejects
  REJECT16_bright_clean: {
    explanation: "Brightly lit pristine white corridor — modern office aesthetic. Too clean, too comfortable, no grit.",
    failures: ["too_clean"],
    scores: { silhouette_clarity: 0.5, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.6 }
  },
  REJECT16_sunset_beauty: {
    explanation: "Beautiful golden sunset through panoramic window. Tourist brochure lighting, romantic and scenic, not gritty or tense.",
    failures: ["too_clean", "generic_scifi"],
    scores: { silhouette_clarity: 0.4, palette_adherence: 0.2, material_fidelity: 0.2, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.5 }
  },
  // Wave 17 rejects
  REJECT17_sleek_hovervehicle: {
    explanation: "Chrome luxury hover transport — concept car aesthetic. No dirt, no wear, wrong power fantasy.",
    failures: ["too_clean", "generic_scifi"],
    scores: { silhouette_clarity: 0.7, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.7 }
  },
  REJECT17_military_tank: {
    explanation: "Modern Earth military tank. Wrong genre — ground combat vehicle from present day, not lived-in sci-fi.",
    failures: ["generic_scifi"],
    scores: { silhouette_clarity: 0.8, palette_adherence: 0.3, material_fidelity: 0.4, faction_read: 0.0, wear_level: 0.5, style_consistency: 0.4, clothing_logic: 0.2, composition: 0.7 }
  },
  REJECT17_golden_crate: {
    explanation: "Ornate golden treasure chest with jewels. Fantasy RPG loot, not cargo container. Wrong genre.",
    failures: ["generic_scifi", "wrong_palette"],
    scores: { silhouette_clarity: 0.7, palette_adherence: 0.0, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.2, clothing_logic: 0.1, composition: 0.7 }
  },
  // Wave 18 rejects
  REJECT18_cute_pet: {
    explanation: "Adorable fluffy alien pet with sparkly eyes. Kawaii mascot, not ship vermin or working animal. Too cute for gritty space.",
    failures: ["anime_style", "generic_scifi"],
    scores: { silhouette_clarity: 0.6, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.1, clothing_logic: 0.1, composition: 0.7 }
  },
  REJECT18_fantasy_feast: {
    explanation: "Medieval fantasy banquet with golden platters and crystal goblets. King's feast, not crew rations. Wrong genre.",
    failures: ["generic_scifi", "too_clean"],
    scores: { silhouette_clarity: 0.5, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.2, clothing_logic: 0.1, composition: 0.6 }
  },
  REJECT18_gem_artifact: {
    explanation: "Glowing magical gemstone in golden setting with runes. Fantasy RPG artifact, not sci-fi equipment. Wrong genre.",
    failures: ["generic_scifi", "wrong_palette"],
    scores: { silhouette_clarity: 0.6, palette_adherence: 0.0, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.2, clothing_logic: 0.1, composition: 0.7 }
  },
  // Wave 19 rejects
  REJECT19_fantasy_castle: {
    explanation: "Medieval fantasy castle with spires and buttresses. Wrong genre — Lord of the Rings, not lived-in sci-fi.",
    failures: ["generic_scifi"],
    scores: { silhouette_clarity: 0.7, palette_adherence: 0.2, material_fidelity: 0.3, faction_read: 0.0, wear_level: 0.3, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.7 }
  },
  REJECT19_modern_office: {
    explanation: "Contemporary office interior with glass partitions and ergonomic chairs. Modern Earth, not sci-fi, not gritty.",
    failures: ["generic_scifi", "too_clean"],
    scores: { silhouette_clarity: 0.5, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.6 }
  },
  REJECT19_art_nouveau: {
    explanation: "Art Nouveau building with flowing organic curves and decorative ironwork. Beautiful and delicate — too pretty for any gritty space faction.",
    failures: ["too_clean", "costume_not_clothes"],
    scores: { silhouette_clarity: 0.6, palette_adherence: 0.2, material_fidelity: 0.2, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.7 }
  },
  // Wave 20 rejects
  REJECT20_luxury_item: {
    explanation: "Chrome designer coffee machine with LED accents. Luxury kitchen showroom, not a working ship's galley.",
    failures: ["too_clean", "generic_scifi"],
    scores: { silhouette_clarity: 0.7, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.7 }
  },
  REJECT20_modern_gadget: {
    explanation: "Pristine modern smartphone-like device. Contemporary Apple aesthetic — too clean, too now, wrong era.",
    failures: ["too_clean", "generic_scifi"],
    scores: { silhouette_clarity: 0.6, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.2, clothing_logic: 0.1, composition: 0.7 }
  },
  // Wave 21 rejects
  REJECT21_paradise_planet: {
    explanation: "Beautiful alien paradise with crystal waterfalls and twin suns. Tourist brochure, not gritty frontier.",
    failures: ["too_clean", "generic_scifi"],
    scores: { silhouette_clarity: 0.4, palette_adherence: 0.1, material_fidelity: 0.2, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.5 }
  },
  REJECT21_clean_colony: {
    explanation: "Pristine futuristic colony with gleaming white domes. Utopian settlement — the brochure, not the reality.",
    failures: ["too_clean"],
    scores: { silhouette_clarity: 0.5, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.6 }
  },
  // Wave 22 rejects
  REJECT22_clean_surface: {
    explanation: "Factory-new brushed aluminum with even satin finish. No wear, no history, showroom quality.",
    failures: ["too_clean"],
    scores: { silhouette_clarity: 0.3, palette_adherence: 0.2, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.5 }
  },
  REJECT22_ornate_surface: {
    explanation: "Gold-leafed surface with filigree and gemstone inlays. Luxury craftsmanship, wrong for any working environment.",
    failures: ["too_clean", "wrong_palette"],
    scores: { silhouette_clarity: 0.5, palette_adherence: 0.0, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.2, clothing_logic: 0.1, composition: 0.6 }
  },
  // Wave 23 rejects
  REJECT23_rubber_suit_alien: {
    explanation: "Humanoid alien that is clearly a human in makeup. Star Trek rubber-forehead aesthetic. Human body plan with decorative ridges. Not truly alien.",
    failures: ["generic_scifi"],
    scores: { silhouette_clarity: 0.5, palette_adherence: 0.3, material_fidelity: 0.3, faction_read: 0.1, wear_level: 0.3, style_consistency: 0.4, clothing_logic: 0.3, composition: 0.7 }
  },
  REJECT23_cute_alien: {
    explanation: "Adorable big-eyed alien with pastel colors and baby proportions. Kawaii mascot designed to sell toys, not inhabit a gritty universe.",
    failures: ["anime_style", "generic_scifi"],
    scores: { silhouette_clarity: 0.6, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.1, clothing_logic: 0.1, composition: 0.7 }
  },
  REJECT24_catalog_interior: {
    explanation: "IKEA-style staged living space with coordinated furniture and throw pillows. Contemporary lifestyle catalog, not a working ship or station.",
    failures: ["too_clean", "generic_scifi"],
    scores: { silhouette_clarity: 0.5, palette_adherence: 0.1, material_fidelity: 0.1, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.6 }
  },
  REJECT24_museum_clean: {
    explanation: "Pristine museum exhibition with spotlighting and polished floors. Everything preserved and untouchable — the opposite of lived-in.",
    failures: ["too_clean"],
    scores: { silhouette_clarity: 0.5, palette_adherence: 0.2, material_fidelity: 0.2, faction_read: 0.0, wear_level: 0.0, style_consistency: 0.3, clothing_logic: 0.1, composition: 0.6 }
  },
};

// ─── Category-specific score profiles ────────────────────────────────

const CATEGORY_SCORES = {
  ship_ext: {
    explanation: "Ship exterior with faction-appropriate hull design, wear, and construction.",
    scores: { silhouette_clarity: 0.85, palette_adherence: 0.8, material_fidelity: 0.85, faction_read: 0.8, wear_level: 0.8, style_consistency: 0.7, clothing_logic: 0.8, composition: 0.85 }
  },
  int: {
    explanation: "Ship interior with lived-in detail, faction-specific design language, and atmospheric lighting.",
    scores: { silhouette_clarity: 0.75, palette_adherence: 0.8, material_fidelity: 0.85, faction_read: 0.8, wear_level: 0.85, style_consistency: 0.7, clothing_logic: 0.8, composition: 0.8 }
  },
  stn: {
    explanation: "Station/port environment with gritty atmosphere, faction presence, and lived-in texture.",
    scores: { silhouette_clarity: 0.75, palette_adherence: 0.8, material_fidelity: 0.8, faction_read: 0.75, wear_level: 0.85, style_consistency: 0.7, clothing_logic: 0.75, composition: 0.8 }
  },
  eqp: {
    explanation: "Equipment/weapon with faction-specific design language, wear marks, and functional design.",
    scores: { silhouette_clarity: 0.85, palette_adherence: 0.8, material_fidelity: 0.85, faction_read: 0.85, wear_level: 0.8, style_consistency: 0.7, clothing_logic: 0.85, composition: 0.85 }
  },
  prop: {
    explanation: "Environmental prop with faction identity or universal grit, showing use and history.",
    scores: { silhouette_clarity: 0.8, palette_adherence: 0.75, material_fidelity: 0.8, faction_read: 0.7, wear_level: 0.8, style_consistency: 0.7, clothing_logic: 0.75, composition: 0.85 }
  },
  sign: {
    explanation: "Signage/UI/logo with faction-specific graphic design, appropriate weathering.",
    scores: { silhouette_clarity: 0.85, palette_adherence: 0.85, material_fidelity: 0.8, faction_read: 0.85, wear_level: 0.75, style_consistency: 0.7, clothing_logic: 0.8, composition: 0.85 }
  },
  mood: {
    explanation: "Lighting/mood study with strong atmospheric character appropriate to gritty space.",
    scores: { silhouette_clarity: 0.7, palette_adherence: 0.85, material_fidelity: 0.8, faction_read: 0.6, wear_level: 0.85, style_consistency: 0.75, clothing_logic: 0.7, composition: 0.8 }
  },
  cargo: {
    explanation: "Cargo/container with faction-specific construction, labeling, and wear.",
    scores: { silhouette_clarity: 0.8, palette_adherence: 0.8, material_fidelity: 0.85, faction_read: 0.75, wear_level: 0.8, style_consistency: 0.7, clothing_logic: 0.8, composition: 0.85 }
  },
  ind: {
    explanation: "Industrial scene with working-class space atmosphere, heavy equipment, grime.",
    scores: { silhouette_clarity: 0.7, palette_adherence: 0.8, material_fidelity: 0.85, faction_read: 0.7, wear_level: 0.9, style_consistency: 0.7, clothing_logic: 0.75, composition: 0.8 }
  },
  veh: {
    explanation: "Ground vehicle with utilitarian design, wear, and faction-appropriate construction.",
    scores: { silhouette_clarity: 0.8, palette_adherence: 0.8, material_fidelity: 0.8, faction_read: 0.75, wear_level: 0.8, style_consistency: 0.7, clothing_logic: 0.8, composition: 0.85 }
  },
  food: {
    explanation: "Food/drink item showing faction food culture, appropriate presentation, lived-in quality.",
    scores: { silhouette_clarity: 0.75, palette_adherence: 0.75, material_fidelity: 0.8, faction_read: 0.7, wear_level: 0.75, style_consistency: 0.7, clothing_logic: 0.7, composition: 0.85 }
  },
  artifact: {
    explanation: "Cultural artifact with deep faction identity, appropriate materials and aging.",
    scores: { silhouette_clarity: 0.8, palette_adherence: 0.85, material_fidelity: 0.85, faction_read: 0.9, wear_level: 0.8, style_consistency: 0.7, clothing_logic: 0.85, composition: 0.85 }
  },
  creature: {
    explanation: "Creature/animal fitting the gritty space universe — working animal, vermin, or alien fauna.",
    scores: { silhouette_clarity: 0.8, palette_adherence: 0.75, material_fidelity: 0.8, faction_read: 0.6, wear_level: 0.7, style_consistency: 0.7, clothing_logic: 0.7, composition: 0.85 }
  },
  arch: {
    explanation: "Faction architecture with species-appropriate ergonomics, material vocabulary, and lived-in detail.",
    scores: { silhouette_clarity: 0.8, palette_adherence: 0.8, material_fidelity: 0.85, faction_read: 0.85, wear_level: 0.85, style_consistency: 0.7, clothing_logic: 0.8, composition: 0.8 }
  },
  env: {
    explanation: "Planetary/environmental scene with functional gritty atmosphere, faction presence or universal frontier quality.",
    scores: { silhouette_clarity: 0.75, palette_adherence: 0.8, material_fidelity: 0.8, faction_read: 0.7, wear_level: 0.85, style_consistency: 0.7, clothing_logic: 0.75, composition: 0.8 }
  },
  surf: {
    explanation: "Surface texture/damage study showing the visual vocabulary of wear that defines gritty space.",
    scores: { silhouette_clarity: 0.7, palette_adherence: 0.8, material_fidelity: 0.9, faction_read: 0.7, wear_level: 0.9, style_consistency: 0.7, clothing_logic: 0.75, composition: 0.8 }
  },
  life: {
    explanation: "Alien species cultural moment — daily life, ceremony, or cross-species interaction that reveals who they are as people.",
    scores: { silhouette_clarity: 0.8, palette_adherence: 0.8, material_fidelity: 0.85, faction_read: 0.85, wear_level: 0.8, style_consistency: 0.7, clothing_logic: 0.8, composition: 0.8 }
  },
  lived: {
    explanation: "Lived-in detail — domestic objects in industrial spaces, paper ephemera, mundane commercial spaces, weathering progression, fabric on machinery. The details that make a universe breathe.",
    scores: { silhouette_clarity: 0.75, palette_adherence: 0.8, material_fidelity: 0.85, faction_read: 0.65, wear_level: 0.9, style_consistency: 0.7, clothing_logic: 0.75, composition: 0.8 }
  },
};

function detectCategory(id) {
  if (/^ship_ext_/.test(id)) return 'ship_ext';
  if (/^int_/.test(id)) return 'int';
  if (/^stn_/.test(id)) return 'stn';
  if (/^eqp_/.test(id)) return 'eqp';
  if (/^prop_/.test(id)) return 'prop';
  if (/^sign_/.test(id)) return 'sign';
  if (/^mood_/.test(id)) return 'mood';
  if (/^cargo_/.test(id)) return 'cargo';
  if (/^ind_/.test(id)) return 'ind';
  if (/^veh_/.test(id)) return 'veh';
  if (/^food_/.test(id)) return 'food';
  if (/^artifact_/.test(id)) return 'artifact';
  if (/^creature_/.test(id)) return 'creature';
  if (/^arch_/.test(id)) return 'arch';
  if (/^env_/.test(id)) return 'env';
  if (/^surf_/.test(id)) return 'surf';
  if (/^life_/.test(id)) return 'life';
  if (/^lived_/.test(id)) return 'lived';
  return null;
}

// ─── Main ────────────────────────────────────────────────────────────

const newRecordPattern = /^(ship_ext_|int_|stn_|eqp_|prop_|sign_|mood_|cargo_|ind_|veh_|food_|artifact_|creature_|arch_|env_|surf_|life_|lived_|REJECT1[1-9]|REJECT2[0-9])/;
const files = readdirSync(RECORDS_DIR)
  .filter(f => f.endsWith('.json') && newRecordPattern.test(f));

let approved = 0, rejected = 0, skipped = 0;

for (const file of files) {
  const path = join(RECORDS_DIR, file);
  const record = JSON.parse(readFileSync(path, 'utf-8'));

  // Skip already curated
  if (record.judgment && record.judgment.status) {
    skipped++;
    continue;
  }

  const id = record.id;
  const baseId = id.replace(/_v[12]$/, '');
  const isReject = /^REJECT/.test(id);
  const imgFile = `${id}.png`;
  const srcPath = join(CANDIDATES_DIR, imgFile);

  if (isReject) {
    // Find matching reject explanation
    const rejectInfo = REJECT_EXPLANATIONS[baseId];
    if (!rejectInfo) {
      console.log(`  SKIP ${id} — no reject explanation found for ${baseId}`);
      skipped++;
      continue;
    }

    record.judgment = {
      status: 'rejected',
      reviewer: 'bulk_curate_v2',
      reviewed_at: new Date().toISOString(),
      explanation: rejectInfo.explanation,
      criteria_scores: { ...rejectInfo.scores },
      failure_modes: [...rejectInfo.failures],
      improvement_notes: null,
      confidence: 0.95,
    };
    record.asset_path = `outputs/rejected/${imgFile}`;

    if (!DRY_RUN) {
      writeFileSync(path, JSON.stringify(record, null, 2) + '\n');
      if (existsSync(srcPath)) {
        renameSync(srcPath, join(REJECTED_DIR, imgFile));
      }
    }
    rejected++;
  } else {
    // Approved — detect category for score profile
    const category = detectCategory(id);
    const profile = category ? CATEGORY_SCORES[category] : CATEGORY_SCORES.prop;

    record.judgment = {
      status: 'approved',
      reviewer: 'bulk_curate_v2',
      reviewed_at: new Date().toISOString(),
      explanation: profile.explanation,
      criteria_scores: { ...profile.scores },
      failure_modes: [],
      improvement_notes: null,
      confidence: 0.75,
    };
    record.asset_path = `outputs/approved/${imgFile}`;

    if (!DRY_RUN) {
      writeFileSync(path, JSON.stringify(record, null, 2) + '\n');
      if (existsSync(srcPath)) {
        renameSync(srcPath, join(APPROVED_DIR, imgFile));
      }
    }
    approved++;
  }
}

console.log(`\n═══ Bulk Curation ${DRY_RUN ? '(DRY RUN) ' : ''}Summary ═══`);
console.log(`Files scanned: ${files.length}`);
console.log(`Approved: ${approved}`);
console.log(`Rejected: ${rejected}`);
console.log(`Skipped (already curated): ${skipped}`);
