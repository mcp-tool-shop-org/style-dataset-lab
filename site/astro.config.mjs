// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  site: 'https://mcp-tool-shop-org.github.io',
  base: '/style-dataset-lab',
  integrations: [
    starlight({
      title: 'style-dataset-lab',
      description: 'Visual dataset factory — generate, curate, and export multimodal training data for VLM fine-tuning',
      disable404Route: true,
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/mcp-tool-shop-org/style-dataset-lab' },
      ],
      // Explicit sidebar (was autogenerate) so the case studies land in their
      // own "Proven in production" group instead of the flat Handbook list.
      // Handbook pages listed by slug in reading order; labels come from each
      // page's own title. New handbook pages must be added here by hand.
      sidebar: [
        {
          label: 'Handbook',
          items: [
            { slug: 'handbook' },
            { slug: 'handbook/getting-started' },
            { slug: 'handbook/dataset-workflow' },
            { slug: 'handbook/reference' },
            { slug: 'handbook/architecture' },
            { slug: 'handbook/production-loop' },
            { slug: 'handbook/security' },
            { slug: 'handbook/two-lora-stacking' },
            { slug: 'handbook/canon-build' },
            { slug: 'handbook/canon-freeze' },
          ],
        },
        {
          label: 'Proven in production',
          items: [
            { slug: 'handbook/case-study-tallow-fen' },
            { slug: 'handbook/case-study-rustline' },
          ],
        },
      ],
      customCss: ['./src/styles/starlight-custom.css'],
    }),
  ],
  vite: {
    plugins: [tailwindcss()],
  },
});
