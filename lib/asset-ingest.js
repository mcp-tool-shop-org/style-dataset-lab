/**
 * Asset ingest engine — register a validated asset export into a project.
 *
 * Sits beside lib/ingest.js (bare external images) as the manifest-driven,
 * gated sibling: `sdlab asset ingest` consumes an export directory whose
 * asset-source.json has passed the full contract (lib/asset-source.js), runs
 * the ported receiving-dock gates per render, and registers records under
 * the existing machinery.
 *
 * Non-negotiables inherited from lib/ingest.js, held here too:
 *   - NEVER invents a judgment, a score, or a caption. Records land with
 *     judgment: null, canon: null via the same buildBaseRecord. Caption
 *     MATERIAL (subject, facing, trigger, domain tag) rides in provenance —
 *     assembling a caption is a package-build decision, not an ingest fact.
 *   - provenance.source is 'asset' — a third honest source alongside
 *     'generated' and 'external', carrying the acceptance block verbatim.
 *   - --dry-run performs zero filesystem writes.
 *   - idempotent + crash-safe: records are skipped when already present
 *     (same asset, same manifest hash), both images and records land via
 *     temp-then-rename, and the receipt is written LAST — its presence
 *     means the ingest completed. A crash mid-ingest leaves records that a
 *     re-run skips, then finishes, then writes the receipt.
 *   - ANDON: a render failing the asset's own declared palette gate is
 *     REJECTED (reported, never registered). All renders failing fails the
 *     ingest. A record-id collision with a different asset refuses loudly.
 *
 * Compensator (NAMED_COMPENSATORS): the receipt lists every path this
 * ingest created. Undo = delete those paths (or `git clean` / `git revert`
 * once committed). Owner: user.
 */

import { readFile, writeFile, mkdir, rename, unlink } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { basename, extname, join, sep } from 'node:path';
import { buildBaseRecord } from './records.js';
import { inputError } from './errors.js';
import { decodePng } from './png-meta.js';
import { paletteGate, classShares } from './asset-masks.js';
import {
  ASSET_MANIFEST_FILENAME,
  validateAssetSource,
  facingFromCamera,
} from './asset-source.js';

export const ASSET_INGEST_TOOL_ID = 'sdlab-asset-ingest-v1';
export const ASSET_RECEIPT_SCHEMA_VERSION = '1.0.0';
export const RECEIPT_FILENAME = 'ingest-receipt.json';

const DEFAULT_DOMAIN_TAG = '3d asset'; // MVDream's verbatim render-caption tag (design doc Q4)

function toPortablePath(p) {
  return p.split(sep).join('/');
}

function sha256(buf) {
  return createHash('sha256').update(buf).digest('hex');
}

// Same temp-then-rename shape as lib/ingest.js / lib/runtime-runs.js /
// lib/batch-runs.js — each module keeps its own copy by established
// convention in this codebase.
async function atomicWriteFile(targetPath, body) {
  const tmpPath = `${targetPath}.tmp-${process.pid}-${Date.now()}`;
  try {
    await writeFile(tmpPath, body);
    await rename(tmpPath, targetPath);
  } catch (err) {
    try { await unlink(tmpPath); } catch { /* best-effort cleanup */ }
    throw err;
  }
}

/**
 * Read + hash + atomically materialize a source file into the project.
 * Returns the sha256 either way; writes only when `write` is true.
 */
async function hashAndMaybeCopy(absSrc, absDest, write) {
  const buf = await readFile(absSrc);
  const hash = sha256(buf);
  if (write) await atomicWriteFile(absDest, buf);
  return { hash, bytes: buf.length };
}

/**
 * Ingest a validated asset export into a project.
 *
 * @param {string} projectRoot — absolute project root (resolved by caller)
 * @param {string} sourceDir — absolute export directory (must contain asset-source.json)
 * @param {Object} [options]
 * @param {boolean} [options.dryRun]
 * @returns {Promise<Object>} report — see the shape at the bottom
 */
