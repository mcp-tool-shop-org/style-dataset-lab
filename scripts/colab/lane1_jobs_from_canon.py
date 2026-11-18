#!/usr/bin/env python3
"""Build Lane 1 `jobs.jsonl` from a git-committed canon directory and entry list.

Prompt extraction rule (`PROMPT_EXTRACTION_RULE`, evaluated in order per entry at `<canon_sha>`):
  1. `frontmatter:prompt` — explicit non-empty `prompt` (or `visual.prompt`) in YAML frontmatter.
  2. `frontmatter:visual` — structured `visual` fields in YAML frontmatter (`silhouette_cue`,
     `material_dominant` / `material_language`, `lighting_mood`, `signature_features`), prefixed
     with the entry title/summary when present.
  3. `section:visual` — first `##` markdown section whose heading names `visual identity`,
     `appearance and palette`, `appearance`, or `visual` (case-insensitive).
  4. `section:at_a_glance` — `## ... At a glance` markdown section, prefixed with `# Title`.
  5. `body:first_paragraph` — first non-empty prose paragraph in the markdown body, prefixed
     with `# Title` when present.

Inline editorial markers (`[invented]`, `[canon]`, `(C:123)`) and markdown emphasis/bullet prefixes
are stripped and whitespace is collapsed. Entries marked `held` (`status: held`, `held: true`, or
`[HELD]`) or yielding an empty prompt are refused.

Licence and attribution rule:
  - Source canon markdown text is MIT (`canon_licence: "MIT"`).
  - Rendered pictures follow the CC BY 4.0 picture terms of `portlight-bounty`'s `LICENSE`
    (`main` `6e2c0db`), so every job carries `licence: "CC-BY-4.0"` and `credit: "mcp-tool-shop"`,
    both stamped into every rendered PNG's `tEXt` provenance metadata (`sdlab:licence` and
    `sdlab:credit`) and verified on read-back.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lane1_render as l1  # noqa: E402

CANON_TEXT_LICENCE = "MIT"
PICTURE_LICENCE = "CC-BY-4.0"
PICTURE_CREDIT = "mcp-tool-shop"
PICTURE_OWNER = "mcp-tool-shop"

DEFAULT_UNET_NAME = "qwen_image_2512_fp8_e4m3fn.safetensors"
DEFAULT_CLIP_NAME = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
DEFAULT_VAE_NAME = "qwen_image_vae.safetensors"

PROMPT_EXTRACTION_RULE = (
    "1:frontmatter.prompt -> 2:frontmatter.visual -> 3:section(visual/appearance) "
    "-> 4:section(at_a_glance) -> 5:body.first_paragraph"
)

_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
_SAFE_ENTRY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_CITATION_RE = re.compile(r"\[(?:invented|canon)\]|\(C:[0-9,\s-]+\)", re.IGNORECASE)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_VISUAL_HEADING_RE = re.compile(
    r"\b(?:visual\s+identity|appearance\s+and\s+palette|appearance|visual)\b",
    re.IGNORECASE,
)
_AT_A_GLANCE_RE = re.compile(r"\bat\s+a\s+glance\b", re.IGNORECASE)
_HELD_HEADING_RE = re.compile(r"\[held\]|\bstatus\s*:\s*held\b", re.IGNORECASE)


class CanonJobsError(Exception):
    """Named refusal raised while building `jobs.jsonl` from a canon repository."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _git_bytes(repo_root: Path, args: list[str]) -> bytes:
    res = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if res.returncode != 0:
        err = res.stderr.decode("utf-8", errors="replace").strip()
        raise CanonJobsError("CANON_GIT_ERROR", f"git {' '.join(args)}: {err or f'rc={res.returncode}'}")
    return res.stdout


