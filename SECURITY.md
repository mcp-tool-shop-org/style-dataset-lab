# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.x     | Yes       |
| 1.x     | No        |
| 0.x     | No        |

## Threat Model

style-dataset-lab is a **local-only** visual dataset factory. It connects to a ComfyUI server running on `localhost:8188` and does not make any external network calls.

**Attack surface:**

- **ComfyUI server** listens on localhost only. If exposed to a network, an attacker could inject workflow payloads. Keep the default localhost binding.
- **Untrusted model weights** (`.safetensors`, `.ckpt`, `.pth`, `.bin`) loaded by ComfyUI could contain malicious pickle payloads. Only load weights from sources you trust.
- **No telemetry.** This tool collects no usage data and makes no outbound requests beyond the local ComfyUI API.
- **No authentication.** The local ComfyUI API has no auth layer. This is acceptable for localhost but dangerous if network-exposed.

## Reporting a Vulnerability

If you discover a security issue, please email:

**64996768+mcp-tool-shop@users.noreply.github.com**

Expected response time: **72 hours**.

Please do not open public issues for security vulnerabilities.
