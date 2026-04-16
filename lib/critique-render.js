/**
 * Critique renderer — converts critique report to human-readable formats.
 *
 * Reads like a working note, not a report card.
 */

// ─── Fit badge ───────────────────────────────────────────────────

const FIT_BADGES = {
  strong: '✓ strong',
  usable: '○ usable',
  'off-model': '✗ off-model',
};

const FIT_EMOJI = {
  strong: '🟢',
  usable: '🟡',
  'off-model': '🔴',
};

// ─── Markdown renderer ──────────────────────────────────────────

/**
 * Render a critique report as Markdown.
 */
export function renderCritiqueMarkdown(report) {
  const lines = [];

  lines.push(`# Critique: ${report.run_id}`);
  lines.push('');
  lines.push(`**Brief:** ${report.brief_id}`);
  lines.push(`**Workflow:** ${report.workflow_id}`);
  lines.push(`**Project:** ${report.project_id}`);
  if (report.subject_id) lines.push(`**Subject:** ${report.subject_id}`);
  lines.push(`**Created:** ${report.created_at}`);
  lines.push('');

  // Recommended action
  const action = report.recommended_action;
  const modeLabel = {
    accept_one: '✓ Accept one candidate',
    refine_from_one: '→ Refine from one candidate',
    rerun_broader: '↻ Rerun with broader parameters',
    discard_run: '✗ Discard this run',
  };
  lines.push('## Recommended Action');
  lines.push('');
  lines.push(`**${modeLabel[action.mode] || action.mode}**`);
  if (action.preferred_candidate) {
    lines.push(`Preferred: **${action.preferred_candidate}**`);
  }
  if (action.reason) lines.push(`Reason: ${action.reason}`);
  lines.push('');

  // Active dimensions
  lines.push('## Active Dimensions');
  lines.push('');
  for (const dim of report.active_dimensions) {
    lines.push(`- ${dim.replace(/_/g, ' ')}`);
  }
  lines.push('');

  // Candidates
  lines.push('## Candidates');
  lines.push('');

  for (const c of report.candidates) {
    const badge = FIT_EMOJI[c.overall_fit] || '?';
    lines.push(`### ${badge} ${c.filename} (seed: ${c.seed ?? '?'})`);
    lines.push('');
    lines.push(`**Fit:** ${c.overall_fit}`);
    lines.push('');

    if (c.strengths.length > 0) {
      lines.push('**Strengths:**');
      for (const s of c.strengths) lines.push(`- ${s}`);
      lines.push('');
    }

    if (c.drift_issues.length > 0) {
      lines.push('**Drift Issues:**');
      for (const d of c.drift_issues) lines.push(`- ⚠ ${d}`);
      lines.push('');
    }

    if (c.preserve_next_pass.length > 0) {
      lines.push('**Preserve Next Pass:**');
      for (const p of c.preserve_next_pass) lines.push(`- ✓ ${p}`);
      lines.push('');
    }

    if (c.correct_next_pass.length > 0) {
      lines.push('**Correct Next Pass:**');
      for (const x of c.correct_next_pass) lines.push(`- → ${x}`);
      lines.push('');
    }
  }

  // Next-pass direction summary
  lines.push('## Next-Pass Direction');
  lines.push('');

  // Aggregate preserve/correct across all candidates
  const allPreserve = new Set();
  const allCorrect = new Set();
  for (const c of report.candidates) {
    for (const p of c.preserve_next_pass) allPreserve.add(p);
    for (const x of c.correct_next_pass) allCorrect.add(x);
  }

  if (allPreserve.size > 0) {
    lines.push('**Preserve:**');
    for (const p of allPreserve) lines.push(`- ${p}`);
    lines.push('');
  }

  if (allCorrect.size > 0) {
    lines.push('**Correct:**');
    for (const x of allCorrect) lines.push(`- ${x}`);
    lines.push('');
  }

  return lines.join('\n');
}

// ─── Terminal text renderer ──────────────────────────────────────

/**
 * Render a critique report as plain text for terminal display.
 */
export function renderCritiqueText(report) {
  const lines = [];

  lines.push(`Critique: ${report.run_id}`);
  lines.push(`Brief: ${report.brief_id}  Workflow: ${report.workflow_id}`);
  if (report.subject_id) lines.push(`Subject: ${report.subject_id}`);
  lines.push('');

  // Action
  const action = report.recommended_action;
  const actionIcon = {
    accept_one: '✓',
    refine_from_one: '→',
    rerun_broader: '↻',
    discard_run: '✗',
  };
  lines.push(`${actionIcon[action.mode] || '?'} ${action.mode.replace(/_/g, ' ')}`);
  if (action.preferred_candidate) lines.push(`  Preferred: ${action.preferred_candidate}`);
  if (action.reason) lines.push(`  ${action.reason}`);
  lines.push('');

  // Dimensions
  lines.push(`Dimensions: ${report.active_dimensions.map(d => d.replace(/_/g, ' ')).join(', ')}`);
  lines.push('');

  // Candidates
  for (const c of report.candidates) {
    const badge = FIT_BADGES[c.overall_fit] || '? unknown';
    lines.push(`  ${badge}  ${c.filename} (seed: ${c.seed ?? '?'})`);

    if (c.strengths.length > 0) {
      lines.push(`    strengths: ${c.strengths.slice(0, 3).join('; ')}`);
    }
    if (c.drift_issues.length > 0) {
      lines.push(`    drift: ${c.drift_issues.slice(0, 3).join('; ')}`);
    }
  }
  lines.push('');

  return lines.join('\n');
}
