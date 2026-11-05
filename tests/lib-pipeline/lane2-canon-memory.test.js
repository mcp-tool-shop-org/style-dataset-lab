import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtempSync, rmSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

import {
  GLIMMER_DEFAULT_MODEL,
  MIN_LLAMA_SERVER_BUILD,
  assertLoopbackEndpoint,
  verifyGlimmerRuntime,
  draftCanonClassViaEndpoint,
  writePromptsJsonl,
  readPromptsJsonl,
} from '../../lib/canon-author.js';

import {
  ratifyCanonDraft,
  assertDirectorRatifiedForFreeze,
  assertNoSelfVerification,
} from '../../lib/canon-review-gate.js';

import {
  MEMORY_SCOPES,
  MEMORY_KINDS,
  MEMORY_STATUSES,
  ALLOWED_FAILURE_MODES,
  appendMemoryEntry,
  approveProposedMemoryEntry,
  promoteProjectMemoryToGlobal,
  loadEffectiveMemory,
  writeMemorySnapshot,
  diffMemorySnapshots,
  recordVisionVerdict,
} from '../../lib/memory-store.js';

const FAKE_SHA_A = 'sha256:' + 'a'.repeat(64);
const FAKE_SHA_B = 'sha256:' + 'b'.repeat(64);
const FAKE_SHA_C = 'sha256:' + 'c'.repeat(64);

function startFakeGlimmerServer() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      if (req.method === 'POST' && req.url === '/v1/chat/completions') {
        let body = '';
        req.on('data', (chunk) => {
          body += chunk;
        });
        req.on('end', () => {
          const parsed = JSON.parse(body);
          const replyPayload = {
            class_id: 'cargo_barge',
            canon_entry_draft: {
              id: 'cargo_barge',
              title: 'Coastal Cargo Barge',
              silhouette_cue: 'Broad low-freeboard hull with twin cargo hatches',
              material_palette: ['weathered oak', 'tarred hemp', 'salt-stained iron'],
            },
            prompt:
              'coastal cargo barge, broad low-freeboard hull, weathered oak planks, twin hatches, studio orthographic plate',
            negative_prompt: 'photorealistic lens flare, watermark, signature, modern steel container',
            model_echo_messages: parsed.messages?.length || 0,
          };
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(
            JSON.stringify({
              id: 'chatcmpl-stub-01',
              model: GLIMMER_DEFAULT_MODEL.name,
              choices: [
                {
                  index: 0,
                  message: {
                    role: 'assistant',
                    content: JSON.stringify(replyPayload),
                  },
                },
              ],
            })
          );
        });
        return;
      }
      res.writeHead(404);
      res.end();
    });
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address();
      resolve({
        server,
        endpoint: `http://127.0.0.1:${addr.port}/v1/chat/completions`,
      });
    });
  });
}

