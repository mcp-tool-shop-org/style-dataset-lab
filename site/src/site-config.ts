import type { SiteConfig } from '@mcptoolshop/site-theme';

export const config: SiteConfig = {
  title: 'Style Dataset Lab',
  description: 'Visual canon and dataset production pipeline — turn approved visual work into versioned, review-backed datasets, splits, export packages, and eval packs',
  logoBadge: 'SD',
  brandName: 'style-dataset-lab',
  repoUrl: 'https://github.com/mcp-tool-shop-org/style-dataset-lab',
  footerText: 'MIT Licensed — built by <a href="https://github.com/mcp-tool-shop-org" style="color:var(--color-muted);text-decoration:underline">mcp-tool-shop-org</a>',

  hero: {
    badge: 'v2.1.0',
    headline: 'Style Dataset Lab',
    headlineAccent: 'From visual canon to versioned datasets.',
    description: 'Build project-specific visual canon. Curate and bind approved work to constitution rules. Produce reproducible dataset packages with leakage-safe splits. Generate eval packs for future model verification. Works for game art, character design, creature design, architecture, and vehicle concepts.',
    primaryCta: { href: '#usage', label: 'Get started' },
    secondaryCta: { href: 'handbook/', label: 'Read the Handbook' },
    previews: [
      { label: 'Install', code: 'npm install -g @mcptoolshop/style-dataset-lab' },
      { label: 'Init', code: 'sdlab init my-project --domain character-design' },
      { label: 'Dataset', code: 'sdlab snapshot create --project my-project\nsdlab split build\nsdlab export build\nsdlab eval-pack build' },
    ],
  },

  sections: [
    {
      kind: 'features',
      id: 'features',
      title: 'Features',
      subtitle: 'A complete pipeline from visual canon to versioned, reproducible datasets.',
      features: [
        { title: 'Frozen Snapshots', desc: 'Deterministic record selection with config fingerprinting. Every inclusion has an explicit reason trace. Once created, a snapshot never silently changes.' },
        { title: 'Leakage-Safe Splits', desc: 'Subject-isolated, lane-balanced train/val/test partitions. Records sharing a subject family always land in the same split. Seeded PRNG for reproducibility.' },
        { title: 'Export Packages', desc: 'Self-contained datasets: manifest, metadata, images, splits, dataset card, and checksums. Everything needed to rebuild the dataset from scratch.' },
        { title: 'Canon-Aware Eval Packs', desc: 'Four task types: lane coverage, forbidden drift, anchor/gold, and subject continuity. Proves the dataset feeds model evaluation, not just file dumps.' },
        { title: 'Canon Binding', desc: 'Every approved asset is bound to constitution rules with pass/fail/partial verdicts. Every approval or rejection cites the specific rule it satisfies or violates.' },
        { title: '5 Domain Templates', desc: 'Game art, character design, creature design, architecture, and vehicle/mech. Each ships with real production rules, lane definitions, and scoring rubrics.' },
        { title: 'Dataset Cards', desc: 'Markdown and JSON twin cards documenting selection criteria, split strategy, lane balance, quality gates, and full provenance chain.' },
      ],
    },
    {
      kind: 'code-cards',
      id: 'usage',
      title: 'Usage',
      cards: [
        { title: 'Scaffold', code: '# Create a project from a domain template\nsdlab init my-project --domain character-design\n\n# Validate the project\nsdlab project doctor --project my-project' },
        { title: 'Curate + Bind', code: '# Approve or reject with per-dimension scores\nsdlab curate <id> approved "Good proportions" \\\n  --scores proportion_accuracy:0.9 --project my-project\n\n# Bind all records to constitution rules\nsdlab bind --project my-project' },
        { title: 'Dataset', code: '# Freeze eligible records into a snapshot\nsdlab snapshot create --project my-project\n\n# Build leakage-safe train/val/test split\nsdlab split build --project my-project\n\n# Build versioned export package\nsdlab export build --project my-project' },
        { title: 'Verify', code: '# Audit split for subject leakage + lane balance\nsdlab split audit <split-id>\n\n# Build canon-aware eval pack\nsdlab eval-pack build --project my-project\n\n# Generate dataset card\nsdlab card generate --project my-project' },
      ],
    },
  ],
};
