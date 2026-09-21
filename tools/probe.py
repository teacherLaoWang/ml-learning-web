"""自检脚本：把每个 ready 算法真跑一遍，检查 visual 齐不齐、有没有 NaN/Inf/非原生类型。

用法：
    uv run python -m tools.probe                # 全部 ready 算法，默认参数
    uv run python -m tools.probe mlp cnn        # 只看指定算法
    uv run python -m tools.probe --sweep        # 每个算法的参数范围端点也跑一遍
"""

from __future__ import annotations

import json
import math
import sys
import time
from typing import Any

from app.content import catalog
from app.ml import registry


def walk(obj: Any, path: str = "$", bad: list[str] | None = None) -> list[str]:
    """递归检查：只允许 list/dict/str/int/float/bool/None，浮点必须有限。"""
    bad = bad if bad is not None else []
    if isinstance(obj, dict):
        for k, v in obj.items():
            walk(v, f"{path}.{k}", bad)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            walk(v, f"{path}[{i}]", bad)
    elif obj is None or isinstance(obj, (bool, str, int)):
        pass
    elif isinstance(obj, float):
        if not math.isfinite(obj):
            bad.append(f"{path}={obj}")
    else:
        bad.append(f"{path}:{type(obj).__name__} 不是原生 JSON 类型")
    return bad


def size_of(obj: Any) -> int:
    return len(json.dumps(obj, ensure_ascii=False))


def run_one(key: str, params: dict[str, Any], steps: int = 150) -> dict[str, Any]:
    t0 = time.perf_counter()
    out = registry.run(key, params, seed=7, steps=steps)
    ms = (time.perf_counter() - t0) * 1000
    payload = {k: v for k, v in out.items() if k not in ("declaredVisuals", "missingVisuals")}
    bad = walk(payload)
    got = {v.get("id") for v in out["visuals"]}
    kinds = {v.get("id"): v.get("kind") for v in out["visuals"]}
    want = {s["id"]: s["kind"] for s in catalog.VISUAL_SPEC[key]}
    wrong_kind = [i for i, k in kinds.items() if want.get(i) != k]
    return {
        "key": key,
        "ms": round(ms, 1),
        "bytes": size_of(payload),
        "backend": out["backend"],
        "missing": out["missingVisuals"],
        "extra": sorted(got - set(want)),
        "wrongKind": wrong_kind,
        "nonFinite": bad[:6],
        "metrics": {k: v for k, v in out["metrics"].items() if v is not None},
    }


def main(argv: list[str]) -> int:
    sweep = "--sweep" in argv
    keys = [a for a in argv if not a.startswith("--")] or catalog.READY_KEYS
    problems = 0
    for key in keys:
        defaults = {p["id"]: p["default"] for p in catalog.PARAM_SPECS[key]}
        cases: list[tuple[str, dict[str, Any]]] = [("默认", defaults)]
        if sweep:
            for p in catalog.PARAM_SPECS[key]:
                for edge, val in (("min", p["min"]), ("max", p["max"])):
                    cases.append((f"{p['id']}={edge}", {**defaults, p["id"]: val}))
        for label, params in cases:
            try:
                r = run_one(key, params)
            except Exception as exc:
                print(f"✗ {key} [{label}] 抛异常 {type(exc).__name__}: {exc}")
                problems += 1
                continue
            flags = []
            if r["missing"]:
                flags.append(f"缺 visual {r['missing']}")
            if r["extra"]:
                flags.append(f"多余 visual {r['extra']}")
            if r["wrongKind"]:
                flags.append(f"kind 不符 {r['wrongKind']}")
            if r["nonFinite"]:
                flags.append(f"非法数值 {r['nonFinite']}")
            mark = "✗" if flags else "✓"
            print(f"{mark} {key:8s} {label:22s} {r['ms']:7.1f}ms {r['bytes']/1024:6.1f}KB "
                  f"backend={r['backend']:5s} metrics={r['metrics']}")
            for f in flags:
                print(f"    ↳ {f}")
                problems += 1
    print(f"\n共 {problems} 个问题")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