describe('Part C — Lane 2 canon authoring, review gate, and persistent memory store (G10, G11, §11, §12)', () => {
  it('G10 & §9.2 item 7: enforces loopback-only endpoint and llama-server >= b10353 + mmproj pre-check', () => {
    const url = assertLoopbackEndpoint('http://127.0.0.1:8080/v1/chat/completions');
    assert.equal(url.hostname, '127.0.0.1');

    assert.throws(
      () => assertLoopbackEndpoint('http://0.0.0.0:8080/v1/chat/completions'),
      /LANE2_NON_LOOPBACK_ENDPOINT/
    );
    assert.throws(
      () => assertLoopbackEndpoint('https://api.example.com/v1/chat/completions'),
      /LANE2_NON_LOOPBACK_ENDPOINT/
    );

    // llama-server build >= b10353 required for Qwen3.5 / Muse-Glimmer-30B-A3B
    assert.equal(MIN_LLAMA_SERVER_BUILD, 10353);
    assert.throws(
      () => verifyGlimmerRuntime({ llamaServerBuild: 'b10200', vision: false }),
      /LANE2_LLAMA_SERVER_TOO_OLD/
    );

    const okTextOnly = verifyGlimmerRuntime({ llamaServerBuild: 'b10353', vision: false });
    assert.equal(okTextOnly.buildNumber, 10353);

    // Vision mode requires mmproj + sha256
    assert.throws(
      () => verifyGlimmerRuntime({ llamaServerBuild: 'b10400', vision: true }),
      /LANE2_MMPROJ_MISSING/
    );
    const okVision = verifyGlimmerRuntime({
      llamaServerBuild: 'b10400',
      vision: true,
      mmprojPath: '/tmp/mmproj-F16.gguf',
      mmprojSha256: FAKE_SHA_A,
      verifyFiles: false,
    });
    assert.equal(okVision.vision, true);
    assert.equal(okVision.mmprojSha256, FAKE_SHA_A);
  });

  it('G10 & G11: drafts canon class via loopback server with status="draft" and judgment=null, refuses freeze until Director ratifies', async () => {
    const tmp = mkdtempSync(join(tmpdir(), 'sdlab-lane2-draft-'));
    const { server, endpoint } = await startFakeGlimmerServer();
    try {
      const draft = await draftCanonClassViaEndpoint({
        endpoint,
        classId: 'cargo_barge',
        brief: 'Draft visual canon entry and prompt for coastal cargo barge class.',
        canonContext: { style: 'orthographic timber vessel plate' },
      });

      assert.equal(draft.class_id, 'cargo_barge');
      assert.equal(draft.status, 'draft');
      assert.equal(draft.judgment, null);
      assert.equal(draft.author_model.licence_id, 'Apache-2.0');
      assert.match(draft.messages_sha256, /^sha256:[0-9a-f]{64}$/);
      assert.match(draft.draft_sha256, /^sha256:[0-9a-f]{64}$/);
      assert.ok(draft.author_model.credit_note.includes('Muse-Glimmer-30B-A3B'));

      const promptsPath = join(tmp, 'prompts.jsonl');
      const written = writePromptsJsonl(promptsPath, [draft]);
      assert.ok(existsSync(written.sha256Path));
      const loaded = readPromptsJsonl(promptsPath);
      assert.equal(loaded.length, 1);
      assert.equal(loaded[0].status, 'draft');
      assert.equal(loaded[0].judgment, null);

      // Gate refuses to freeze while status === 'draft'
      assert.throws(
        () => assertDirectorRatifiedForFreeze(draft),
        /CANON_DRAFT_UNRATIFIED/
      );

      // Model cannot self-approve a draft
      assert.throws(
        () =>
          ratifyCanonDraft({
            draft,
            approver: 'model:glimmer@' + FAKE_SHA_A,
            reason: 'Self-approved by model',
          }),
        /CANON_SELF_APPROVAL_FORBIDDEN/
      );

      // Director ratifies with explicit accept + reason + matching draft_sha256
      const ratified = ratifyCanonDraft({
        draft,
        approver: 'human:director',
        reason: 'Approved coastal cargo barge silhouette and material cues',
        at: '2026-11-05T11:30:00Z',
      });
      assert.equal(ratified.status, 'ratified');
      assert.equal(ratified.ratification.approver, 'human:director');
      assert.equal(ratified.ratification.draft_sha256, draft.draft_sha256);

      // Tampering with the prompt after ratification invalidates the ratification hash
      const tampered = { ...ratified, prompt: 'tampered prompt' };
      assert.throws(
        () => assertDirectorRatifiedForFreeze(tampered),
        /CANON_DRAFT_SHA_MISMATCH/
      );

      // Untampered ratified draft passes the freeze gate
      const gateOk = assertDirectorRatifiedForFreeze(ratified);
      assert.equal(gateOk.ok, true);
    } finally {
      server.close();
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  it('§12.6: enforces self-verification ban (Glimmer cannot be the deciding reader of a canon entry or prompt it wrote)', () => {
    assert.throws(
      () =>
        assertNoSelfVerification({
          authorModel: 'Muse-Glimmer-30B-A3B-Q4_K_M.gguf',
          verifierModel: 'Muse-Glimmer-30B-A3B-Q4_K_M.gguf',
          context: 'canon entry cargo_barge',
        }),
      /SELF_VERIFICATION_FORBIDDEN/
    );

    assert.throws(
      () =>
        assertNoSelfVerification({
          authorModel: 'model:glimmer@sha256:' + 'a'.repeat(64),
          verifierModel: 'Muse-Glimmer-30B-A3B',
          context: 'prompt cargo_barge',
        }),
      /SELF_VERIFICATION_FORBIDDEN/
    );

    // Cross-family or human verifier is allowed
    const okHuman = assertNoSelfVerification({
      authorModel: 'Muse-Glimmer-30B-A3B-Q4_K_M.gguf',
      verifierModel: 'human:director',
      context: 'canon entry cargo_barge',
    });
    assert.equal(okHuman.ok, true);

    const okCross = assertNoSelfVerification({
      authorModel: 'human:director',
      verifierModel: 'Muse-Glimmer-30B-A3B-Q4_K_M.gguf',
      context: 'render inspection',
    });
    assert.equal(okCross.ok, true);
  });

  it('§12.1–§12.4: persistent memory store enforces global->project precedence, explicit override only, no cross-talk, promotion, proposed->active, and sealed holdout guard', () => {
    const tmp = mkdtempSync(join(tmpdir(), 'sdlab-lane2-mem-'));
    try {
      assert.ok(MEMORY_SCOPES.includes('global'));
      assert.ok(MEMORY_KINDS.includes('rule'));
      assert.ok(MEMORY_STATUSES.includes('proposed'));

      // 1. Add active global rule by Director
      const globalRule = appendMemoryEntry({
        rootDir: tmp,
        entry: {
          id: 'mem_global_001',
          scope: 'global',
          project: null,
          kind: 'rule',
          rule_key: 'lighting.glare',
          status: 'active',
          statement: 'Never allow blown-out specular lens flare on hull plates.',
          evidence_refs: ['canon:lighting_v1'],
          author: 'human:director',
          approver: 'human:director',
          overrides: null,
          superseded_by: null,
          reason: 'Core studio lighting rule',
        },
      });
      assert.equal(globalRule.status, 'active');

      // 2. Model-authored entry cannot be written directly as active
      assert.throws(
        () =>
          appendMemoryEntry({
            rootDir: tmp,
            entry: {
              id: 'mem_proj_bad_active',
              scope: 'project',
              project: 'portlight-ships',
              kind: 'failure_example',
              status: 'active',
              statement: 'Wake foam must not clip hull timber.',
              evidence_refs: ['run:run_01'],
              author: 'model:glimmer@' + FAKE_SHA_A,
              approver: 'human:director',
            },
          }),
        /MEMORY_MODEL_ACTIVE_FORBIDDEN/
      );

      // 3. Sealed holdout guard: refuses any proposal citing a sealed holdout id
      assert.throws(
        () =>
          appendMemoryEntry({
            rootDir: tmp,
            sealedHoldoutIds: ['holdout_ship_099'],
            entry: {
              id: 'mem_proj_holdout_leak',
              scope: 'project',
              project: 'portlight-ships',
              kind: 'failure_example',
              status: 'proposed',
              statement: 'Observed rigging drift on holdout_ship_099.',
              evidence_refs: ['record:holdout_ship_099'],
              author: 'model:glimmer@' + FAKE_SHA_A,
              approver: null,
            },
          }),
        /MEMORY_HOLDOUT_CITATION_FORBIDDEN/
      );

      // 4. Model proposes a valid project entry (status: "proposed", approver: null)
      const proposed = appendMemoryEntry({
        rootDir: tmp,
        sealedHoldoutIds: ['holdout_ship_099'],
        entry: {
          id: 'mem_proj_001',
          scope: 'project',
          project: 'portlight-ships',
          kind: 'checklist',
          rule_key: 'rigging.shrouds',
          status: 'proposed',
          statement: 'Check that shrouds terminate cleanly at the chainwale.',
          evidence_refs: ['run:run_02'],
          author: 'model:glimmer@' + FAKE_SHA_A,
          approver: null,
        },
      });
      assert.equal(proposed.status, 'proposed');

      // Proposed entry is NOT in effective active memory yet
      const beforeApprove = loadEffectiveMemory({ rootDir: tmp, project: 'portlight-ships' });
      assert.equal(beforeApprove.activeEntries.length, 1);
      assert.equal(beforeApprove.activeEntries[0].id, 'mem_global_001');

      // 5. Director approves proposed project entry -> becomes active
      const approved = approveProposedMemoryEntry({
        rootDir: tmp,
        scope: 'project',
        project: 'portlight-ships',
        id: 'mem_proj_001',
        approver: 'human:director',
        reason: 'Confirmed shroud termination issue on brigantine plates',
      });
      assert.equal(approved.status, 'active');
      assert.equal(approved.approver, 'human:director');

      // 6. Silent contradiction of global rule (same rule_key without overrides) is refused!
      assert.throws(
        () =>
          appendMemoryEntry({
            rootDir: tmp,
            entry: {
              id: 'mem_proj_silent_contra',
              scope: 'project',
              project: 'portlight-ships',
              kind: 'rule',
              rule_key: 'lighting.glare',
              status: 'active',
              statement: 'Allow bright lens flare on beacon ships.',
              evidence_refs: ['canon:beacon'],
              author: 'human:director',
              approver: 'human:director',
              overrides: null,
            },
          }),
        /MEMORY_SILENT_CONTRADICTION/
      );

      // Override without reason is refused!
      assert.throws(
        () =>
          appendMemoryEntry({
            rootDir: tmp,
            entry: {
              id: 'mem_proj_no_reason',
              scope: 'project',
              project: 'portlight-ships',
              kind: 'rule',
              rule_key: 'lighting.glare',
              status: 'active',
              statement: 'Allow controlled lantern glint on beacon vessels.',
              evidence_refs: ['canon:beacon'],
              author: 'human:director',
              approver: 'human:director',
              overrides: 'mem_global_001',
              reason: '',
            },
          }),
        /MEMORY_OVERRIDE_INVALID/
      );

      // 7. Explicit override with overrides + reason + human:director succeeds and supersedes global rule in effective view
      appendMemoryEntry({
        rootDir: tmp,
        entry: {
          id: 'mem_proj_override_001',
          scope: 'project',
          project: 'portlight-ships',
          kind: 'rule',
          rule_key: 'lighting.glare',
          status: 'active',
          statement: 'Allow controlled lantern glint on signal vessels only.',
          evidence_refs: ['canon:signal_ships'],
          author: 'human:director',
          approver: 'human:director',
          overrides: 'mem_global_001',
          reason: 'Signal ships require visible lantern specular highlight',
        },
      });

      const effective = loadEffectiveMemory({ rootDir: tmp, project: 'portlight-ships' });
      // Global mem_global_001 is overridden by mem_proj_override_001; order is global active then project active
      assert.deepEqual(
        effective.activeEntries.map((e) => e.id),
        ['mem_proj_001', 'mem_proj_override_001']
      );

      // 8. No cross-talk: another project's memory is never read, and cross-project load paths are refused
      appendMemoryEntry({
        rootDir: tmp,
        entry: {
          id: 'mem_other_proj_001',
          scope: 'project',
          project: 'star-freight',
          kind: 'rule',
          status: 'active',
          statement: 'Star-freight thruster rule.',
          evidence_refs: ['canon:thruster'],
          author: 'human:director',
          approver: 'human:director',
          reason: 'Star-freight rule',
        },
      });
      const portlightAfterOther = loadEffectiveMemory({ rootDir: tmp, project: 'portlight-ships' });
      assert.ok(!portlightAfterOther.activeEntries.some((e) => e.id === 'mem_other_proj_001'));

      assert.throws(
        () =>
          loadEffectiveMemory({
            rootDir: tmp,
            project: 'portlight-ships',
            extraProjectStores: ['star-freight'],
          }),
        /MEMORY_CROSS_TALK_FORBIDDEN/
      );

      // 9. Promotion from project to global writes a reviewed promotion entry in global store and keeps project entry intact
      const promoted = promoteProjectMemoryToGlobal({
        rootDir: tmp,
        sourceProject: 'portlight-ships',
        sourceEntryId: 'mem_proj_001',
        newGlobalId: 'mem_global_promoted_001',
        approver: 'human:director',
        reason: 'Chainwale shroud check applies to all maritime projects',
      });
      assert.equal(promoted.scope, 'global');
      assert.equal(promoted.kind, 'promotion');
      assert.equal(promoted.status, 'active');
      assert.equal(promoted.promoted_from.project, 'portlight-ships');
      assert.equal(promoted.promoted_from.entry_id, 'mem_proj_001');
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  it('§7 & §12.5: writes memory-snapshot.json, diffs snapshots, and records verdicts.jsonl with both memory SHAs and closed-list failure modes', () => {
    const tmp = mkdtempSync(join(tmpdir(), 'sdlab-lane2-snap-'));
    try {
      appendMemoryEntry({
        rootDir: tmp,
        entry: {
          id: 'mem_global_10',
          scope: 'global',
          project: null,
          kind: 'rule',
          status: 'active',
          statement: 'Orthographic side profile must show complete waterline.',
          evidence_refs: ['canon:ortho_v1'],
          author: 'human:director',
          approver: 'human:director',
          reason: 'Studio orthographic baseline',
        },
      });

      const snap1Path = join(tmp, 'snap1.json');
      const snap1 = writeMemorySnapshot({
        rootDir: tmp,
        project: 'portlight-ships',
        windowId: 'win_lane2_01',
        outPath: snap1Path,
      });
      assert.match(snap1.memory_sha_global, /^sha256:[0-9a-f]{64}$/);
      assert.match(snap1.memory_sha_project, /^sha256:[0-9a-f]{64}$/);

      appendMemoryEntry({
        rootDir: tmp,
        entry: {
          id: 'mem_proj_10',
          scope: 'project',
          project: 'portlight-ships',
          kind: 'banned_token',
          status: 'active',
          statement: 'Never include modern radar domes.',
          evidence_refs: ['canon:era_rules'],
          author: 'human:director',
          approver: 'human:director',
          reason: 'Pre-industrial maritime canon',
        },
      });

      const snap2Path = join(tmp, 'snap2.json');
      const snap2 = writeMemorySnapshot({
        rootDir: tmp,
        project: 'portlight-ships',
        windowId: 'win_lane2_02',
        outPath: snap2Path,
      });
      assert.equal(snap1.memory_sha_global, snap2.memory_sha_global);
      assert.notEqual(snap1.memory_sha_project, snap2.memory_sha_project);

      const diff = diffMemorySnapshots(snap1, snap2);
      assert.deepEqual(diff.added, ['mem_proj_10']);
      assert.deepEqual(diff.removed, []);
      assert.equal(diff.globalChanged, false);
      assert.equal(diff.projectChanged, true);

      // Record vision verdict carrying both memory snapshot SHAs and closed-list failure modes
      const verdictsPath = join(tmp, 'verdicts.jsonl');
      assert.ok(ALLOWED_FAILURE_MODES.includes('silhouette_drift'));

      assert.throws(
        () =>
          recordVisionVerdict({
            verdictsPath,
            windowId: 'win_lane2_02',
            imageSha256: FAKE_SHA_B,
            canonSha: FAKE_SHA_C,
            memorySnapshot: snap2,
            verifierModel: {
              name: GLIMMER_DEFAULT_MODEL.name,
              digest: FAKE_SHA_A,
              licence_id: 'Apache-2.0',
            },
            verdict: 'fail',
            failureModes: ['made_up_failure_mode'],
          }),
        /VERDICT_FAILURE_MODE_INVALID/
      );

      const row = recordVisionVerdict({
        verdictsPath,
        windowId: 'win_lane2_02',
        imageSha256: FAKE_SHA_B,
        canonSha: FAKE_SHA_C,
        memorySnapshot: snap2,
        verifierModel: {
          name: GLIMMER_DEFAULT_MODEL.name,
          digest: FAKE_SHA_A,
          licence_id: 'Apache-2.0',
        },
        sampling: { temperature: 0, top_p: 1.0, seed: 42 },
        verdict: 'fail',
        failureModes: ['silhouette_drift', 'rigging_tangle'],
        notes: 'Foremast rigging merges into staysail silhouette.',
      });

      assert.equal(row.memory_sha_global, snap2.memory_sha_global);
      assert.equal(row.memory_sha_project, snap2.memory_sha_project);
      assert.equal(row.verdict, 'fail');
      const onDisk = readFileSync(verdictsPath, 'utf-8').trim().split('\n');
      assert.equal(onDisk.length, 1);
      assert.equal(JSON.parse(onDisk[0]).image_sha256, FAKE_SHA_B);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});
