---
title: Security
description: Threat model, trust boundaries, and data handling.
sidebar:
  order: 6
---

## Threat model

Style Dataset Lab is a **local-only** tool. It runs on your machine, talks to a local ComfyUI server, and never makes outbound network requests.

### Attack surface

| Component | Risk | Mitigation |
|-----------|------|------------|
| ComfyUI server | Listens on `127.0.0.1:8188`. If exposed to a network, an attacker could inject workflow payloads. | Keep the default localhost binding. Never bind to `0.0.0.0` or a public interface. |
| Model weights | `.safetensors`, `.ckpt`, `.pth`, `.bin` files loaded by ComfyUI could contain malicious pickle payloads (especially `.ckpt` and `.pth`). | Only load weights from sources you trust. Prefer `.safetensors` format, which is pickle-free by design. |
| Prompt packs | JSON files that define generation parameters. A malicious prompt pack could attempt path traversal in output paths. | Scripts resolve paths relative to the repo root and do not follow symlinks. |
| Record files | JSON files with judgment and provenance data. Not executable. | No risk beyond data integrity. |

### What it does NOT do

- **No telemetry.** Zero usage data collection. Zero outbound requests beyond the local ComfyUI API.
- **No authentication.** The local ComfyUI API has no auth layer. This is acceptable for localhost but dangerous if the server is network-exposed.
- **No remote storage.** All images, records, and exports stay on your local filesystem.
- **No code execution from records.** Record JSON is read as data, never evaluated or executed.

## Model weight trust

ComfyUI loads model weights at startup and during workflow execution. The trust chain is:

1. **Checkpoints** (`.safetensors`, `.ckpt`) -- the base diffusion model. The `.safetensors` format is safe by design (no arbitrary code). The `.ckpt` format uses Python pickle and can contain arbitrary code -- only load `.ckpt` files from trusted sources.

2. **LoRAs** (`.safetensors`) -- style and subject fine-tunes. Same trust rules as checkpoints.

3. **ControlNet models** -- structural guidance models. Same trust rules.

4. **IP-Adapter models** -- style reference models. Same trust rules.

**Recommendation:** Use `.safetensors` exclusively. The default generation setup (DreamShaper XL Turbo + ClassipeintXL LoRA) uses only `.safetensors` files.

## Data handling

### What is stored

| Data | Location | Sensitive? |
|------|----------|------------|
| Generated images | `outputs/` | No -- synthetic images, no PII |
| Provenance records | `records/` | No -- generation parameters only |
| Judgment records | `records/` | No -- aesthetic scores and explanations |
| Comparisons | `comparisons/` | No -- pairwise preference judgments |
| Exports | `exports/` | No -- training data derived from above |
| Prompt packs | `inputs/prompts/` | No -- text prompts and generation config |

### What is gitignored

Large binary files are excluded from version control:

- `outputs/candidates/*.png` -- raw generations (regenerable)
- `outputs/approved/*.png` -- curated images (regenerable)
- `outputs/rejected/*.png` -- rejected images (regenerable)
- `exports/` -- training data output (regenerable)
- `*.safetensors`, `*.ckpt`, `*.pth`, `*.bin` -- model weights

Records (`records/*.json`) and comparisons (`comparisons/*.json`) are tracked in git because they represent human judgment that cannot be regenerated.

## Reporting vulnerabilities

If you discover a security issue, email **64996768+mcp-tool-shop@users.noreply.github.com**. Expected response time: 72 hours. Do not open public issues for security vulnerabilities.
