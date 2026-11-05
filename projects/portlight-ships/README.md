# Portlight Ships (`portlight-ships`)

Age-of-sail merchant and naval vessel visual canon and dataset project for **Portlight**, built on the Apache-2.0 **Qwen-Image** base model (`qwen_image_fp8_e4m3fn.safetensors`, `qwen_2.5_vl_7b_fp8_scaled.safetensors`, `qwen_image_vae.safetensors`) and released under **CC-BY-4.0** (`owner: mcp-tool-shop`).

## Shipwright Traditions & 14 Canonical Hulls

1. **Cold-Coast (`cold-coast`)**: `cog`, `fluyt`, `carrack`
2. **Sunward-Sea (`sunward-sea`)**: `galley`, `xebec`, `caravel`
3. **Crown Naval (`crown-naval`)**: `brig`, `barque`, `frigate`, `galleon`
4. **Longshore (`longshore`)**: `sloop`, `schooner`, `brigantine`
5. **Far-Trade (`far-trade`)**: `junk`

## Quick Start

```bash
sdlab project doctor --project portlight-ships
sdlab canon build --project portlight-ships --dry-run
sdlab verify --project portlight-ships
```
