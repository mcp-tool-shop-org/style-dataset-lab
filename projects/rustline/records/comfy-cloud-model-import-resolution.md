# Comfy Cloud model import — how names resolve, and the trap

> Learned the hard way 2026-08-22, across several failed build attempts by the Comfy Agent. None of
> this is in the Comfy docs. Read it before wiring any graph against an imported LoRA.

## The resolver form is `<hf-owner>__<repo>__<filename>` — double underscore

An imported model does **not** appear under its bare filename, and **not** under a slash-namespaced
path. It appears as the HF owner, the repo, and the filename joined by **double underscores**:

```
SaintEloi__rustline-lora__rustline_v3ckpt_1500.safetensors
```

Not `rustline_v3ckpt_1500.safetensors`. Not `mikeyfrilot/rustline-lora/rustline_v3ckpt_1500.safetensors`.
Both of those were tried and both rejected.

## ⚠ The HF owner is the CANONICAL namespace, which may not be the one you typed

`mikeyfrilot/rustline-lora` and `SaintEloi/rustline-lora` are **the same private repo** —
`SaintEloi` is the canonical namespace and `mikeyfrilot` redirects to it (HF does this after a
rename). `huggingface_hub` follows the redirect silently, so uploads to the `mikeyfrilot` path land
correctly and `repo_info()` on it returns the files — giving no hint that the canonical owner
differs.

**But Comfy Cloud registers the model under the CANONICAL owner.** So the resolver string uses
`SaintEloi`, and every guess built from the URL you actually typed will fail.

**Check the canonical owner before predicting a resolver name:**

```python
from huggingface_hub import HfApi
print(HfApi().repo_info("<owner>/<repo>", repo_type="model").author)
```

## ⚠ THE TRAP: `search_models` and the node combo are DIFFERENT surfaces and can disagree

This is what actually cost the time.

| surface | what it is | saw the import? |
|---|---|---|
| `search_models(q="rustline")` | the **model catalog** | ✅ yes |
| `get_node(["LoraLoaderModelOnly"])` → `lora_name` options | the **build resolver** the graph runs against | ❌ no — 647 entries, zero rustline |

A successfully imported model lands in the catalog **immediately** and in the node combo **later**.
An already-open build session enumerates a stale combo, so a rig wired against a catalog-confirmed
name rejects at run.

**The combo is the one that governs whether a graph runs.** Catalog presence is not sufficient.

**Fix: reload the editor / start a fresh session** to repopulate the combo. Nothing inside the open
session can force it.

**Diagnosis, when a name won't resolve:** if `search_models` finds it and the combo does not, the
import landed and it is a propagation gap → reload. If **neither** finds it, the import never
happened → do the Model Library import.

## Uploading to HF is NOT importing into Comfy Cloud

Two separate steps, and the second is a **manual browser action** nobody can perform via API:

1. Push `.safetensors` to a HF repo.
2. **Comfy Cloud → Model Library → Import** → paste the HF file link → set type **LoRA**, target
   folder **loras** → wait for the download.

Step 2 was silently skipped for a whole round here because step 1 finishing looked like completion.

Private repos additionally need an HF token saved in **Comfy Cloud → Secrets**, or the import 401s.

## Settled facts

- **Creator tier is confirmed working on this account** — an import succeeded, so tier is not a
  blocker.
- **The catalog's `recommended.loader` hint is WRONG for LoRAs.** The rustline entry advertises
  `CheckpointLoaderSimple`. It is a LoRA — wire it through `LoraLoaderModelOnly` and ignore the hint.
- Import accepts `.safetensors` only, effectively no size cap (100 GB), and imports are private to
  the account.

## Current rustline state on Comfy Cloud

| checkpoint | on HF | imported | in combo |
|---|---|---|---|
| `rustline_v3ckpt_1500` | ✅ | ✅ | ❌ awaiting reload |
| `rustline_v5ckpt_1000` | ✅ | ❌ | ❌ |
| `rustline_v5ckpt_1250` | ✅ | ❌ | ❌ |
| `rustline_v5ckpt_1500` | ✅ | ❌ | ❌ |
| `rustline_v5ckpt_1750` | ✅ | ❌ | ❌ |

Repo: `SaintEloi/rustline-lora` (private, author `mikeyfrilot`).

## Related

The reason any of this matters is that Comfy Cloud can *import* a LoRA but cannot *export* one —
see [`comfy-cloud-lora-export-request.md`](comfy-cloud-lora-export-request.md). Generation runs on
Cloud from an imported adapter; training stays on the rented ai-toolkit box that produced v4 and v5.
