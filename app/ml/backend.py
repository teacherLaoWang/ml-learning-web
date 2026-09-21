"""后端内核探测：PyTorch 是可选 extra，装了就用，没装自动退回 NumPy。"""

from __future__ import annotations

import importlib.metadata as md
import platform
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def torch_state() -> dict[str, Any]:
    try:
        import torch  # type: ignore
    except Exception:
        return {"available": False, "version": None, "device": None}
    try:
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"
    except Exception:
        device = "cpu"
    return {"available": True, "version": torch.__version__, "device": device}


def env_payload() -> dict[str, Any]:
    try:
        numpy_v = md.version("numpy")
    except Exception:
        numpy_v = None
    st = torch_state()
    hint = None if st["available"] else "真训练内核未安装：uv sync --extra ml（不装也能跑，全部演示走 NumPy 实现）"
    return {
        "python": platform.python_version(),
        "numpy": numpy_v,
        "torch": st,
        "hint": hint,
    }
