/**
 * End-to-end offline provenance chain verifier (G9, §2.2–§2.3).
 *
 * Walks every link required for CC-BY-4.0 release eligibility:
 *   1. owner_and_licence (G5): owner === "mcp-tool-shop", licence === "CC-BY-4.0", ai_assisted_disclosure === true
 *   2. canon_link (G6): canon_sha, entry_id, entry_sha256 match canon-build/<canon_sha>/manifest.json per_entity_hashes
 *   3. run_manifest_link (§2.2.1): run_id, seed, prompt/prompt_sha256, comfy_workflow_sha match runs/<run_id>/manifest.json, and image exists
 *   4. model_licences (G4): all models and LoRAs in pinning have cleared SPDX licence_id, non-empty licence_url, and date_read
 *   5. quarantine_guard (§2.2.5): no reference to held Portlight data (`plsvessel`, `nano-banana`)
 *   6. verdict_separation (§2.2.6): approved records cite a reviewer/judge distinct from the generator model
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, resolve, relative, isAbsolute } from 'node:path';
import { STUDIO_OWNER, STUDIO_LICENCE } from './records.js';
import { isClearedLicenceEntry, isQuarantinedName } from './model-licences.js';

function isSafeRelativeAssetPath(projectRoot, assetPath) {
  if (!assetPath || typeof assetPath !== 'string') return false;
  const absRoot = resolve(projectRoot);
  const absAsset = resolve(projectRoot, assetPath);
  const rel = relative(absRoot, absAsset);
  return Boolean(rel && !rel.startsWith('..') && !isAbsolute(rel));
}

/**
 * Verify all provenance links for a single record object against on-disk manifests.
 */
