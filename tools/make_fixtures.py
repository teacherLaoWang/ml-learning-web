"""用后端真实输出重新生成前端离线 fixture（mock 模式的数据源）。

手动写 fixture 一定会和后端飘走，所以这里只做一件事：
拿默认参数跑一遍 registry.run，按「够看、够小」的规则降采样，写回 frontend/src/fixtures/。

用法：
    uv run python -m tools.make_fixtures            # 生成全部 ready 算法
    uv run python -m tools.make_fixtures mlp cnn    # 只生成指定算法
同时刷新 frontend/src/fixtures/_meta/{catalog,specs,lessons}.json。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from app.content import catalog, loader
from app.ml import backend, registry

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "frontend" / "src" / "fixtures"

MAX_GRID = 33      # 曲面网格边长上限
MAX_PATH = 80      # 轨迹点数上限
MAX_POINTS = 220   # 散点数上限
MAX_SERIES = 80    # 曲线点数上限
STEPS = 150        # fixture 固定步数（mock 也要能看到完整收敛过程）


def stride(n: int, cap: int) -> int:
    return 1 if n <= cap else -(-n // cap)


def pick(seq: list[Any], cap: int) -> list[Any]:
    s = stride(len(seq), cap)
    out = seq[::s]
    if seq and out[-1] is not seq[-1]:
        out.append(seq[-1])          # 永远保留最后一点（收敛态）
    return out


def thin_grid(g: dict[str, Any]) -> dict[str, Any]:
    xs, ys, zs = g["x"], g["y"], g["z"]
    sx, sy = stride(len(xs), MAX_GRID), stride(len(ys), MAX_GRID)
    nx = xs[::sx]
    return {"x": nx, "y": ys[::sy], "z": [row[::sx] for row in zs[::sy]]}


def thin_visual(v: dict[str, Any]) -> dict[str, Any]:
    d = dict(v.get("data") or {})
    if isinstance(d.get("grid"), dict):
        d["grid"] = thin_grid(d["grid"])
    if isinstance(d.get("path"), list):
        d["path"] = pick(d["path"], MAX_PATH)
    if isinstance(d.get("points"), list):
        d["points"] = pick(d["points"], MAX_POINTS)
    bound = d.get("boundary")
    if isinstance(bound, dict) and isinstance(bound.get("grid"), dict):
        bound = dict(bound)
        bound["grid"] = thin_grid(bound["grid"])
        d["boundary"] = bound
    for key in ("curves",):
        if isinstance(d.get(key), list):
            d[key] = [{**c, "x": pick(c["x"], MAX_SERIES), "y": pick(c["y"], MAX_SERIES)}
                      if isinstance(c, dict) and isinstance(c.get("x"), list) else c
                      for c in d[key]]
    return {**v, "data": d}


def thin_series(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for s in series:
        if isinstance(s.get("x"), list) and isinstance(s.get("y"), list):
            n = stride(len(s["x"]), MAX_SERIES)
            out.append({**s, "x": s["x"][::n], "y": s["y"][::n]})
        else:
            out.append(s)
    return out


def make(key: str) -> int:
    defaults = {p["id"]: p["default"] for p in catalog.PARAM_SPECS[key]}
    t0 = time.perf_counter()
    payload = registry.run(key, defaults, seed=7, steps=STEPS)
    elapsed = round((time.perf_counter() - t0) * 1000, 2)
    fixture = {
        "key": payload["key"],
        "backend": payload["backend"],
        "mock": True,
        "params": defaults,
        "seed": 7,
        "steps": STEPS,
        "elapsedMs": elapsed,
        "metrics": payload["metrics"],
        "series": thin_series(payload["series"]),
        "table": payload["table"],
        "visuals": [thin_visual(v) for v in payload["visuals"]],
        "declaredVisuals": payload["declaredVisuals"],
    }
    FIX.mkdir(parents=True, exist_ok=True)
    path = FIX / f"{key}.json"
    path.write_text(json.dumps(fixture, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return path.stat().st_size


def make_meta() -> None:
    """_meta 三个文件的形状由 frontend/src/mock/offline.ts 决定，不能随意改。"""
    meta = FIX / "_meta"
    meta.mkdir(parents=True, exist_ok=True)

    env = backend.env_payload()
    env["hint"] = "离线演示数据（mock）：真实环境请启动后端。装可选内核：uv sync --extra ml"
    text_fields = ("name", "tagline", "story", "formula", "intuition", "derivation",
                   "terms", "pitfalls", "presets", "seeAlso", "quiz")

    # 离线路径下概念卡片靠 catalog 里的 concept 兜底（在线时前端会另取 /api/algorithms/{key}），
    # 所以只给 outline 条目带上，且只带卡片真正会渲染的字段，避免把 /api/catalog 撑大。
    def concept_of(key: str) -> dict[str, Any]:
        p = loader.payload(key)
        return {"story": p.get("story", ""), "intuition": p.get("intuition", [])[:3],
                "formula": p.get("formula", {"text": "", "vars": []}),
                "terms": p.get("terms", []), "pitfalls": p.get("pitfalls", [])[:3],
                "seeAlso": p.get("seeAlso", [])}

    families = []
    concepts: dict[str, Any] = {}
    for fam in catalog.catalog_payload()["families"]:
        items = []
        for it in fam["items"]:
            if it["status"] != "ready":
                concepts[it["key"]] = concept_of(it["key"])
            items.append(it)
        families.append({**fam, "items": items})

    meta = FIX / "_meta"
    meta.mkdir(parents=True, exist_ok=True)
    files = {
        "catalog.json": {"env": env, "families": families},
        "concepts.json": concepts,
        "specs.json": {"paramSpecs": catalog.PARAM_SPECS,
                       "visualSpecs": catalog.VISUAL_SPEC,
                       "metricSpecs": catalog.METRIC_SPEC},
        "lessons.json": {k: {f: loader.payload(k)[f] for f in text_fields} for k in catalog.READY_KEYS},
    }
    for name, obj in files.items():
        (meta / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    keys = [a for a in argv if not a.startswith("-")] or catalog.READY_KEYS
    total = 0
    for key in keys:
        size = make(key)
        total += size
        print(f"✓ {key:8s} {size / 1024:6.1f}KB")
    make_meta()
    print(f"合计 {total / 1024:.0f}KB（全部按 import.meta.glob 懒加载，不进主包）+ _meta 已刷新")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
