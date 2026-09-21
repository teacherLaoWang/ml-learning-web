"""算法实现的分发与参数清洗。

每个 ready 算法在 app/ml/{key}.py 里实现：

    def run(params: dict, seed: int, steps: int) -> dict
        # 返回 {key, backend, steps, seed, params, metrics, series, table, visuals}
        # visuals 的每一项必须落在 docs/API-CONTRACT.md §2 声明的 kind 内
"""

from __future__ import annotations

import importlib
import math
from typing import Any

from app.content import catalog

VISIBLE_KINDS = {"surface3d", "cloud3d", "vector3d", "line2d", "bars", "matrix", "tree2d"}


class ParamError(ValueError):
    pass


def spec_of(key: str) -> list[dict[str, Any]]:
    if key not in catalog.PARAM_SPECS:
        raise ParamError(f"算法「{key}」还没有可交互的仿真实现")
    return catalog.PARAM_SPECS[key]


def coerce_params(key: str, raw: dict[str, Any] | None) -> dict[str, Any]:
    """按目录里的参数规格做默认值回填、类型转换与越界钳制。"""
    raw = raw or {}
    out: dict[str, Any] = {}
    for p in spec_of(key):
        pid, typ = p["id"], p.get("type", "number")
        val = raw.get(pid, p["default"])
        try:
            if typ in ("int", "choice"):
                v = round(float(val))
            else:
                v = float(val)
        except (TypeError, ValueError):
            raise ParamError(f"参数「{p['label']}」不是合法数字：{val!r}") from None
        if not math.isfinite(v):
            raise ParamError(f"参数「{p['label']}」不能是 NaN/Infinity")
        lo, hi = float(p["min"]), float(p["max"])
        if typ in ("int", "choice"):
            v = int(max(int(lo), min(int(hi), round(v))))
        else:
            v = round(max(lo, min(hi, v)), 6)
        out[pid] = v
    extra = set(raw) - set(out)
    if extra:
        out["_ignored"] = sorted(extra)
    return out


def clamp_steps(steps: Any, default: int = 150) -> int:
    try:
        v = int(steps)
    except (TypeError, ValueError):
        v = default
    return max(8, min(400, v))


def run(key: str, params: dict[str, Any], seed: int, steps: int) -> dict[str, Any]:
    try:
        mod = importlib.import_module(f"app.ml.{key}")
    except ModuleNotFoundError as exc:
        raise ParamError(f"算法「{key}」的仿真模块尚未就绪（app/ml/{key}.py 缺失）") from exc
    fn = getattr(mod, "run", None)
    if fn is None:
        raise ParamError(f"app/ml/{key}.py 没有实现 run(params, seed, steps)")
    out = fn(params, seed, steps)
    return normalize(key, out)


def normalize(key: str, out: dict[str, Any]) -> dict[str, Any]:
    """兜底：补默认字段、把非有限数字列成 null、丢掉前端不认的 visual kind。"""
    if not isinstance(out, dict):
        raise ParamError(f"app/ml/{key}.py 的 run() 返回了 {type(out).__name__}，应为 dict")
    out.setdefault("key", key)
    out.setdefault("backend", "numpy")
    out.setdefault("metrics", {})
    out.setdefault("series", [])
    out.setdefault("table", [])
    out["metrics"] = {k: _num(v) for k, v in out["metrics"].items()}
    visuals = []
    for v in out.get("visuals", []):
        kind = v.get("kind")
        if kind not in VISIBLE_KINDS:
            continue
        visuals.append(v)
    out["visuals"] = visuals
    wanted = [s["id"] for s in catalog.VISUAL_SPEC.get(key, [])]
    out["declaredVisuals"] = wanted
    out["missingVisuals"] = [w for w in wanted if w not in {v.get("id") for v in visuals}]
    return out


def _num(v: Any) -> Any:
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int,)):
        return v
    if isinstance(v, float):
        return None if not math.isfinite(v) else round(v, 6)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return None if not math.isfinite(f) else round(f, 6)