def resolve_canon_repo_and_commit(canon_dir: Path, canon_commit: str) -> tuple[Path, str, str]:
    """Return `(repo_root, canon_rel_posix, resolved_40hex_commit)` for `canon_dir` at `canon_commit`."""
    if not isinstance(canon_commit, str) or not canon_commit.strip():
        raise CanonJobsError("CANON_COMMIT_INVALID", "canon commit must be a non-empty git commit")
    probe_dir = canon_dir if canon_dir.exists() else canon_dir.parent
    if not probe_dir.exists():
        raise CanonJobsError("CANON_DIR_MISSING", f"{canon_dir} does not exist")
    try:
        top_raw = _git_bytes(probe_dir, ["rev-parse", "--show-toplevel"]).decode("utf-8").strip()
    except CanonJobsError as exc:
        raise CanonJobsError("CANON_NOT_GIT_REPO", f"{canon_dir} is not inside a git repository ({exc.detail})") from None
    repo_root = Path(top_raw).resolve()
    canon_abs = canon_dir.resolve()
    try:
        rel_posix = canon_abs.relative_to(repo_root).as_posix()
    except ValueError:
        raise CanonJobsError("CANON_DIR_OUTSIDE_REPO", f"{canon_abs} is outside repo root {repo_root}") from None
    if rel_posix == ".":
        rel_posix = ""

    commit_clean = canon_commit.strip()
    try:
        resolved = (
            _git_bytes(repo_root, ["rev-parse", "--verify", f"{commit_clean}^{{commit}}"])
            .decode("utf-8")
            .strip()
            .lower()
        )
    except CanonJobsError:
        raise CanonJobsError("CANON_COMMIT_INVALID", f"commit {commit_clean!r} not found in {repo_root}") from None
    if not _HEX40_RE.match(resolved):
        raise CanonJobsError("CANON_COMMIT_INVALID", f"resolved ref {resolved!r} is not a 40-hex commit")
    if _HEX40_RE.match(commit_clean.lower()) and resolved != commit_clean.lower():
        raise CanonJobsError("CANON_COMMIT_INVALID", f"commit mismatch: {commit_clean} != {resolved}")
    return repo_root, rel_posix, resolved


def _list_canon_tree_files(repo_root: Path, canon_sha: str, canon_rel_posix: str) -> list[str]:
    cmd = ["ls-tree", "-r", "--name-only", canon_sha]
    if canon_rel_posix:
        cmd.extend(["--", canon_rel_posix])
    out = _git_bytes(repo_root, cmd).decode("utf-8", errors="replace")
    files = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not files:
        scope = canon_rel_posix or "."
        raise CanonJobsError("CANON_DIR_MISSING", f"no tracked canon files under {scope!r} at {canon_sha}")
    return files


def _resolve_entry_git_path(
    entry_id: str,
    tree_files: list[str],
    canon_rel_posix: str,
) -> tuple[str, str]:
    """Return `(canonical_entry_id, repo_rel_posix_path)` for `entry_id` within `tree_files`."""
    clean = entry_id.strip()
    if (
        not clean
        or "\\" in clean
        or clean.startswith("/")
        or not _SAFE_ENTRY_RE.match(clean)
        or any(p in ("", ".", "..") for p in clean.split("/"))
    ):
        raise CanonJobsError("CANON_ENTRY_INVALID", f"unsafe or invalid entry_id {entry_id!r}")

    prefix = f"{canon_rel_posix}/" if canon_rel_posix else ""
    rel_candidates = [clean] if clean.endswith(".md") else [f"{clean}.md", clean]
    tree_set = set(tree_files)
    for cand in rel_candidates:
        full_cand = f"{prefix}{cand}"
        if full_cand in tree_set:
            canon_id = cand[:-3] if cand.endswith(".md") else cand
            return canon_id, full_cand

    if "/" not in clean:
        target_name = clean if clean.endswith(".md") else f"{clean}.md"
        matches = [
            f
            for f in tree_files
            if f.startswith(prefix) and Path(f).name == target_name
        ]
        if len(matches) == 1:
            rel_match = matches[0][len(prefix) :]
            canon_id = rel_match[:-3] if rel_match.endswith(".md") else rel_match
            return canon_id, matches[0]
        if len(matches) > 1:
            raise CanonJobsError(
                "CANON_ENTRY_AMBIGUOUS",
                f"entry_id {entry_id!r} matches multiple canon files: {matches}",
            )

    raise CanonJobsError("CANON_ENTRY_MISSING", f"entry_id {entry_id!r} not found at canon commit")


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end_idx: int | None = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return {}, text
    fm_raw = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1 :])
    try:
        import yaml  # noqa: PLC0415

        parsed = yaml.safe_load(fm_raw)
        if isinstance(parsed, dict):
            return parsed, body
    except Exception:
        pass
    return _parse_minimal_frontmatter(fm_raw), body


