import type { SiteConfig } from '@mcptoolshop/site-theme';

export const config: SiteConfig = {
  title: 'Style Dataset Lab',
  description: 'Build canon-aligned datasets, train reusable style assets, and put them to work in real production workflows. Write rules, generate art, curate against those rules, and produce versioned training datasets — then compile briefs, run production, select winners, and feed them back.',
  logoBadge: 'SD',
  brandName: 'style-dataset-lab',
  repoUrl: 'https://github.com/mcp-tool-shop-org/style-dataset-lab',
  footerText: 'MIT Licensed — built by <a href="https://github.com/mcp-tool-shop-org" style="color:var(--color-muted);text-decoration:underline">mcp-tool-shop-org</a>',

  hero: {
    badge: 'v3.0.0',
    headline: 'Style Dataset Lab',
    headlineAccent: 'Build canon-aligned datasets, train style assets, and put them to work.',
    description: 'Define your visual canon. Generate concept art against those rules. Curate, bind, and package versioned datasets. Then compile production briefs, run them through ComfyUI, critique and batch-produce real work surfaces, select the best results, and re-ingest them into your corpus. Every record carries provenance, judgment, and canon binding. The full loop closes.',
    primaryCta: { href: '#how-it-works', label: 'See how it works' },
    secondaryCta: { href: 'handbook/', label: 'Read the Handbook' },
    previews: [
      { label: 'Start', code: 'npm install -g @mcptoolshop/style-dataset-lab\nsdlab init my-project --domain character-design' },
      { label: 'Dataset', code: 'sdlab generate inputs/prompts/wave1.json\nsdlab curate <id> approved "Strong silhouette"\nsdlab bind && sdlab snapshot create\nsdlab split build && sdlab export build' },
      { label: 'Produce', code: 'sdlab brief compile --workflow character-portrait-set\nsdlab run generate --brief brief_001\nsdlab critique --run run_001\nsdlab batch generate --mode expression-sheet' },
      { label: 'Close the loop', code: 'sdlab select --run run_001 --approve 001.png,003.png\nsdlab reingest selected --selection sel_001\nsdlab curate gen_sel_001_001 approved "Keeper"' },
    ],
  },

  sections: [
    {
      kind: 'features',
      id: 'how-it-works',
      title: 'How it works',
      subtitle: 'Define canon. Build datasets. Train models. Compile briefs. Run production. Critique and batch-produce. Select winners. Feed them back. The whole loop.',
      features: [
        { title: 'Write the rules', desc: 'Define your style constitution: what passes, what fails, and why. Per-dimension scoring rubrics, subject lanes, faction vocabulary. Five domain templates ship with production-grade rules.' },
        { title: 'Generate and curate', desc: 'Generate concept art via ComfyUI with full provenance tracking. Review every image against your rubric. Approve, reject, or mark borderline with per-dimension scores.' },
        { title: 'Bind to canon', desc: 'Every approved asset is bound to the specific constitution rules it satisfies. Not a tag. A graded, traceable verdict with rationale.' },
        { title: 'Freeze versioned datasets', desc: 'Frozen snapshots with config fingerprints. Leakage-safe splits where subject families never cross partition boundaries. Self-contained export packages with checksums.' },
        { title: 'Build training packages', desc: 'Manifest-bound, adapter-driven packages for specific trainers. Ships with generic-image-caption and diffusers-lora. Adapters transform layout but never mutate truth.' },
        { title: 'Run production workflows', desc: 'Compile generation briefs from project truth. Execute through ComfyUI. Critique runs, refine briefs, batch-produce expression sheets and environment boards.' },
        { title: 'Select and re-ingest', desc: 'Choose the best outputs. Selected work returns as candidate records with full generation provenance. Same review, same binding, same standards. The corpus grows.' },
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
        { title: 'Production loop', code: '# Compile brief, run, batch-produce\nsdlab brief compile --workflow portrait-set\nsdlab run generate --brief brief_001\nsdlab batch generate --mode expression-sheet\n\n# Select winners, re-ingest\nsdlab select --run run_001 --approve 001.png\nsdlab reingest selected --selection sel_001' },
      ],
    },
  ],
};
