"""Stand-in for the lane's torch on the fake GPU VM: just the calls lane3_rung.gpu_smoke makes.

FAKE_VM_GPU_SMOKE=no_cuda makes torch.cuda.is_available() False (a driver the cu13x wheel cannot use).
"""

from __future__ import annotations

import os

__version__ = "2.15.0+cu130"
bfloat16 = "bfloat16"


class _Version:
    cuda = "13.0"


version = _Version()


class _Cuda:
    @staticmethod
    def is_available() -> bool:
        return os.environ.get("FAKE_VM_GPU_SMOKE") != "no_cuda"

    @staticmethod
    def get_device_name(index: int = 0) -> str:
        return os.environ.get("FAKE_VM_GPU_NAME", "NVIDIA A100-SXM4-80GB")

    @staticmethod
    def synchronize() -> None:
        return None


cuda = _Cuda()


def device(name: str) -> str:
    return name


class _Bool:
    def __init__(self, value: bool) -> None:
        self.value = value

    def all(self) -> bool:
        return self.value

    def any(self) -> bool:
        return self.value

    def __bool__(self) -> bool:
        return self.value


class Tensor:
    def __init__(self, value: float = 1.0) -> None:
        self.value = value

    def __matmul__(self, other: "Tensor") -> "Tensor":
        return Tensor(self.value * other.value)

    def __pow__(self, n: int) -> "Tensor":
        return Tensor(self.value**n)

    def __ne__(self, other: object) -> _Bool:  # type: ignore[override]
        return _Bool(isinstance(other, Tensor) and self.value != other.value)

    def float(self) -> "Tensor":
        return Tensor(self.value)

    def mean(self) -> "Tensor":
        return Tensor(self.value)

    def backward(self) -> None:
        return None

    def detach(self) -> "Tensor":
        return self

    def clone(self) -> "Tensor":
        return Tensor(self.value)


def randn(*_shape: int, device: str | None = None, dtype: str | None = None) -> Tensor:
    return Tensor(0.5)


def isfinite(_t: Tensor) -> _Bool:
    return _Bool(True)


class _NN:
    @staticmethod
    def Parameter(t: Tensor) -> Tensor:  # noqa: N802 - torch's name
        return t


nn = _NN()