def _parse_minimal_frontmatter(fm_raw: str) -> dict[str, Any]:
    """Minimal indentation-aware key/list parser used only if PyYAML is absent."""
    out: dict[str, Any] = {}
    cur_section: str | None = None
    cur_list_key: str | None = None
    for raw_ln in fm_raw.splitlines():
        if not raw_ln.strip() or raw_ln.lstrip().startswith("#"):
            continue
        indent = len(raw_ln) - len(raw_ln.lstrip(" "))
        stripped = raw_ln.strip()
        if indent == 0 and ":" in stripped:
            k, v = stripped.split(":", 1)
            key = k.strip()
            val = v.strip().strip("\"'")
            cur_list_key = None
            if not val:
                out[key] = {}
                cur_section = key
            else:
                out[key] = True if val.lower() == "true" else (False if val.lower() == "false" else val)
                cur_section = None
        elif indent > 0 and cur_section and isinstance(out.get(cur_section), dict):
            sec = out[cur_section]
            if stripped.startswith("- ") and cur_list_key:
                sec.setdefault(cur_list_key, []).append(stripped[2:].strip().strip("\"'"))
            elif ":" in stripped:
                k, v = stripped.split(":", 1)
                sub_k = k.strip()
                sub_v = v.strip().strip("\"'")
                if not sub_v:
                    sec[sub_k] = []
                    cur_list_key = sub_k
                else:
                    sec[sub_k] = sub_v
                    cur_list_key = None
    return out


def _clean_prose_text(raw: str) -> str:
    cleaned_lines: list[str] = []
    in_fence = False
    for raw_ln in raw.splitlines():
        ln = raw_ln.strip()
        if ln.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not ln or ln.startswith("|") or set(ln) <= {"-", "=", "*"}:
            continue
        if ln.startswith(">"):
            ln = ln.lstrip(">").strip()
        ln = re.sub(r"^(?:[-*+]|\d+\.)\s+", "", ln)
        ln = _MD_LINK_RE.sub(r"\1", ln)
        ln = _CITATION_RE.sub("", ln)
        ln = ln.replace("**", "").replace("__", "").replace("`", "")
        ln = re.sub(r"\s+([.,;:!?])", r"\1", ln)
        ln = " ".join(ln.split()).strip(" ;")
        if ln:
            cleaned_lines.append(ln)
    joined = " ".join(
        part if part.endswith((".", "!", "?", ":", ";")) else f"{part}."
        for part in cleaned_lines
    )
    return " ".join(joined.split()).strip()