export async function ingestAssetSource(projectRoot, sourceDir, options = {}) {
  const dryRun = Boolean(options.dryRun);

  const manifestPath = join(sourceDir, ASSET_MANIFEST_FILENAME);
  const { manifest, resolved, manifestRaw } = await validateAssetSource(manifestPath);

  const assetId = manifest.asset.id;
  const manifestSha = sha256(manifestRaw);
  const assetDir = join(projectRoot, 'assets', assetId);
  const receiptPath = join(assetDir, RECEIPT_FILENAME);
  const recordsDir = join(projectRoot, 'records');
  const candidatesDir = join(projectRoot, 'outputs', 'candidates');

  // ── Idempotency at the asset level ────────────────────────────────
  if (existsSync(receiptPath)) {
    let receipt;
    try {
      receipt = JSON.parse(await readFile(receiptPath, 'utf-8'));
    } catch (err) {
      throw inputError(
        'ASSET_RECEIPT_CORRUPT',
        `${receiptPath} exists but is unreadable: ${err.message}`,
        'Inspect the assets directory; remove it explicitly (it is listed as the compensator) to re-ingest.'
      );
    }
    if (receipt.manifest_sha256 === manifestSha) {
      return { assetId, alreadyIngested: true, receiptPath: toPortablePath(join('assets', assetId, RECEIPT_FILENAME)), created: [], skipped: (receipt.records_created || []).slice(), rejected: receipt.rejected_renders || [], dryRun };
    }
    throw inputError(
      'ASSET_ALREADY_INGESTED',
      `Asset "${assetId}" was already ingested from a DIFFERENT manifest (receipt sha ${receipt.manifest_sha256?.slice(0, 12)}…, incoming ${manifestSha.slice(0, 12)}…).`,
      `A changed export is a new truth, not an overwrite. Compensator: delete projects/<project>/assets/${assetId}/ and the records it lists, then re-run. Nothing was written.`
    );
  }

  // ── Receiving-dock gates + measurements (pure reads) ──────────────
  const channelDecls = new Map((manifest.channels || []).map((c) => [c.id, c]));
  const admitted = [];
  const rejected = [];

  for (const [renderId, entry] of resolved.renders) {
    const renderBuf = await readFile(entry.abs);
    const renderImg = decodePng(renderBuf, entry.relPath);
    const silhouetteImg = decodePng(await readFile(entry.silhouette.abs), entry.silhouette.relPath);

    const gate = paletteGate(renderImg, silhouetteImg, manifest.palette, entry.relPath);

    const shares = {};
    for (const [cid, inst] of entry.instances) {
      const decl = channelDecls.get(cid);
      if (!decl?.categorical) continue;
      const instImg = decodePng(await readFile(inst.abs), inst.relPath);
      shares[cid] = classShares(instImg, silhouetteImg, decl, inst.relPath);
    }

    if (!gate.pass) {
      rejected.push({ render_id: renderId, reason: 'palette-gate', gate });
      continue;
    }
    admitted.push({
      renderId,
      entry,
      renderBuf,
      renderSha: sha256(renderBuf),
      width: renderImg.width,
      height: renderImg.height,
      gate,
      shares,
    });
  }

  if (admitted.length === 0) {
    throw inputError(
      'ASSET_ALL_RENDERS_REJECTED',
      `Every render of "${assetId}" failed the asset's own declared palette gate — nothing to register.`,
      `Rejected: ${rejected.map((r) => `${r.render_id} (blob ${r.gate.largest_blob_px}px)`).join(', ')}. ` +
      'The gate bands and thresholds come from the manifest itself; if they are wrong, that is an export-side fix.'
    );
  }

  // ── Plan record ids; refuse collisions with foreign records ───────
  const captionDefaults = manifest.captions || {};
  const plans = [];
  const skipped = [];
  for (const a of admitted) {
    const recordId = `${assetId}__${a.renderId}`;
    const recordPath = join(recordsDir, `${recordId}.json`);
    if (existsSync(recordPath)) {
      let existing = null;
      try {
        existing = JSON.parse(await readFile(recordPath, 'utf-8'));
      } catch { /* unreadable => treated as foreign below */ }
      const sameIngest = existing?.provenance?.source === 'asset'
        && existing?.provenance?.asset_id === assetId
        && existing?.provenance?.manifest_sha256 === manifestSha;
      if (sameIngest) {
        skipped.push(recordId); // crash-resume: record done, receipt wasn't
        continue;
      }
      throw inputError(
        'ASSET_RECORD_COLLISION',
        `Record id "${recordId}" already exists and does not belong to this ingest (source: ${existing?.provenance?.source ?? 'unreadable'}).`,
        'Rename the asset id or resolve the existing record explicitly. Nothing was written.'
      );
    }
    plans.push({ ...a, recordId, recordPath });
  }

  const wouldWrite = [];
  const written = [];
  const filesLedger = [];
  const note = (role, sourceRel, destRel, materialized, hash, bytes) => {
    filesLedger.push({
      role,
      source: toPortablePath(sourceRel),
      dest: destRel ? toPortablePath(destRel) : null,
      materialized,
      sha256: hash ?? null,
      bytes: bytes ?? null,
    });
  };

  // ── Dry run: full plan, zero writes ────────────────────────────────
  if (dryRun) {
    for (const p of plans) {
      wouldWrite.push(toPortablePath(join('records', `${p.recordId}.json`)));
      wouldWrite.push(toPortablePath(join('outputs', 'candidates', `${p.recordId}.png`)));
    }
    wouldWrite.push(toPortablePath(join('assets', assetId, ASSET_MANIFEST_FILENAME)));
    wouldWrite.push(toPortablePath(join('assets', assetId, RECEIPT_FILENAME)));
    return {
      assetId,
      alreadyIngested: false,
      dryRun: true,
      created: plans.map((p) => p.recordId),
      skipped,
      rejected,
      gates: Object.fromEntries(plans.map((p) => [p.recordId, p.gate])),
      wouldWrite,
    };
  }

  // ── Writes ──────────────────────────────────────────────────────────
  await mkdir(recordsDir, { recursive: true });
  await mkdir(candidatesDir, { recursive: true });
  await mkdir(assetDir, { recursive: true });

  // Texture-space artifacts: hashed in place, not materialized — they are
  // provenance-of-record (mesh, atlas, texture channels), never consumed
  // per-render by sdlab mechanism. The receipt pins them by source + hash.
  for (const key of ['mesh', 'atlas']) {
    const ref = resolved[key];
    if (!ref) continue;
    const { hash, bytes } = await hashAndMaybeCopy(ref.abs, null, false);
    note(key, ref.relPath, null, false, hash, bytes);
  }
  for (const [cid, ref] of resolved.textureChannels) {
    const { hash, bytes } = await hashAndMaybeCopy(ref.abs, null, false);
    note(`channel:${cid}`, ref.relPath, null, false, hash, bytes);
  }

  // Per-render artifacts: materialized into the project.
  const subdirs = { masks: join(assetDir, 'masks'), channels: join(assetDir, 'channels'), pairs: join(assetDir, 'pairs'), loss: join(assetDir, 'loss-masks') };

  const created = [];
  for (const p of plans) {
    const { entry } = p;
    const candidateName = `${p.recordId}.png`;
    const candidatePath = join(candidatesDir, candidateName);
    const candidateRel = toPortablePath(join('outputs', 'candidates', candidateName));

    if (!existsSync(candidatePath)) {
      await atomicWriteFile(candidatePath, p.renderBuf);
    }
    note('render', entry.relPath, candidateRel, true, p.renderSha, p.renderBuf.length);
    written.push(candidateRel);

    const silName = `${p.renderId}${extname(entry.silhouette.relPath) || '.png'}`;
    await mkdir(subdirs.masks, { recursive: true });
    const silDest = join(subdirs.masks, silName);
    const silRel = toPortablePath(join('assets', assetId, 'masks', silName));
    const sil = await hashAndMaybeCopy(entry.silhouette.abs, silDest, true);
    note('silhouette', entry.silhouette.relPath, silRel, true, sil.hash, sil.bytes);
    written.push(silRel);

    const channelRefs = {};
    for (const [cid, inst] of entry.instances) {
      await mkdir(subdirs.channels, { recursive: true });
      const instName = `${cid}__${p.renderId}${extname(inst.relPath) || '.png'}`;
      const instDest = join(subdirs.channels, instName);
      const instRel = toPortablePath(join('assets', assetId, 'channels', instName));
      const h = await hashAndMaybeCopy(inst.abs, instDest, true);
      note(`channel:${cid}:${p.renderId}`, inst.relPath, instRel, true, h.hash, h.bytes);
      written.push(instRel);
      channelRefs[cid] = { path: instRel, sha256: h.hash };
    }

    let lossRef;
    if (entry.lossMask) {
      await mkdir(subdirs.loss, { recursive: true });
      const lossName = `${p.renderId}${extname(entry.lossMask.relPath) || '.png'}`;
      const lossDest = join(subdirs.loss, lossName);
      const lossRel = toPortablePath(join('assets', assetId, 'loss-masks', lossName));
      const h = await hashAndMaybeCopy(entry.lossMask.abs, lossDest, true);
      note(`loss-mask:${p.renderId}`, entry.lossMask.relPath, lossRel, true, h.hash, h.bytes);
      written.push(lossRel);
      lossRef = { path: lossRel, sha256: h.hash };
    }

    const pairRefs = {};
    for (const [name, pref] of entry.pairs) {
      await mkdir(subdirs.pairs, { recursive: true });
      const pairName = `${name}__${p.renderId}${extname(pref.relPath) || '.png'}`;
      const pairDest = join(subdirs.pairs, pairName);
      const pairRel = toPortablePath(join('assets', assetId, 'pairs', pairName));
      const h = await hashAndMaybeCopy(pref.abs, pairDest, true);
      note(`pair:${name}:${p.renderId}`, pref.relPath, pairRel, true, h.hash, h.bytes);
      written.push(pairRel);
      pairRefs[name] = { path: pairRel, sha256: h.hash };
    }

    const render = entry.render;
    const facing = render.facing || facingFromCamera(render.camera);
    const provenance = {
      source: 'asset',
      ingested_at: new Date().toISOString(),
      asset_id: assetId,
      asset_source: manifest.asset.source ?? null,
      manifest_path: toPortablePath(join('assets', assetId, ASSET_MANIFEST_FILENAME)),
      manifest_sha256: manifestSha,
      acceptance: { ...manifest.acceptance },
      render_id: p.renderId,
      camera: { yaw_deg: render.camera.yaw_deg, elevation_deg: render.camera.elevation_deg ?? 0 },
      light: render.light ?? null,
      facing,
      silhouette_mask: { path: silRel, sha256: sil.hash },
      channels: channelRefs,
      caption_fields: {
        subject: captionDefaults.subject ?? null,
        style_trigger: captionDefaults.style_trigger ?? null,
        domain_tag: captionDefaults.domain_tag ?? DEFAULT_DOMAIN_TAG,
        facing,
      },
      generation_provenance_known: true,
    };
    if (lossRef) provenance.loss_mask = lossRef;
    if (Object.keys(pairRefs).length > 0) provenance.pair = pairRefs;

    const record = buildBaseRecord(
      p.recordId,
      candidateRel,
      { width: p.width, height: p.height, bytes: p.renderBuf.length },
      provenance
    );
    // Distinct key from `sdlab measure`'s record.measurements, which that
    // command overwrites wholesale — asset receiving-dock numbers must
    // survive a later measure run.
    record.asset_measurements = {
      tool: ASSET_INGEST_TOOL_ID,
      palette_gate: p.gate,
      class_shares: p.shares,
    };

    const recordRel = toPortablePath(join('records', `${p.recordId}.json`));
    await atomicWriteFile(p.recordPath, JSON.stringify(record, null, 2) + '\n');
    written.push(recordRel);
    created.push(p.recordId);
  }

  // Manifest copy — byte-identical.
  const manifestDestRel = toPortablePath(join('assets', assetId, ASSET_MANIFEST_FILENAME));
  await atomicWriteFile(join(assetDir, ASSET_MANIFEST_FILENAME), manifestRaw);
  note('manifest', ASSET_MANIFEST_FILENAME, manifestDestRel, true, manifestSha, manifestRaw.length);
  written.push(manifestDestRel);

  // Receipt LAST — its presence means this ingest completed.
  const receipt = {
    schema_version: ASSET_RECEIPT_SCHEMA_VERSION,
    tool: ASSET_INGEST_TOOL_ID,
    ingested_at: new Date().toISOString(),
    asset_id: assetId,
    source_dir: toPortablePath(sourceDir),
    manifest_sha256: manifestSha,
    files: filesLedger,
    records_created: created,
    records_skipped: skipped,
    rejected_renders: rejected,
    written,
  };
  const receiptRel = toPortablePath(join('assets', assetId, RECEIPT_FILENAME));
  await atomicWriteFile(receiptPath, JSON.stringify(receipt, null, 2) + '\n');

  return {
    assetId,
    alreadyIngested: false,
    dryRun: false,
    created,
    skipped,
    rejected,
    gates: Object.fromEntries(plans.map((p) => [p.recordId, p.gate])),
    receiptPath: receiptRel,
  };
}
