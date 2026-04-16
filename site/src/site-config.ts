import type { SiteConfig } from '@mcptoolshop/site-theme';

export const config: SiteConfig = {
  title: 'Style Dataset Lab',
  description: 'Visual canon and dataset production pipeline — from approved work to versioned datasets, training packages, eval scorecards, and implementation examples',
  logoBadge: 'SD',
  brandName: 'style-dataset-lab',
  repoUrl: 'https://github.com/mcp-tool-shop-org/style-dataset-lab',
  footerText: 'MIT Licensed — built by <a href="https://github.com/mcp-tool-shop-org" style="color:var(--color-muted);text-decoration:underline">mcp-tool-shop-org</a>',

  hero: {
    badge: 'v2.2.0',
    headline: 'Style Dataset Lab',
    headlineAccent: 'From visual canon to trained model assets.',
    description: 'Build project-specific visual canon. Curate and bind approved work. Produce reproducible dataset packages. Build trainer-ready assets with frozen manifests. Score outputs against canon-aware eval packs. Re-ingest accepted work back into the project. The full closed loop.',
    primaryCta: { href: '#usage', label: 'Get started' },
    secondaryCta: { href: 'handbook/', label: 'Read the Handbook' },
    previews: [
      { label: 'Install', code: 'npm install -g @mcptoolshop/style-dataset-lab' },
      { label: 'Dataset', code: 'sdlab snapshot create --project my-project\nsdlab split build\nsdlab export build' },
      { label: 'Train', code: 'sdlab training-manifest create --profile character-style-lora\nsdlab training-package build\nsdlab eval-run create\nsdlab implementation-pack build' },
    ],
  },

  sections: [
    {
      kind: 'features',
      id: 'features',
      title: 'Features',
      subtitle: 'A complete pipeline from visual canon to trained model assets and back.',
      features: [
        { title: 'Frozen Snapshots', desc: 'Deterministic record selection with config fingerprinting. Every inclusion has an explicit reason trace. Once created, a snapshot never silently changes.' },
        { title: 'Leakage-Safe Splits', desc: 'Subject-isolated, lane-balanced train/val/test partitions. Records sharing a subject family always land in the same split. Seeded PRNG for reproducibility.' },
        { title: 'Training Packages', desc: 'Manifest-bound, adapter-driven packages for specific trainers. Ships with generic-image-caption and diffusers-lora adapters. Adapters never mutate dataset truth.' },
        { title: 'Eval Scorecards', desc: 'Score generated outputs against canon-aware eval packs. Four task types: lane coverage, forbidden drift, anchor/gold, subject continuity. Per-task pass/fail verdicts.' },
        { title: 'Implementation Packs', desc: 'Prompt examples, known failure cases, subject continuity groups, and re-ingest guidance. Everything needed to use the trained asset in production.' },
        { title: 'Closed Loop', desc: 'Accepted generated outputs re-enter through normal review and canon binding. No bypass. Generated work is judged like everything else.' },
        { title: '5 Domain Templates', desc: 'Game art, character design, creature design, architecture, and vehicle/mech. Each ships with real production rules, lane definitions, and scoring rubrics.' },
      ],
    },
    {
      kind: 'code-cards',
      id: 'usage',
      title: 'Usage',
      cards: [
        { title: 'Scaffold', code: '# Create a project from a domain template\nsdlab init my-project --domain character-design\n\n# Validate the project\nsdlab project doctor --project my-project' },
        { title: 'Dataset', code: '# Freeze eligible records into a snapshot\nsdlab snapshot create --project my-project\n\n# Build leakage-safe train/val/test split\nsdlab split build --project my-project\n\n# Build versioned export package\nsdlab export build --project my-project' },
        { title: 'Train', code: '# Create frozen training contract\nsdlab training-manifest create \\\n  --profile character-style-lora --project my-project\n\n# Build trainer-ready package\nsdlab training-package build --project my-project' },
        { title: 'Verify', code: '# Score outputs against eval pack\nsdlab eval-run create --project my-project\nsdlab eval-run score <id> --outputs results.jsonl\n\n# Re-ingest accepted outputs\nsdlab reingest generated --source ./outputs \\\n  --manifest <id> --project my-project' },
      ],
    },
  ],
};
