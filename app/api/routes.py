"""HTTP 层：只做参数校验、错误翻译成中文、以及把 numpy 结果转成纯 JSON。"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.content import catalog, loader
from app.ml import backend, registry

router = APIRouter(prefix="/api")


class FitRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    seed: int = 7
    steps: int = 150


@router.get("/env")
def get_env() -> dict[str, Any]:
    return backend.env_payload()


@router.get("/catalog")
def get_catalog() -> dict[str, Any]:
    return catalog.catalog_payload()


@router.get("/glossary")
def get_glossary() -> dict[str, Any]:
    rows = loader.glossary()
    return {"terms": rows, "count": len(rows)}


@router.get("/algorithms")
def list_algorithms() -> dict[str, Any]:
    return {"items": [
        {"key": l["key"], "name": l["name"], "tagline": l["tagline"], "family": l["family"],
         "familyName": l["familyName"], "color": l["color"], "difficulty": l["difficulty"],
         "tags": l["tags"], "status": l["status"]}
        for l in (loader.payload(k) for k in sorted(catalog.PARAM_SPECS))
    ]}


@router.get("/algorithms/{key}")
def get_algorithm(key: str) -> dict[str, Any]:
    try:
        return loader.payload(key)
    except KeyError:
        raise HTTPException(404, f"没有这个算法：{key}") from None


def _fit(key: str, req: FitRequest) -> dict[str, Any]:
    try:
        params = registry.coerce_params(key, req.params)
    except registry.ParamError as exc:
        raise HTTPException(400, str(exc)) from exc
    steps = registry.clamp_steps(req.steps)
    t0 = time.perf_counter()
    try:
        out = registry.run(key, params, int(req.seed) % 100000, steps)
    except registry.ParamError as exc:
        raise HTTPException(501, str(exc)) from exc
    except Exception as exc:  # 数值炸了也要给中文可读的提示
        raise HTTPException(422, f"训练失败：{type(exc).__name__}: {exc}") from exc
    out["elapsedMs"] = round((time.perf_counter() - t0) * 1000, 2)
    out["seed"] = int(req.seed) % 100000
    out["steps"] = steps
    out["params"] = {k: v for k, v in params.items() if k != "_ignored"}
    return out


@router.post("/algorithms/{key}/fit")
def post_fit(key: str, req: FitRequest) -> dict[str, Any]:
    if key not in catalog.PARAM_SPECS:
        raise HTTPException(404, f"算法「{key}」暂无仿真实现")
    return _fit(key, req)


@router.post("/algorithms/{key}/step")
def post_step(key: str, req: FitRequest) -> dict[str, Any]:
    """单步推进：轨迹可复现（同 seed 同轨迹），所以直接重算到第 steps 步即可。"""
    if key not in catalog.PARAM_SPECS:
        raise HTTPException(404, f"算法「{key}」暂无仿真实现")
    res = _fit(key, req)
    res["resumed"] = True
    return res
