import type { SiteConfig } from '@mcptoolshop/site-theme';

export const config: SiteConfig = {
  title: 'Style Dataset Lab',
  description: 'Visual dataset pipeline — canon to prompts to ComfyUI generation to curated, canon-bound training data',
  logoBadge: 'SD',
  brandName: 'style-dataset-lab',
  repoUrl: 'https://github.com/mcp-tool-shop-org/style-dataset-lab',
  footerText: 'MIT Licensed — built by <a href="https://github.com/mcp-tool-shop-org" style="color:var(--color-muted);text-decoration:underline">mcp-tool-shop-org</a>',

  hero: {
    badge: 'v1.2.0',
    headline: 'Style Dataset Lab',
    headlineAccent: 'Visual dataset production pipeline.',
    description: 'A production pipeline for visual dataset creation. Write canon rules, compose structured prompts, generate with ComfyUI, curate with per-dimension scoring, bind to canon, and export in 10 formats.',
    primaryCta: { href: '#usage', label: 'Get started' },
    secondaryCta: { href: 'handbook/', label: 'Read the Handbook' },
    previews: [
      { label: 'Install', code: 'npm install @mcptoolshop/style-dataset-lab' },
      { label: 'Generate', code: 'npm run generate -- --game star-freight inputs/prompts/wave1.json' },
      { label: 'Curate', code: 'npm run curate -- --game star-freight <id> approved "Clean silhouette"' },
    ],
  },

  sections: [
    {
      kind: 'features',
      id: 'features',
      title: 'Features',
      subtitle: 'A complete pipeline from style rules to training-ready data.',
      features: [
        { title: '13 Pipeline Scripts', desc: 'Generate, curate, compare, canon-bind, painterly, identity generation, ControlNet, IP-Adapter, bulk curation, and migration. All accept --game <name> for multi-game support.' },
        { title: 'Blank Templates', desc: 'Starter constitution, review rubric, and example prompt pack. Install from npm and start building your dataset immediately without cloning the repo.' },
        { title: 'Canon Binding', desc: 'Bind each asset to constitution rules with pass/fail/partial assertions. Every approval or rejection cites the specific rule it satisfies or violates.' },
        { title: 'Per-Dimension Scoring', desc: 'Curate every image across 8 scoring dimensions — silhouette clarity, palette adherence, material fidelity, faction read, wear level, style consistency, clothing logic, and composition.' },
        { title: 'Identity Packets', desc: 'Generate named-subject images with lineage tracking. Discovery, anchor, and follow-on phases preserve identity persistence across views.' },
        { title: 'Painterly Pipeline', desc: 'Post-process approved images through an img2img painterly pass. Low denoise preserves composition while shifting from photorealistic to concept-art aesthetic.' },
        { title: '10 Export Formats', desc: 'Export training data as TRL, LLaVA, Qwen2-VL, Axolotl, LLaMA-Factory, and more via repo-dataset. Classification, preference pairs, and critique training units.' },
      ],
    },
    {
      kind: 'code-cards',
      id: 'usage',
      title: 'Usage',
      cards: [
        { title: 'Generate', code: '# Start ComfyUI, then generate a wave\nnpm run generate -- --game star-freight inputs/prompts/wave1.json\nnpm run generate -- --game star-freight inputs/prompts/wave1.json --dry-run' },
        { title: 'Curate', code: '# Approve or reject with per-dimension scores\nnpm run curate -- --game star-freight <id> approved "explanation" \\\n  --scores silhouette:0.9,palette:0.8\nnpm run curate -- --game star-freight <id> rejected "explanation" \\\n  --failures too_clean,wrong_material' },
        { title: 'Compare', code: '# Record pairwise A-vs-B preference judgments\nnpm run compare -- --game star-freight <asset_a> <asset_b> a \\\n  "Better faction read and silhouette"' },
        { title: 'Export', code: '# Export training data via repo-dataset\nrepo-dataset visual generate ./games/star-freight --format trl\nrepo-dataset visual inspect ./games/star-freight' },
      ],
    },
  ],
};