export function verifyRecordProvenance(projectRoot, record) {
  const recordId = record?.id || record?.record_id || '<unknown>';
  const failures = [];
  const links = {
    owner_and_licence: 'pass',
    canon_link: 'pass',
    run_manifest_link: 'pass',
    model_licences: 'pass',
    quarantine_guard: 'pass',
    verdict_separation: 'pass',
  };

  function fail(link, code, message) {
    links[link] = 'fail';
    failures.push({ record_id: recordId, link, code, message });
  }

  // 1. G5: Owner and CC-BY-4.0 licence stamp
  const owner = record?.owner ?? record?.rights?.owner ?? null;
  const licence = record?.licence ?? record?.rights?.licence ?? null;
  const disclosure = record?.rights?.ai_assisted_disclosure === true;
  if (owner !== STUDIO_OWNER || licence !== STUDIO_LICENCE || !disclosure) {
    fail(
      'owner_and_licence',
      'MISSING_OWNER_OR_LICENCE',
      `Record "${recordId}" must carry owner="${STUDIO_OWNER}", licence="${STUDIO_LICENCE}", and rights.ai_assisted_disclosure=true (got owner=${JSON.stringify(owner)}, licence=${JSON.stringify(licence)}, disclosure=${JSON.stringify(disclosure)})`,
    );
  }

  const genProv =
    record?.generation_provenance ||
    record?.provenance?.generation_provenance ||
    record?.provenance ||
    {};

  // 2. G6: Canon link (canon_sha, entry_id, entry_sha256 -> canon-build/<canon_sha>/manifest.json)
  const canonSha = record?.canon?.canon_sha ?? genProv?.canon_sha ?? null;
  const entryId = record?.canon?.entry_id ?? genProv?.entry_id ?? null;
  const entrySha256 = record?.canon?.entry_sha256 ?? genProv?.entry_sha256 ?? null;

  if (!canonSha || !entryId || !entrySha256) {
    fail(
      'canon_link',
      'BROKEN_CANON_LINK',
      `Record "${recordId}" is missing canon link fields (canon_sha=${canonSha}, entry_id=${entryId}, entry_sha256=${entrySha256})`,
    );
  } else {
    const canonManifestPath = join(projectRoot, 'canon-build', String(canonSha), 'manifest.json');
    if (!existsSync(canonManifestPath)) {
      fail(
        'canon_link',
        'BROKEN_CANON_LINK',
        `Canon build manifest not found at canon-build/${canonSha}/manifest.json for record "${recordId}"`,
      );
    } else {
      try {
        const canonManifest = JSON.parse(readFileSync(canonManifestPath, 'utf-8'));
        const expectedSha = canonManifest?.per_entity_hashes?.[entryId];
        if (!expectedSha || expectedSha !== entrySha256) {
          fail(
            'canon_link',
            'BROKEN_CANON_LINK',
            `Record "${recordId}" entry_sha256 (${entrySha256}) does not match canon-build/${canonSha}/manifest.json per_entity_hashes["${entryId}"] (${expectedSha || 'missing'})`,
          );
        }
      } catch (err) {
        fail(
          'canon_link',
          'BROKEN_CANON_LINK',
          `Canon build manifest canon-build/${canonSha}/manifest.json could not be parsed: ${err.message}`,
        );
      }
    }
  }

  // 3. §2.2.1: Run manifest link + workflow sha + image existence
  const runId = genProv?.run_id ?? null;
  const recWorkflowSha = genProv?.comfy_workflow_sha ?? record?.provenance?.pinning?.comfy_workflow_sha ?? null;
  const hasSeed = Number.isFinite(genProv?.seed);
  const hasPrompt =
    (typeof genProv?.prompt === 'string' && genProv.prompt.length > 0) ||
    (typeof genProv?.prompt_sha256 === 'string' && genProv.prompt_sha256.length > 0);

  let runManifest = null;
  if (!runId || !recWorkflowSha || !hasSeed || !hasPrompt) {
    fail(
      'run_manifest_link',
      'BROKEN_RUN_MANIFEST_LINK',
      `Record "${recordId}" provenance is missing run_id (${runId}), comfy_workflow_sha (${recWorkflowSha}), seed (${genProv?.seed}), or prompt`,
    );
  } else {
    const runManifestPath = join(projectRoot, 'runs', String(runId), 'manifest.json');
    if (!existsSync(runManifestPath)) {
      fail(
        'run_manifest_link',
        'BROKEN_RUN_MANIFEST_LINK',
        `Run manifest runs/${runId}/manifest.json not found for record "${recordId}"`,
      );
    } else {
      try {
        runManifest = JSON.parse(readFileSync(runManifestPath, 'utf-8'));
        const manifestWfSha = runManifest?.pinning?.comfy_workflow_sha ?? null;
        if (!manifestWfSha || manifestWfSha !== recWorkflowSha) {
          fail(
            'run_manifest_link',
            'BROKEN_RUN_MANIFEST_LINK',
            `Record "${recordId}" comfy_workflow_sha (${recWorkflowSha}) does not match runs/${runId}/manifest.json (${manifestWfSha})`,
          );
        }
      } catch (err) {
        fail(
          'run_manifest_link',
          'BROKEN_RUN_MANIFEST_LINK',
          `Run manifest runs/${runId}/manifest.json could not be parsed: ${err.message}`,
        );
      }
    }
  }

  const assetPath = record?.asset_path ?? record?.image_path ?? null;
  if (!isSafeRelativeAssetPath(projectRoot, assetPath) || !existsSync(join(projectRoot, assetPath))) {
    fail(
      'run_manifest_link',
      'BROKEN_RUN_MANIFEST_LINK',
      `Record "${recordId}" asset_path (${assetPath}) does not exist inside the project`,
    );
  }

  // 4. G4: Model and LoRA licences
  const pinning = runManifest?.pinning ?? record?.provenance?.pinning ?? null;
  const modelEntries = Object.entries(pinning?.models || {}).map(([role, entry]) => ({ role, ...entry }));
  const loraEntries = (pinning?.loras || []).map((entry, idx) => ({ role: `lora[${idx}]`, ...entry }));
  const allWeightEntries = [...modelEntries, ...loraEntries];

  if (!pinning || allWeightEntries.length === 0) {
    fail(
      'model_licences',
      'UNLICENSED_OR_EXCLUDED_MODEL',
      `Record "${recordId}" has no pinned model weights to verify licences against`,
    );
  } else {
    const invalidWeights = allWeightEntries.filter((entry) => !isClearedLicenceEntry(entry));
    if (pinning.cc_by_4_eligible === false || invalidWeights.length > 0) {
      const desc = invalidWeights
        .map((w) => `${w.role}:${w.name || '<unnamed>'}(licence=${w.licence_id || 'missing'})`)
        .join(', ');
      fail(
        'model_licences',
        'UNLICENSED_OR_EXCLUDED_MODEL',
        `Record "${recordId}" uses unlicensed or excluded model/LoRA weights: ${desc || 'cc_by_4_eligible=false'}`,
      );
    }
  }

  // 5. §2.2.5: Quarantine guard (no held Portlight data / plsvessel / nano-banana)
  const serializedChain = JSON.stringify({ record, runManifest });
  if (isQuarantinedName(serializedChain)) {
    fail(
      'quarantine_guard',
      'QUARANTINED_SOURCE_REFERENCED',
      `Record "${recordId}" or its run manifest references quarantined/held data (plsvessel / nano-banana)`,
    );
  }

  // 6. §2.2.6: Verdict separation (judge != generator on approved records)
  if (record?.judgment && record.judgment.status === 'approved') {
    const judge = record.judgment.judged_by_model || record.judgment.reviewed_by || null;
    const generator = record.judgment.generator_model || null;
    if (!judge || (generator && judge === generator)) {
      fail(
        'verdict_separation',
        'INVALID_VERDICT_PROVENANCE',
        `Record "${recordId}" has an invalid approval verdict (judge=${judge}, generator=${generator})`,
      );
    }
  }

  return {
    record_id: recordId,
    ok: failures.length === 0,
    links,
    failures,
  };
}