def extract_prompt_from_markdown(markdown_text: str, *, entry_id: str) -> tuple[str, str]:
    """Extract `(prompt, prompt_source)` from canon markdown according to `PROMPT_EXTRACTION_RULE`."""
    fm, body = _split_frontmatter(markdown_text)

    fm_status = str(fm.get("status", "")).strip().lower()
    if fm_status == "held" or fm.get("held") is True or _HELD_HEADING_RE.search(body[:400]):
        raise CanonJobsError("CANON_ENTRY_HELD", f"entry {entry_id!r} is marked held and cannot be rendered")

    # Rule 1: Explicit prompt in frontmatter (`prompt` or `visual.prompt`)
    fm_prompt = fm.get("prompt")
    if isinstance(fm_prompt, str) and fm_prompt.strip():
        return " ".join(fm_prompt.split()), "frontmatter:prompt"
    fm_visual = fm.get("visual")
    if isinstance(fm_visual, dict):
        vis_prompt = fm_visual.get("prompt")
        if isinstance(vis_prompt, str) and vis_prompt.strip():
            return " ".join(vis_prompt.split()), "frontmatter:prompt"

        # Rule 2: Structured `visual` fields in frontmatter
        vis_parts: list[str] = []
        title_str = str(fm.get("name") or fm.get("title") or "").strip()
        summary_str = str(fm.get("summary") or "").strip()
        if title_str and summary_str:
            vis_parts.append(f"{title_str}: {summary_str.rstrip('.')}")
        elif title_str:
            vis_parts.append(title_str)
        elif summary_str:
            vis_parts.append(summary_str.rstrip("."))

        for key in ("silhouette_cue", "material_dominant", "material_language", "lighting_mood"):
            val = fm_visual.get(key)
            if isinstance(val, str) and val.strip():
                vis_parts.append(val.strip().rstrip("."))
        sig = fm_visual.get("signature_features")
        if isinstance(sig, list):
            feats = [str(x).strip().rstrip(".") for x in sig if str(x).strip()]
            if feats:
                vis_parts.append("Signature features: " + ", ".join(feats))
        elif isinstance(sig, str) and sig.strip():
            vis_parts.append(sig.strip().rstrip("."))

        if len(vis_parts) >= 2 or (vis_parts and any(k in fm_visual for k in ("silhouette_cue", "signature_features"))):
            prompt_txt = ". ".join(vis_parts).strip()
            if not prompt_txt.endswith("."):
                prompt_txt += "."
            return " ".join(prompt_txt.split()), "frontmatter:visual"

    # Parse markdown `# Title` and `##` sections
    h1_title = ""
    sections: list[tuple[str, list[str]]] = []
    preamble_lines: list[str] = []
    cur_heading: str | None = None
    cur_buf: list[str] = []

    for ln in body.splitlines():
        stripped = ln.strip()
        if stripped.startswith("# ") and not h1_title:
            raw_h1 = stripped[2:].strip()
            raw_h1 = re.sub(r"\s*\([^)]*\)\s*$", "", raw_h1).strip()
            h1_title = raw_h1
            continue
        if stripped.startswith("## "):
            if cur_heading is not None:
                sections.append((cur_heading, cur_buf))
            cur_heading = stripped[3:].strip()
            cur_buf = []
            continue
        if stripped.startswith("### "):
            continue
        if cur_heading is None:
            preamble_lines.append(ln)
        else:
            cur_buf.append(ln)
    if cur_heading is not None:
        sections.append((cur_heading, cur_buf))

    # Rule 3: Visual / appearance section
    for heading, buf in sections:
        if _VISUAL_HEADING_RE.search(heading):
            sec_text = _clean_prose_text("\n".join(buf))
            if sec_text:
                prefix = f"{h1_title}. " if h1_title and not sec_text.lower().startswith(h1_title.lower()) else ""
                return f"{prefix}{sec_text}".strip(), "section:visual"

    # Rule 4: At a glance section
    for heading, buf in sections:
        if _AT_A_GLANCE_RE.search(heading):
            sec_text = _clean_prose_text("\n".join(buf))
            if sec_text:
                prefix = f"{h1_title}. " if h1_title and not sec_text.lower().startswith(h1_title.lower()) else ""
                return f"{prefix}{sec_text}".strip(), "section:at_a_glance"

    # Rule 5: First non-empty prose paragraph in preamble or first section
    first_para_lines: list[str] = []
    for candidate_lines in (preamble_lines, *(buf for _, buf in sections)):
        first_para_lines = []
        in_fence = False
        for ln in candidate_lines:
            s = ln.strip()
            if s.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if not s:
                if first_para_lines:
                    break
                continue
            if s.startswith(("#", "|")):
                continue
            first_para_lines.append(ln)
        if first_para_lines:
            para_text = _clean_prose_text("\n".join(first_para_lines))
            if para_text:
                prefix = f"{h1_title}. " if h1_title and not para_text.lower().startswith(h1_title.lower()) else ""
                return f"{prefix}{para_text}".strip(), "body:first_paragraph"

    raise CanonJobsError("CANON_PROMPT_EMPTY", f"entry {entry_id!r} yielded no extractable prompt text")


