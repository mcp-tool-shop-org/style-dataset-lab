/**
 * H1: lib/brief-compiler.js gated subject_mode: 'required' only on the
 * --subject STRING being non-empty (BRIEF_SUBJECT_REQUIRED). resolveSubject()
 * swallows every per-file parse failure (catch {}) and returns [] when
 * nothing matches — a typo'd subject id passed the string check, so nothing
 * downstream ever checked subjectRecords.length. The result: a typo'd
 * subject compiled a brief that reports the typo as Subject:, omits
 * subject_identity / subject_constraints (both gated on length > 0), and is
 * saved as a normal brief — a generic brief wearing a subject label it
 * never actually anchored to.
 *
 * resolveReferences() in the SAME file fails loudly (BRIEF_REF_NOT_FOUND) on
 * the identical "nothing matched" case — this closes the asymmetry by
 * matching that precedent.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { compileBrief } from '../../lib/brief-compiler.js';
import { createTmpProject } from '../lib-dataset/fixtures/make-project.js';

const REQUIRED_SUBJECT_WORKFLOW = {
  workflow_id: 'test-workflow',
  label: 'Test workflow',
  lane_id: 'concept',
  subject_mode: 'required',
  output_mode: 'portrait_set',
  output_count: 4,
  prompt_strategy: { style_prefix: ['test style'], structure: 'style_prefix, subject_identity', must_include: [] },
  negative_strategy: { must_avoid: ['blurry'] },
  canon_focus: [],
  drift_guards: [],
  runtime_defaults: { adapter_target: 'comfyui' },
};

async function writeWorkflowProfile(projectRoot, profile) {
  const dir = join(projectRoot, 'workflows', 'profiles');
  await mkdir(dir, { recursive: true });
  await writeFile(join(dir, `${profile.workflow_id}.json`), JSON.stringify(profile, null, 2));
}

test('H1: compileBrief throws BRIEF_SUBJECT_NOT_FOUND when subject_mode is required but --subject resolves to zero records', async () => {
  const proj = createTmpProject({ records: [] }); // no records exist at all
  try {
    await writeWorkflowProfile(proj.projectRoot, REQUIRED_SUBJECT_WORKFLOW);

    await assert.rejects(
      () => compileBrief({
        projectRoot: proj.projectRoot,
        projectId: 'testproj',
        workflowId: 'test-workflow',
        subjectId: 'kael_marne', // typo — real subject would be kael_maren
      }),
      (err) => {
        assert.equal(err.code, 'BRIEF_SUBJECT_NOT_FOUND');
        assert.match(err.message, /kael_marne/, 'error must name the offending subject id');
        assert.match(err.message, /records/, 'error must name the records directory searched, matching resolveReferences precedent');
        return true;
      }
    );
  } finally {
    proj.cleanup();
  }
});

test('H1: compileBrief succeeds and anchors normally when subject_mode is required AND the subject actually resolves — explicit PASS branch for contrast', async () => {
  const record = {
    id: 'kael_maren_v0',
    schema_version: '2.1.0',
    created_at: '2025-01-01T00:00:00.000Z',
    asset_path: 'inputs/kael_maren_v0.png',
    identity: { subject_id: 'kael_maren', stable_traits: ['scar over left brow'], faction: 'compact' },
    judgment: { status: 'approved', failure_modes: [] },
    canon: { assertion_count: 0, pass_count: 0, assertions: [] },
  };
  const proj = createTmpProject({ records: [record] });
  try {
    await writeWorkflowProfile(proj.projectRoot, REQUIRED_SUBJECT_WORKFLOW);

    const brief = await compileBrief({
      projectRoot: proj.projectRoot,
      projectId: 'testproj',
      workflowId: 'test-workflow',
      subjectId: 'kael_maren',
    });
    assert.equal(brief.subject_id, 'kael_maren');
    assert.ok(brief.subject_constraints?.length > 0, 'a resolved subject should populate subject_constraints');
  } finally {
    proj.cleanup();
  }
});

test('H1: subject_mode "optional" is unaffected by this fix — an unmatched subject does not throw', async () => {
  const optionalWorkflow = { ...REQUIRED_SUBJECT_WORKFLOW, subject_mode: 'optional' };
  const proj = createTmpProject({ records: [] });
  try {
    await writeWorkflowProfile(proj.projectRoot, optionalWorkflow);

    const brief = await compileBrief({
      projectRoot: proj.projectRoot,
      projectId: 'testproj',
      workflowId: 'test-workflow',
      subjectId: 'nonexistent_subject',
    });
    // subject_mode optional: a non-matching subject degrades gracefully,
    // exactly as before this fix — only 'required' mode is stricter now.
    assert.equal(brief.subject_id, 'nonexistent_subject');
  } finally {
    proj.cleanup();
  }
});
