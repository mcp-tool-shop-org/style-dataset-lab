/**
 * Pick the canonical output image from a ComfyUI run's `outputs` map.
 *
 * ComfyUI workflows can contain more than one SaveImage node (e.g. a
 * preview save + a final save, or multiple intermediate saves). Picking
 * the first via `Object.values()` is non-deterministic across builds —
 * Node guarantees insertion order, but the order in which ComfyUI
 * populates `outputs` depends on its execution scheduler.
 *
 * Selection precedence:
 *   1. `preferNodeId` — explicit hint from the workflow builder
 *      (`buildWorkflowGraph` returns `{ saveNodeId }`) or from a
 *      workflow profile's `expected_outputs.save_node_id`.
 *   2. Highest numeric node id among nodes that emitted images.
 *      This matches the typical convention where the final save node
 *      is appended last, and is deterministic regardless of map order.
 *   3. First node in iteration order — last-resort fallback for the
 *      pathological case where node ids aren't numeric.
 *
 * @param {Object} nodeOutputs - the `outputs` field from a ComfyUI prompt result
 * @param {Object} [opts]
 * @param {string|number|null} [opts.preferNodeId] - hint to prefer
 * @returns {{ filename: string, subfolder: string, nodeId: string } | null}
 */
export function pickOutputImage(nodeOutputs, { preferNodeId = null } = {}) {
  if (!nodeOutputs || typeof nodeOutputs !== 'object') return null;

  const candidates = [];
  for (const [nodeId, nodeOut] of Object.entries(nodeOutputs)) {
    if (nodeOut?.images?.length > 0) {
      candidates.push({ nodeId, image: nodeOut.images[0] });
    }
  }
  if (candidates.length === 0) return null;

  // 1. Honor explicit hint when the matching node actually produced an image.
  if (preferNodeId !== null && preferNodeId !== undefined) {
    const wanted = String(preferNodeId);
    const match = candidates.find(c => c.nodeId === wanted);
    if (match) {
      return {
        filename: match.image.filename,
        subfolder: match.image.subfolder || '',
        nodeId: match.nodeId,
      };
    }
  }

  // 2. Highest numeric node id wins (typical "final save" convention).
  const numeric = candidates
    .map(c => ({ ...c, n: Number(c.nodeId) }))
    .filter(c => Number.isFinite(c.n));
  if (numeric.length > 0) {
    numeric.sort((a, b) => b.n - a.n);
    const winner = numeric[0];
    return {
      filename: winner.image.filename,
      subfolder: winner.image.subfolder || '',
      nodeId: winner.nodeId,
    };
  }

  // 3. Last resort: first iteration entry (non-numeric ids).
  const first = candidates[0];
  return {
    filename: first.image.filename,
    subfolder: first.image.subfolder || '',
    nodeId: first.nodeId,
  };
}