def _safe_job_slug(entry_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", entry_id.strip()).strip("_.-")
    return slug or "job"


def _parse_lora_specs(specs: list[str] | None) -> list[dict[str, Any]]:
    loras: list[dict[str, Any]] = []
    for raw in specs or []:
        part = raw.strip()
        if not part:
            continue
        if ":" in part:
            name, w_str = part.rsplit(":", 1)
            try:
                weight = float(w_str)
            except ValueError:
                raise CanonJobsError("CANON_LORA_INVALID", f"invalid LoRA weight in {raw!r}") from None
        else:
            name, weight = part, 1.0
        if not name.strip():
            raise CanonJobsError("CANON_LORA_INVALID", f"empty LoRA name in {raw!r}")
        loras.append({"name": name.strip(), "weight": weight})
    return loras


def build_jobs_from_canon(
    *,
    canon_dir: Path,
    canon_commit: str,
    entry_ids: list[str],
    out_path: Path,
    sha256_out: Path | None = None,
    run_id: str | None = None,
    template_id: str = "qwen_txt2img_lora",
    seeds: list[int] | None = None,
    width: int = 1024,
    height: int = 1024,
    steps: int = 28,
    cfg: float = 3.5,
    shift: float = 3.1,
    negative: str = "",
    style_prefix: str = "",
    unet_name: str = DEFAULT_UNET_NAME,
    clip_name: str = DEFAULT_CLIP_NAME,
    vae_name: str = DEFAULT_VAE_NAME,
    loras: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build `jobs.jsonl` from `canon_dir` at `canon_commit` for `entry_ids` and return summary."""
    cleaned_entries = [e.strip() for e in entry_ids if isinstance(e, str) and e.strip()]
    if not cleaned_entries:
        raise CanonJobsError("CANON_ENTRIES_EMPTY", "at least one entry id is required")
    if template_id not in l1.REAL_MODEL_TEMPLATES:
        raise CanonJobsError(
            "JOB_TEMPLATE_INVALID",
            f"template_id {template_id!r} must be one of {sorted(l1.REAL_MODEL_TEMPLATES)}",
        )

    active_seeds = list(seeds) if seeds else [42]
    if any(isinstance(s, bool) or not isinstance(s, int) for s in active_seeds):
        raise CanonJobsError("RENDER_JOB_INVALID", "seeds must be integers")

    repo_root, canon_rel_posix, canon_sha = resolve_canon_repo_and_commit(canon_dir, canon_commit)
    tree_files = _list_canon_tree_files(repo_root, canon_sha, canon_rel_posix)
    effective_run_id = (run_id or "").strip() or f"run_qwen2512_{canon_sha[:8]}"

    jobs: list[dict[str, Any]] = []
    seen_job_ids: set[str] = set()
    multi_seed = len(active_seeds) > 1

    for raw_entry_id in cleaned_entries:
        canonical_entry_id, git_rel_path = _resolve_entry_git_path(raw_entry_id, tree_files, canon_rel_posix)
        blob_bytes = _git_bytes(repo_root, ["cat-file", "blob", f"{canon_sha}:{git_rel_path}"])
        entry_sha256 = "sha256:" + hashlib.sha256(blob_bytes).hexdigest()
        md_text = blob_bytes.decode("utf-8", errors="replace")
        extracted_prompt, prompt_source = extract_prompt_from_markdown(md_text, entry_id=canonical_entry_id)

        if style_prefix.strip():
            pfx = style_prefix.strip().rstrip(".")
            final_prompt = f"{pfx}. {extracted_prompt}"
        else:
            final_prompt = extracted_prompt

        base_slug = _safe_job_slug(canonical_entry_id)
        for seed_val in active_seeds:
            job_id = f"{base_slug}_s{seed_val}" if multi_seed else base_slug
            if job_id in seen_job_ids:
                raise CanonJobsError("CANON_DUPLICATE_ENTRY", f"duplicate job_id {job_id!r} from entry {raw_entry_id!r}")
            seen_job_ids.add(job_id)

            model_pins: dict[str, Any] = {
                "base_repo": l1.PINNED_BASE_MODEL_REPO,
                "base_revision": l1.PINNED_BASE_MODEL_REVISION,
                "repack_repo": l1.PINNED_COMFY_REPACK_REPO,
                "repack_revision": l1.PINNED_COMFY_REPACK_REVISION,
                "base": {"name": unet_name},
                "text_encoder": {"name": clip_name},
                "vae": {"name": vae_name},
            }
            job: dict[str, Any] = {
                "job_id": job_id,
                "run_id": effective_run_id,
                "template_id": template_id,
                "prompt": final_prompt,
                "prompt_rule": PROMPT_EXTRACTION_RULE,
                "prompt_source": prompt_source,
                "negative": negative,
                "seed": int(seed_val),
                "width": int(width),
                "height": int(height),
                "steps": int(steps),
                "cfg": float(cfg),
                "shift": float(shift),
                "canon_sha": canon_sha,
                "canon_licence": CANON_TEXT_LICENCE,
                "entry_id": canonical_entry_id,
                "entry_sha256": entry_sha256,
                "owner": PICTURE_OWNER,
                "licence": PICTURE_LICENCE,
                "credit": PICTURE_CREDIT,
                "model_pins": model_pins,
            }
            if loras:
                job["loras"] = list(loras)
            wf = l1.build_qwen_lora_graph(job)
            wf_canonical = json.dumps(wf, sort_keys=True, separators=(",", ":")).encode("utf-8")
            job["workflow_sha"] = l1.sha256_bytes(wf_canonical)
            jobs.append(job)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(j, ensure_ascii=False) + "\n" for j in jobs)
    out_path.write_text(body, encoding="utf-8", newline="\n")
    jobs_sha256 = l1.sha256_file(out_path)[7:]

    # Validate through Lane 1's own render-jobs gate before returning.
    l1.validate_render_jobs(out_path, jobs_sha256)

    if sha256_out is not None:
        sha256_out.parent.mkdir(parents=True, exist_ok=True)
        sha256_out.write_text(f"{jobs_sha256}\n", encoding="utf-8", newline="\n")

    return {
        "jobs_path": str(out_path),
        "jobs_sha256": jobs_sha256,
        "job_count": len(jobs),
        "canon_sha": canon_sha,
        "canon_licence": CANON_TEXT_LICENCE,
        "licence": PICTURE_LICENCE,
        "credit": PICTURE_CREDIT,
        "prompt_rule": PROMPT_EXTRACTION_RULE,
    }


def _read_entries_file(path: Path) -> list[str]:
    if not path.is_file():
        raise CanonJobsError("CANON_ENTRIES_FILE_MISSING", f"{path} does not exist")
    items: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        items.append(s)
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Lane 1 jobs.jsonl from a git-committed canon folder")
    parser.add_argument("--canon-dir", type=Path, required=True, help="Canon directory inside a git repository")
    parser.add_argument("--canon-commit", required=True, help="Git commit SHA or ref of the canon repository")
    parser.add_argument("--entry", action="append", default=[], help="Entry id (repeatable, e.g. ships/brig)")
    parser.add_argument("--entries-file", type=Path, default=None, help="Newline-delimited file of entry ids")
    parser.add_argument("--out", type=Path, required=True, help="Output jobs.jsonl path")
    parser.add_argument("--sha256-out", type=Path, default=None, help="Optional file to write 64-hex jobs_sha256")
    parser.add_argument("--run-id", default=None, help="Run identifier (default: run_qwen2512_<canon_sha[:8]>)")
    parser.add_argument("--template-id", default="qwen_txt2img_lora", help="Real-model template_id")
    parser.add_argument("--seed", type=int, action="append", dest="seeds", default=None, help="Seed(s) per entry")
    parser.add_argument("--width", type=int, default=1024, help="Image width in pixels")
    parser.add_argument("--height", type=int, default=1024, help="Image height in pixels")
    parser.add_argument("--steps", type=int, default=28, help="Sampler steps")
    parser.add_argument("--cfg", type=float, default=3.5, help="CFG guidance scale")
    parser.add_argument("--shift", type=float, default=3.1, help="AuraFlow shift")
    parser.add_argument("--negative", default="", help="Negative prompt")
    parser.add_argument("--style-prefix", default="", help="Optional style prefix prepended to extracted prompts")
    parser.add_argument("--unet-name", default=DEFAULT_UNET_NAME, help="ComfyUI UNETLoader safetensors filename")
    parser.add_argument("--clip-name", default=DEFAULT_CLIP_NAME, help="ComfyUI CLIPLoader safetensors filename")
    parser.add_argument("--vae-name", default=DEFAULT_VAE_NAME, help="ComfyUI VAELoader safetensors filename")
    parser.add_argument("--lora", action="append", default=[], help="Optional LoRA spec name.safetensors[:weight]")
    args = parser.parse_args(argv)

    try:
        entries = list(args.entry or [])
        if args.entries_file is not None:
            entries.extend(_read_entries_file(args.entries_file))
        loras = _parse_lora_specs(args.lora)
        summary = build_jobs_from_canon(
            canon_dir=args.canon_dir,
            canon_commit=args.canon_commit,
            entry_ids=entries,
            out_path=args.out,
            sha256_out=args.sha256_out,
            run_id=args.run_id,
            template_id=args.template_id,
            seeds=args.seeds,
            width=args.width,
            height=args.height,
            steps=args.steps,
            cfg=args.cfg,
            shift=args.shift,
            negative=args.negative,
            style_prefix=args.style_prefix,
            unet_name=args.unet_name,
            clip_name=args.clip_name,
            vae_name=args.vae_name,
            loras=loras,
        )
    except CanonJobsError as exc:
        print(f"REFUSED: {exc.code}: {exc.detail}", file=sys.stderr, flush=True)
        return 1
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None)
        detail = getattr(exc, "detail", None)
        if code and detail:
            print(f"REFUSED: {code}: {detail}", file=sys.stderr, flush=True)
            return 1
        print(f"REFUSED: CANON_JOBS_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1

    print("JOBS_BUILT " + json.dumps(summary), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
