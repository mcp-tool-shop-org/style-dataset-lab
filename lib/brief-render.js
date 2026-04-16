/**
 * Brief renderer — converts compiled brief JSON to human-readable formats.
 */

/**
 * Render a compiled brief as Markdown.
 */
export function renderBriefMarkdown(brief) {
  const lines = [];

  lines.push(`# Brief: ${brief.brief_id}`);
  lines.push('');
  lines.push(`**Workflow:** ${brief.workflow_id}`);
  lines.push(`**Project:** ${brief.project_id}`);
  lines.push(`**Lane:** ${brief.lane_id}`);
  if (brief.subject_id) {
    lines.push(`**Subject:** ${brief.subject_id}`);
  }
  if (brief.training_asset_ref) {
    lines.push(`**Training Asset:** ${brief.training_asset_ref}`);
  }
  if (brief.implementation_pack_ref) {
    lines.push(`**Implementation Pack:** ${brief.implementation_pack_ref}`);
  }
  lines.push('');

  // Prompt
  lines.push('## Prompt');
  lines.push('');
  lines.push('```');
  lines.push(brief.prompt);
  lines.push('```');
  lines.push('');

  // Negative prompt
  lines.push('## Negative Prompt');
  lines.push('');
  lines.push('```');
  lines.push(brief.negative_prompt);
  lines.push('```');
  lines.push('');

  // Canon constraints
  if (brief.canon_constraints?.length > 0) {
    lines.push('## Canon Constraints');
    lines.push('');
    for (const c of brief.canon_constraints) {
      lines.push(`- ${c}`);
    }
    lines.push('');
  }

  // Subject constraints
  if (brief.subject_constraints?.length > 0) {
    lines.push('## Subject Constraints');
    lines.push('');
    for (const c of brief.subject_constraints) {
      lines.push(`- ${c}`);
    }
    lines.push('');
  }

  // Drift warnings
  if (brief.drift_warnings?.length > 0) {
    lines.push('## Drift Warnings');
    lines.push('');
    for (const w of brief.drift_warnings) {
      lines.push(`- ⚠ ${w}`);
    }
    lines.push('');
  }

  // Runtime plan
  lines.push('## Runtime Plan');
  lines.push('');
  lines.push('| Parameter | Value |');
  lines.push('|-----------|-------|');
  const rp = brief.runtime_plan;
  if (rp) {
    lines.push(`| Adapter | ${rp.adapter_target} |`);
    lines.push(`| Width | ${rp.width} |`);
    lines.push(`| Height | ${rp.height} |`);
    lines.push(`| Steps | ${rp.steps} |`);
    lines.push(`| CFG | ${rp.cfg} |`);
    lines.push(`| Sampler | ${rp.sampler} |`);
    lines.push(`| Seed Mode | ${rp.seed_mode} |`);
  }
  lines.push('');

  // Expected outputs
  lines.push('## Expected Outputs');
  lines.push('');
  const eo = brief.expected_outputs;
  if (eo) {
    lines.push(`- **Mode:** ${eo.output_mode}`);
    lines.push(`- **Count:** ${eo.output_count}`);
    if (eo.review_surface) {
      lines.push(`- **Review Surface:** ${eo.review_surface}`);
    }
  }
  lines.push('');

  // Selected references
  if (brief.reference_selection?.length > 0) {
    lines.push('## Selected References');
    lines.push('');
    for (const ref of brief.reference_selection) {
      lines.push(`- **${ref.record_id}** (${ref.role}): ${ref.reason}`);
    }
    lines.push('');
  }

  // Metadata
  lines.push('---');
  lines.push('');
  lines.push(`Compiled: ${brief.compiled_at}`);
  lines.push(`Config fingerprint: \`${brief.config_fingerprint}\``);
  lines.push('');

  return lines.join('\n');
}

/**
 * Render a compiled brief as plain text for terminal output.
 */
export function renderBriefText(brief) {
  const lines = [];

  lines.push(`\x1b[1mBrief: ${brief.brief_id}\x1b[0m`);
  lines.push(`  Workflow:  ${brief.workflow_id}`);
  lines.push(`  Project:   ${brief.project_id}`);
  lines.push(`  Lane:      ${brief.lane_id}`);
  if (brief.subject_id) {
    lines.push(`  Subject:   ${brief.subject_id}`);
  }
  if (brief.training_asset_ref) {
    lines.push(`  Asset:     ${brief.training_asset_ref}`);
  }
  lines.push('');

  lines.push('\x1b[1mPrompt:\x1b[0m');
  lines.push(`  ${brief.prompt}`);
  lines.push('');

  lines.push('\x1b[1mNegative:\x1b[0m');
  lines.push(`  ${brief.negative_prompt}`);
  lines.push('');

  if (brief.canon_constraints?.length > 0) {
    lines.push('\x1b[1mCanon Constraints:\x1b[0m');
    for (const c of brief.canon_constraints) {
      lines.push(`  • ${c}`);
    }
    lines.push('');
  }

  if (brief.subject_constraints?.length > 0) {
    lines.push('\x1b[1mSubject Constraints:\x1b[0m');
    for (const c of brief.subject_constraints) {
      lines.push(`  • ${c}`);
    }
    lines.push('');
  }

  if (brief.drift_warnings?.length > 0) {
    lines.push('\x1b[1mDrift Warnings:\x1b[0m');
    for (const w of brief.drift_warnings) {
      lines.push(`  \x1b[33m⚠\x1b[0m ${w}`);
    }
    lines.push('');
  }

  lines.push('\x1b[1mRuntime Plan:\x1b[0m');
  const rp = brief.runtime_plan;
  if (rp) {
    lines.push(`  Adapter:   ${rp.adapter_target}`);
    lines.push(`  Size:      ${rp.width}×${rp.height}`);
    lines.push(`  Steps:     ${rp.steps}`);
    lines.push(`  CFG:       ${rp.cfg}`);
    lines.push(`  Sampler:   ${rp.sampler}`);
    lines.push(`  Seed mode: ${rp.seed_mode}`);
  }
  lines.push('');

  lines.push('\x1b[1mExpected Outputs:\x1b[0m');
  const eo = brief.expected_outputs;
  if (eo) {
    lines.push(`  Mode:  ${eo.output_mode}`);
    lines.push(`  Count: ${eo.output_count}`);
  }
  lines.push('');

  if (brief.reference_selection?.length > 0) {
    lines.push('\x1b[1mSelected References:\x1b[0m');
    for (const ref of brief.reference_selection) {
      lines.push(`  ${ref.record_id} (${ref.role}) — ${ref.reason}`);
    }
    lines.push('');
  }

  lines.push(`  Compiled:    ${brief.compiled_at}`);
  lines.push(`  Fingerprint: ${brief.config_fingerprint}`);

  return lines.join('\n');
}
