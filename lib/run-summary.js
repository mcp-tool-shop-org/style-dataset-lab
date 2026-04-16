/**
 * Run summary — render manifest to human-readable summary files.
 *
 * Writes summary.md + summary.json to the run directory.
 * Contact sheet generation is separate (requires image processing).
 */

import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';

/**
 * Build a summary object from a manifest.
 */
export function buildRunSummary(manifest) {
  const ok = manifest.outputs.filter(o => o.status === 'ok');
  const failed = manifest.outputs.filter(o => o.status === 'error');
  const totalElapsed = ok.reduce((sum, o) => sum + (o.elapsed_ms || 0), 0);

  return {
    run_id: manifest.run_id,
    brief_id: manifest.brief_id,
    project_id: manifest.project_id,
    adapter_target: manifest.adapter_target,
    output_mode: manifest.output_mode,
    created_at: manifest.created_at,
    dry_run: manifest.dry_run,
    success_count: manifest.success_count,
    error_count: manifest.error_count,
    total_outputs: manifest.output_count,
    total_elapsed_ms: totalElapsed,
    avg_elapsed_ms: ok.length > 0 ? Math.round(totalElapsed / ok.length) : 0,
    seed_plan: manifest.seed_plan,
    checkpoint: manifest.checkpoint,
  };
}

/**
 * Render a manifest to Markdown summary.
 */
export function renderRunMarkdown(manifest) {
  const lines = [];
  lines.push(`# Run: ${manifest.run_id}`);
  lines.push('');
  lines.push(`**Brief:** ${manifest.brief_id}`);
  lines.push(`**Project:** ${manifest.project_id}`);
  lines.push(`**Created:** ${manifest.created_at}`);
  lines.push(`**Adapter:** ${manifest.adapter_target}`);
  lines.push(`**Mode:** ${manifest.output_mode}`);
  if (manifest.dry_run) lines.push('**⚠ DRY RUN — no images generated**');
  lines.push('');

  // Results
  lines.push('## Results');
  lines.push('');
  lines.push(`| # | Seed | Status | File | Time |`);
  lines.push(`|---|------|--------|------|------|`);
  for (const out of manifest.outputs) {
    const file = out.filename || '—';
    const time = out.elapsed_ms ? `${(out.elapsed_ms / 1000).toFixed(1)}s` : '—';
    const status = out.status === 'ok' ? '✓' : out.status === 'dry_run' ? '○' : '✗';
    lines.push(`| ${out.index + 1} | ${out.seed} | ${status} | ${file} | ${time} |`);
  }
  lines.push('');

  // Errors
  if (manifest.errors.length > 0) {
    lines.push('## Errors');
    lines.push('');
    for (const err of manifest.errors) {
      lines.push(`- **Image ${err.index + 1}** (seed ${err.seed}): ${err.error}`);
    }
    lines.push('');
  }

  // Runtime
  lines.push('## Runtime');
  lines.push('');
  lines.push(`| Parameter | Value |`);
  lines.push(`|-----------|-------|`);
  lines.push(`| Checkpoint | ${manifest.checkpoint || '—'} |`);
  lines.push(`| LoRAs | ${(manifest.loras || []).map(l => l.name).join(', ') || '—'} |`);
  lines.push(`| ComfyUI | ${manifest.comfy_url || '—'} |`);

  const rp = manifest.runtime_plan || {};
  lines.push(`| Size | ${rp.width || '?'}×${rp.height || '?'} |`);
  lines.push(`| Steps | ${rp.steps || '?'} |`);
  lines.push(`| CFG | ${rp.cfg || '?'} |`);
  lines.push(`| Sampler | ${rp.sampler || '?'} |`);
  lines.push(`| Seed mode | ${rp.seed_mode || '?'} |`);
  lines.push(`| Base seed | ${manifest.seed_plan?.base_seed || '?'} |`);
  lines.push('');

  return lines.join('\n');
}

/**
 * Render a manifest to terminal text.
 */
export function renderRunText(manifest) {
  const ok = manifest.outputs.filter(o => o.status === 'ok' || o.status === 'dry_run');
  const failed = manifest.outputs.filter(o => o.status === 'error');
  const lines = [];

  lines.push(`Run: ${manifest.run_id}`);
  lines.push(`Brief: ${manifest.brief_id}`);
  lines.push(`Project: ${manifest.project_id}`);
  lines.push(`Mode: ${manifest.output_mode} (${manifest.adapter_target})`);
  if (manifest.dry_run) lines.push('⚠ DRY RUN');
  lines.push(`Results: ${ok.length}/${manifest.output_count} succeeded`);
  if (failed.length > 0) lines.push(`Errors: ${failed.length}`);
  lines.push('');

  for (const out of manifest.outputs) {
    const status = out.status === 'ok' ? '✓' : out.status === 'dry_run' ? '○' : '✗';
    const time = out.elapsed_ms ? ` (${(out.elapsed_ms / 1000).toFixed(1)}s)` : '';
    const file = out.filename ? ` → ${out.filename}` : '';
    const err = out.error ? ` — ${out.error}` : '';
    lines.push(`  ${status} [${out.index + 1}] seed ${out.seed}${file}${time}${err}`);
  }

  return lines.join('\n');
}

/**
 * Save summary files into the run directory.
 */
export async function saveRunSummary(runDir, manifest) {
  const summary = buildRunSummary(manifest);
  await writeFile(join(runDir, 'summary.json'), JSON.stringify(summary, null, 2) + '\n');
  await writeFile(join(runDir, 'summary.md'), renderRunMarkdown(manifest) + '\n');
}
