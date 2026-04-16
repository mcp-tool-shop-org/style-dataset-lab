import type { SiteConfig } from '@mcptoolshop/site-theme';

export const config: SiteConfig = {
  title: 'Style Dataset Lab',
  description: 'Canon-bound visual dataset pipeline for directed image production — define project canon, generate and curate assets, bind to constitution rules, export trustworthy training data',
  logoBadge: 'SD',
  brandName: 'style-dataset-lab',
  repoUrl: 'https://github.com/mcp-tool-shop-org/style-dataset-lab',
  footerText: 'MIT Licensed — built by <a href="https://github.com/mcp-tool-shop-org" style="color:var(--color-muted);text-decoration:underline">mcp-tool-shop-org</a>',

  hero: {
    badge: 'v2.0.0',
    headline: 'Style Dataset Lab',
    headlineAccent: 'Canon-bound visual dataset pipeline.',
    description: 'Define project canon. Generate and curate assets against constitution rules. Export trustworthy datasets for training, evaluation, and production reuse. Works for game art, character design, creature design, architecture, and vehicle concepts.',
    primaryCta: { href: '#usage', label: 'Get started' },
    secondaryCta: { href: 'handbook/', label: 'Read the Handbook' },
    previews: [
      { label: 'Install', code: 'npm install -g @mcptoolshop/style-dataset-lab' },
      { label: 'Init', code: 'sdlab init my-project --domain character-design' },
      { label: 'Pipeline', code: 'sdlab generate wave1.json --project my-project\nsdlab curate <id> approved "explanation"\nsdlab bind --project my-project' },
    ],
  },

  sections: [
    {
      kind: 'features',
      id: 'features',
      title: 'Features',
      subtitle: 'A complete pipeline from visual canon to trustworthy training data.',
      features: [
        { title: 'sdlab CLI', desc: 'Unified command-line interface. Init projects from domain templates, generate, curate, bind, compare, and validate — all through one tool.' },
        { title: '5 Domain Templates', desc: 'Game art, character design, creature design, architecture, and vehicle/mech. Each ships with real production rules, lane definitions, and scoring rubrics.' },
        { title: 'Canon Binding', desc: 'Bind each asset to constitution rules with pass/fail/partial verdicts. Every approval or rejection cites the specific rule it satisfies or violates.' },
        { title: 'Per-Dimension Scoring', desc: 'Curate every image across project-defined scoring dimensions — from silhouette clarity to anatomical plausibility to structural integrity.' },
        { title: 'Project Doctor', desc: 'Validate config completeness: required files, lane patterns, rubric cross-references, constitution rules, and directory structure.' },
        { title: 'Identity Continuity', desc: 'Generate named-subject images with lineage tracking. Discovery, anchor, and follow-on phases preserve identity across views.' },
        { title: '10+ Export Formats', desc: 'Export training data as TRL, LLaVA, Qwen2-VL, JSONL, Parquet, and more via repo-dataset. Classification, preference, and critique units.' },
      ],
    },
    {
      kind: 'code-cards',
      id: 'usage',
      title: 'Usage',
      cards: [
        { title: 'Scaffold', code: '# Create a project from a domain template\nsdlab init my-project --domain character-design\n\n# Validate the project\nsdlab project doctor --project my-project' },
        { title: 'Generate', code: '# Start ComfyUI, then generate a wave\nsdlab generate inputs/prompts/wave1.json --project my-project\nsdlab generate inputs/prompts/wave1.json --project my-project --dry-run' },
        { title: 'Curate + Bind', code: '# Approve or reject with per-dimension scores\nsdlab curate <id> approved "Good proportions" \\\n  --scores proportion_accuracy:0.9 --project my-project\n\n# Bind all records to constitution rules\nsdlab bind --project my-project' },
        { title: 'Export', code: '# Export training data via repo-dataset\nrepo-dataset visual generate ./projects/my-project --format trl\nrepo-dataset visual inspect ./projects/my-project' },
      ],
    },
  ],
};
