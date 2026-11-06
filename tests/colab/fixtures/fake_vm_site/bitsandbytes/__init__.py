"""Stand-in for bitsandbytes on the fake GPU VM.

FAKE_VM_GPU_SMOKE=bnb_fail makes the AdamW8bit step raise the way a CUDA binary that does not match
the driver does.
"""

from __future__ import annotations

import os

__version__ = "0.50.2"


class _AdamW8bit:
    def __init__(self, params: list, lr: float = 1e-3) -> None:
        self.params = params
        self.lr = lr

    def step(self) -> None:
        if os.environ.get("FAKE_VM_GPU_SMOKE") == "bnb_fail":
            raise RuntimeError("CUDA error: no kernel image is available for execution on the device")
        for p in self.params:
            p.value -= self.lr


class _Optim:
    AdamW8bit = _AdamW8bit


optim = _Optim()
