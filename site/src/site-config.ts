import type { SiteConfig } from '@mcptoolshop/site-theme';

export const config: SiteConfig = {
  title: 'Style Dataset Lab',
  description: 'Visual dataset factory — generate, curate, and export multimodal training data',
  logoBadge: 'SD',
  brandName: 'style-dataset-lab',
  repoUrl: 'https://github.com/mcp-tool-shop-org/style-dataset-lab',
  footerText: 'MIT Licensed — built by <a href="https://github.com/mcp-tool-shop-org" style="color:var(--color-muted);text-decoration:underline">mcp-tool-shop-org</a>',

  hero: {
    badge: 'v1.0.0',
    headline: 'Style Dataset Lab',
    headlineAccent: "Train your VLM's eye.",
    description: 'Generate images with ComfyUI, curate with per-dimension scoring, bind to canon rules, and export as training data in 10 formats.',
    primaryCta: { href: '#usage', label: 'Get started' },
    secondaryCta: { href: 'handbook/', label: 'Read the Handbook' },
    previews: [
      { label: 'Install', code: 'git clone https://github.com/mcp-tool-shop-org/style-dataset-lab' },
      { label: 'Generate', code: 'node scripts/generate.js inputs/prompts/wave1.json' },
      { label: 'Curate', code: 'node scripts/curate.js <id> approved "Clean silhouette" --scores silhouette:0.9' },
    ],
  },

  sections: [
    {
      kind: 'features',
      id: 'features',
      title: 'Features',
      subtitle: 'Everything you need to build visual training datasets from scratch.',
      features: [
        { title: 'ComfyUI Generation', desc: 'Drive ComfyUI over HTTP to produce candidate images from prompt packs. SDXL, LoRA, IP-Adapter, and ControlNet support built in.' },
        { title: 'Per-Dimension Scoring', desc: 'Curate every image across 8 scoring dimensions — silhouette clarity, palette adherence, material fidelity, faction read, wear level, style consistency, clothing logic, and composition.' },
        { title: 'Canon Binding', desc: 'Bind each asset to constitution rules with pass/fail/partial assertions. Every approval or rejection cites the specific rule it satisfies or violates.' },
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
        { title: 'Generate', code: '# Start ComfyUI, then generate a wave\nnode scripts/generate.js inputs/prompts/wave1.json\nnode scripts/generate.js inputs/prompts/wave1.json --dry-run' },
        { title: 'Curate', code: '# Approve or reject with per-dimension scores\nnode scripts/curate.js <id> approved "explanation" \\\n  --scores silhouette:0.9,palette:0.8\nnode scripts/curate.js <id> rejected "explanation" \\\n  --failures too_clean,wrong_material' },
        { title: 'Compare', code: '# Record pairwise A-vs-B preference judgments\nnode scripts/compare.js <asset_a> <asset_b> a \\\n  "Better faction read and silhouette"' },
        { title: 'Export', code: '# Export training data via repo-dataset\nnpx repo-dataset visual generate . --format trl\nnpx repo-dataset visual inspect .\nnpx repo-dataset visual validate exports/dataset.jsonl' },
      ],
    },
  ],
};