/**
 * Verify the provenance chain across a project (or a single record / snapshot).
 */
export async function verifyProvenanceChain(
  projectRoot,
  { recordId = null, snapshotId = null, allowEmpty = false } = {},
) {
  const recordsDir = join(projectRoot, 'records');
  const recordsToCheck = [];
  const globalFailures = [];

  if (recordId) {
    const recPath = join(recordsDir, `${recordId}.json`);
    if (!existsSync(recPath)) {
      globalFailures.push({
        record_id: recordId,
        link: 'scope',
        code: 'RECORD_NOT_FOUND',
        message: `Record "${recordId}" not found at records/${recordId}.json`,
      });
    } else {
      recordsToCheck.push(JSON.parse(readFileSync(recPath, 'utf-8')));
    }
  } else if (snapshotId) {
    const incPath = join(projectRoot, 'snapshots', snapshotId, 'included.jsonl');
    if (!existsSync(incPath)) {
      globalFailures.push({
        record_id: null,
        link: 'scope',
        code: 'SNAPSHOT_NOT_FOUND',
        message: `Snapshot "${snapshotId}" included.jsonl not found`,
      });
    } else {
      const lines = readFileSync(incPath, 'utf-8')
        .split('\n')
        .filter((l) => l.trim())
        .map((l) => JSON.parse(l));
      for (const item of lines) {
        const rid = item.record_id || item.id;
        const recPath = join(recordsDir, `${rid}.json`);
        if (!existsSync(recPath)) {
          globalFailures.push({
            record_id: rid,
            link: 'scope',
            code: 'RECORD_NOT_FOUND',
            message: `Snapshot record "${rid}" not found at records/${rid}.json`,
          });
        } else {
          recordsToCheck.push(JSON.parse(readFileSync(recPath, 'utf-8')));
        }
      }
    }
  } else if (existsSync(recordsDir)) {
    const files = readdirSync(recordsDir)
      .filter((f) => f.endsWith('.json'))
      .sort();
    for (const file of files) {
      recordsToCheck.push(JSON.parse(readFileSync(join(recordsDir, file), 'utf-8')));
    }
  }

  if (recordsToCheck.length === 0 && globalFailures.length === 0 && !allowEmpty) {
    globalFailures.push({
      record_id: null,
      link: 'scope',
      code: 'NO_RECORDS_IN_SCOPE',
      message: 'No records found in scope to verify',
    });
  }

  const results = [];
  const failures = [...globalFailures];

  for (const rec of recordsToCheck) {
    const res = verifyRecordProvenance(projectRoot, rec);
    results.push(res);
    failures.push(...res.failures);
  }

  const passedCount = results.filter((r) => r.ok).length;
  const failedCount = results.length - passedCount;

  return {
    ok: failures.length === 0,
    project_root: projectRoot,
    records_checked: results.length,
    passed_count: passedCount,
    failed_count: failedCount,
    results,
    failures,
  };
}
