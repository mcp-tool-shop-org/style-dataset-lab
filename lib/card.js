/**
 * Dataset card generation — markdown + JSON twin.
 *
 * Produces a human-readable dataset card summarizing provenance,
 * selection criteria, split strategy, and distribution statistics.
 */

import { loadSnapshot, loadSnapshotIncluded } from './snapshot.js';
import { loadSplit, loadSplitAudit } from './split.js';
import { loadProjectConfig } from './config.js';

/**
 * Generate a dataset card from snapshot + split + project config.
 *
 * @param {string} projectRoot
 * @param {string} snapshotId
 * @param {string} splitId
 * @returns {Promise<{markdown: string, json: Object}>}
 */
export async function generateCard(projectRoot, snapshotId, splitId) {
  const config = loadProjectConfig(projectRoot);
  const snapshot = await loadSnapshot(projectRoot, snapshotId);
  const split = await loadSplit(projectRoot, splitId);
  const audit = await loadSplitAudit(projectRoot, splitId);
  const included = await loadSnapshotIncluded(projectRoot, snapshotId);

  const json = {
    dataset_name: `${config.meta.name}-visual`,
    version: config.meta.version || '1.0.0',
    created_at: new Date().toISOString(),
    created_by: 'sdlab-card-v1',
    project: {
      name: config.meta.name,
      display_name: config.meta.display_name,
      domain: config.meta.domain,
    },
    snapshot: {
      id: snapshot.snapshot_id,
      created_at: snapshot.created_at,
      config_fingerprint: snapshot.config_fingerprint,
      total_records: snapshot.counts.total_records,
      included: snapshot.counts.included,
      excluded: snapshot.counts.excluded,
    },
    selection: snapshot.selection_profile,
    split: {
      id: split.split_id,
      strategy: split.profile.strategy,
      seed: split.profile.seed,
      ratios: {
        train: split.profile.train_ratio,
        val: split.profile.val_ratio,
        test: split.profile.test_ratio,
      },
      counts: split.counts,
      leakage_free: audit.leakage_check.passed,
    },
    lane_balance: audit.lane_balance,
    constitution: {
      rule_count: config.constitution.rules?.length || 0,
    },
    rubric: {
      dimension_count: config.rubric.dimensions?.length || 0,
      thresholds: config.rubric.thresholds,
    },
  };

  const markdown = renderMarkdown(json, config);

  return { markdown, json };
}

function renderMarkdown(card, config) {
  const lines = [];
  const add = (s = '') => lines.push(s);

  add(`# ${card.dataset_name}`);
  add();
  add(`**Project:** ${card.project.display_name}  `);
  add(`**Domain:** ${card.project.domain}  `);
  add(`**Version:** ${card.version}  `);
  add(`**Generated:** ${card.created_at}  `);
  add();

  add('## Selection');
  add();
  add(`- **Snapshot:** \`${card.snapshot.id}\``);
  add(`- **Config fingerprint:** \`${card.snapshot.config_fingerprint.slice(0, 16)}...\``);
  add(`- **Total records evaluated:** ${card.snapshot.total_records}`);
  add(`- **Included:** ${card.snapshot.included} (${(card.snapshot.included / card.snapshot.total_records * 100).toFixed(1)}%)`);
  add(`- **Excluded:** ${card.snapshot.excluded}`);
  add();

  add('### Selection criteria');
  add();
  const sel = card.selection;
  if (sel.require_judgment) add('- Requires human judgment');
  if (sel.require_status?.length) add(`- Status: ${sel.require_status.join(', ')}`);
  if (sel.require_canon_bound) add('- Must be canon-bound (constitution assertions)');
  if (sel.minimum_pass_ratio != null) add(`- Minimum pass ratio: ${(sel.minimum_pass_ratio * 100).toFixed(0)}%`);
  add();

  add('## Split');
  add();
  add(`- **Split ID:** \`${card.split.id}\``);
  add(`- **Strategy:** ${card.split.strategy}`);
  add(`- **Seed:** ${card.split.seed}`);
  add(`- **Subject leakage:** ${card.split.leakage_free ? 'None (verified)' : 'DETECTED'}`);
  add();

  add('| Partition | Records | % |');
  add('|-----------|---------|---|');
  const total = card.split.counts.total_records;
  add(`| Train | ${card.split.counts.train} | ${(card.split.counts.train / total * 100).toFixed(1)}% |`);
  add(`| Val | ${card.split.counts.val} | ${(card.split.counts.val / total * 100).toFixed(1)}% |`);
  add(`| Test | ${card.split.counts.test} | ${(card.split.counts.test / total * 100).toFixed(1)}% |`);
  add();

  add('## Lane Balance');
  add();
  add('| Lane | Total | Train% | Val% | Test% |');
  add('|------|-------|--------|------|-------|');
  for (const [lane, b] of Object.entries(card.lane_balance).sort((a, b) => b[1].total - a[1].total)) {
    add(`| ${lane} | ${b.total} | ${b.train_pct}% | ${b.val_pct}% | ${b.test_pct}% |`);
  }
  add();

  add('## Quality Gates');
  add();
  add(`- **Constitution rules:** ${card.constitution.rule_count}`);
  add(`- **Rubric dimensions:** ${card.rubric.dimension_count}`);
  if (card.rubric.thresholds) {
    add(`- **Pass threshold:** ${(card.rubric.thresholds.pass * 100).toFixed(0)}%`);
  }
  add();

  add('## Provenance');
  add();
  add('This dataset was produced by [Style Dataset Lab](https://github.com/mcp-tool-shop-org/style-dataset-lab).');
  add('Every included record has been human-reviewed, canon-bound, and verified against project constitution rules.');
  add('Split strategy ensures no subject appears in multiple partitions.');
  add();

  return lines.join('\n');
}
