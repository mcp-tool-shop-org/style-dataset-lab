import type { SiteConfig } from '@mcptoolshop/site-theme';

export const config: SiteConfig = {
  title: 'Style Dataset Lab',
  description: 'A style constitution for your AI art pipeline. Write rules, generate art, curate against those rules, and produce versioned training datasets with a receipt at every step.',
  logoBadge: 'SD',
  brandName: 'style-dataset-lab',
  repoUrl: 'https://github.com/mcp-tool-shop-org/style-dataset-lab',
  footerText: 'MIT Licensed — built by <a href="https://github.com/mcp-tool-shop-org" style="color:var(--color-muted);text-decoration:underline">mcp-tool-shop-org</a>',

  hero: {
    badge: 'v2.2.0',
    headline: 'Style Dataset Lab',
    headlineAccent: 'A style constitution for your AI art pipeline.',
    description: 'Write down what your project looks like. Generate concept art against those rules. Curate the results. Turn approved work into versioned, auditable datasets with leakage-safe splits, training packages, eval scorecards, and a closed re-ingest loop. Every record carries provenance, judgment, and canon binding. Not labels. Reasons.',
    primaryCta: { href: '#how-it-works', label: 'See how it works' },
    secondaryCta: { href: 'handbook/', label: 'Read the Handbook' },
    previews: [
      { label: 'Start', code: 'npm install -g @mcptoolshop/style-dataset-lab\nsdlab init my-project --domain character-design' },
      { label: 'Curate', code: 'sdlab generate inputs/prompts/wave1.json\nsdlab curate <id> approved "Strong silhouette"\nsdlab bind --project my-project' },
      { label: 'Ship', code: 'sdlab snapshot create && sdlab split build\nsdlab export build\nsdlab training-package build\nsdlab eval-run score <id> --outputs results.jsonl' },
    ],
  },

  sections: [
    {
      kind: 'features',
      id: 'how-it-works',
      title: 'How it works',
      subtitle: 'Written canon becomes generated art becomes auditable datasets becomes trained model assets. The whole loop.',
      features: [
        { title: 'Write the rules', desc: 'Define your style constitution: what passes, what fails, and why. Per-dimension scoring rubrics, subject lanes, faction vocabulary. Five domain templates ship with production-grade rules.' },
        { title: 'Generate and curate', desc: 'Generate concept art via ComfyUI with full provenance tracking. Review every image against your rubric. Approve, reject, or mark borderline with per-dimension scores.' },
        { title: 'Bind to canon', desc: 'Every approved asset is bound to the specific constitution rules it satisfies. Not a tag. A graded, traceable verdict with rationale.' },
        { title: 'Freeze versioned datasets', desc: 'Frozen snapshots with config fingerprints. Leakage-safe splits where subject families never cross partition boundaries. Self-contained export packages with checksums.' },
        { title: 'Build training packages', desc: 'Manifest-bound, adapter-driven packages for specific trainers. Ships with generic-image-caption and diffusers-lora. Adapters transform layout but never mutate truth.' },
        { title: 'Score and close the loop', desc: 'Eval scorecards verify generated outputs against canon-aware tasks. Accepted outputs re-enter through normal review. The loop closes and the dataset grows.' },
      ],
    },
    {
      kind: 'code-cards',
      id: 'usage',
      title: 'The pipeline',
      cards: [
        { title: 'Define canon', code: '# Scaffold from a domain template\nsdlab init my-project --domain game-art\n\n# Validate the project\nsdlab project doctor --project my-project\n\n# 5 config files define all rules:\n# constitution.json, lanes.json,\n# rubric.json, terminology.json,\n# project.json' },
        { title: 'Curate + bind', code: '# Generate and review\nsdlab curate <id> approved \\\n  "Correct palette, strong silhouette"\n\n# Bind approved work to constitution\nsdlab bind --project my-project\n\n# Every record now carries:\n# provenance + judgment + canon binding' },
        { title: 'Produce datasets', code: '# Freeze, split, and package\nsdlab snapshot create --project my-project\nsdlab split build   # zero subject leakage\nsdlab export build  # manifest + checksums\nsdlab card generate # dataset card (md + json)' },
        { title: 'Train + eval', code: '# Build a training package\nsdlab training-manifest create \\\n  --profile character-style-lora\nsdlab training-package build\n\n# Score outputs, reingest accepted work\nsdlab eval-run score <id> --outputs results.jsonl\nsdlab reingest generated --source ./outputs' },
      ],
    },
  ],
};
