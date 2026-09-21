"""数值内核层的公共工具：契约负载构造 + 通用评估指标 + 数值清洗。

所有 `app/ml/{key}.py` 产出的 JSON 都经 `clean()` 走一遍：
NumPy 标量/数组 → 原生 Python 类型，NaN/Inf → 有限值（见 docs/API-CONTRACT.md §0）。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from app.content import catalog

ND = 6  # 浮点统一 round 到 6 位
MAX_ABS = 1e6  # 万一出现 Inf，钳到这个量级而不是抛异常
GRID = 45  # 网格分辨率（契约要求 41~61）
MAX_PATH = 240  # 轨迹点数上限（控制 JSON 体积）

# ---------------------------------------------------------------- 数值清洗


def clean(obj: Any, nd: int = ND) -> Any:
    """递归地把 NumPy 对象换成原生 JSON 值，并保证所有数有限。"""
    if isinstance(obj, np.ndarray):
        obj = obj.tolist()
    if isinstance(obj, dict):
        return {k: clean(v, nd) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v, nd) for v in obj]
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        if math.isnan(f):
            return 0.0
        if math.isinf(f):
            return MAX_ABS if f > 0 else -MAX_ABS
        return round(f, nd)
    try:  # torch.Tensor / Decimal 等：能转 float 就按数字处理，转不了就退化成字符串
        return clean(float(obj), nd)
    except Exception:
        return str(obj)


def num(x: Any, nd: int = ND) -> float:
    """单个安全的原生浮点（NaN→0，Inf→±MAX_ABS）。"""
    return clean(float(x), nd)  # type: ignore[return-value]


def metric(x: Any) -> float | None:
    """指标值：非有限就交给分发层转 null。"""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(f) else round(f, ND)


def finite_problems(obj: Any, path: str = "$") -> list[str]:
    """递归体检：列出 NaN/Inf/非原生类型/bool 之外的坏值（测试用）。"""
    bad: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                bad.append(f"{path}: 键不是字符串 {k!r}")
            bad += finite_problems(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        if isinstance(obj, tuple):
            bad.append(f"{path}: 残留 tuple，应为 list")
        for i, v in enumerate(obj):
            bad += finite_problems(v, f"{path}[{i}]")
    elif isinstance(obj, bool) or obj is None or isinstance(obj, str):
        pass
    elif isinstance(obj, float):
        if not math.isfinite(obj):
            bad.append(f"{path}: 非有限浮点 {obj}")
    elif isinstance(obj, int):
        pass
    else:
        bad.append(f"{path}: 非原生类型 {type(obj).__name__}")
    return bad


# ---------------------------------------------------------------- 采样


def rng(seed: int, salt: int = 0) -> np.random.Generator:
    """同 seed 完全可复现；salt 用于在同一算法内派生互不相关的流。"""
    return np.random.default_rng([int(seed), int(salt)])


def thin(seq: list[Any], cap: int = MAX_PATH) -> list[Any]:
    """等距抽稀，保留首尾（轨迹太长时前端也不需要每帧）。"""
    n = len(seq)
    if n <= cap:
        return seq
    idx = sorted({round(i * (n - 1) / (cap - 1)) for i in range(cap)})
    return [seq[i] for i in idx]



def ax(label: str, lo: float, hi: float) -> dict[str, Any]:
    return {"label": label, "min": num(min(lo, hi)), "max": num(max(lo, hi))}


def zlim(z: np.ndarray, lo: float | None = None, hi: float | None = None) -> tuple[float, float]:
    flat = np.asarray(z, dtype=float).ravel()
    flat = flat[np.isfinite(flat)]
    if flat.size == 0:
        return 0.0, 1.0
    a = float(lo if lo is not None else flat.min())
    b = float(hi if hi is not None else flat.max())
    if b - a < 1e-9:
        b = a + 1e-3
    return a, b


def surface(
    xg: np.ndarray | list[float],
    yg: np.ndarray | list[float],
    zg: np.ndarray,
    xlab: str,
    ylab: str,
    zlab: str,
    path: list[dict[str, Any]] | None = None,
    optimum: dict[str, Any] | None = None,
    markers: list[dict[str, Any]] | None = None,
    levels: list[float] | None = None,
    climax: str | None = None,
    window: dict[str, Any] | None = None,
    zlo: float | None = None,
    zhi: float | None = None,
) -> dict[str, Any]:
    """surface3d 负载：grid.z 形状固定为 [len(y)][len(x)]。"""
    xs = [round(float(v), ND) for v in np.asarray(xg, dtype=float).ravel()]
    ys = [round(float(v), ND) for v in np.asarray(yg, dtype=float).ravel()]
    Z = np.nan_to_num(np.asarray(zg, dtype=float), nan=0.0, posinf=MAX_ABS, neginf=-MAX_ABS)
    lo, hi = zlim(Z, zlo, zhi)
    out: dict[str, Any] = {
        "axes": {"x": ax(xlab, min(xs), max(xs)), "y": ax(ylab, min(ys), max(ys)),
                 "z": ax(zlab, lo, hi)},
        "grid": {"x": xs, "y": ys, "z": [[round(float(v), ND) for v in row] for row in Z]},
    }
    if levels is None and Z.size:
        levels = [lo + (hi - lo) * f for f in (0.2, 0.4, 0.6, 0.8)]
    if levels is not None:
        out["levels"] = [round(float(v), ND) for v in levels]
    if path:
        out["path"] = thin([clean(p) for p in path])
    if optimum:
        out["optimum"] = clean(optimum)
    if markers:
        out["markers"] = [clean(m) for m in markers]
    if climax:
        out["climaxNote"] = climax
    if window:
        out["window"] = clean(window)
    return out


def trace(x: float, y: float, z: float, step: int, grad: Any) -> dict[str, Any]:
    """surface3d 的轨迹点：必须带 step 与 grad。"""
    return {"x": num(x), "y": num(y), "z": num(z), "step": int(step),
            "grad": [num(g) for g in np.asarray(grad, dtype=float).ravel()]}


def marker(x: float, y: float, z: float, label: str, color: str = "#f97316") -> dict[str, Any]:
    return {"x": num(x), "y": num(y), "z": num(z), "label": label, "color": color}


PALETTE = ["#2563eb", "#ea580c", "#0d9488", "#db2777", "#7c3aed",
           "#4f46e5", "#16a34a", "#b45309", "#0891b2", "#be123c"]


def color_of(i: int) -> str:
    return PALETTE[int(i) % len(PALETTE)]


def point3(x: float, y: float, z: float, label: Any = 0, size: float = 1.0) -> dict[str, Any]:
    return {"x": num(x), "y": num(y), "z": num(z), "label": int(label) if isinstance(
        label, (int, np.integer)) else str(label), "size": num(size)}


def boundary(xg: Any, yg: Any, zg: Any, xlab: str, ylab: str, zlab: str,
             contour0: bool = True, level: float | None = None) -> dict[str, Any]:
    xs = [round(float(v), ND) for v in np.asarray(xg, dtype=float).ravel()]
    ys = [round(float(v), ND) for v in np.asarray(yg, dtype=float).ravel()]
    Z = np.asarray(zg, dtype=float)
    lo, hi = zlim(Z)
    return {
        "axes": {"x": ax(xlab, min(xs), max(xs)), "y": ax(ylab, min(ys), max(ys)),
                 "z": {"label": zlab, "min": num(lo), "max": num(hi)}},
        "grid": {"x": xs, "y": ys, "z": [[round(float(v), ND) for v in row]
                                         for row in np.nan_to_num(Z, nan=0.0, posinf=MAX_ABS, neginf=-MAX_ABS)]},
        "contour0": bool(contour0),
        **({"level": num(level)} if level is not None else {}),
    }



def cloud(points: list[dict[str, Any]], legend: list[dict[str, Any]] | None = None,
          bound: dict[str, Any] | None = None, projection: dict[str, Any] | None = None,
          hulls: list[dict[str, Any]] | None = None,
          centroids: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"points": thin(points, 420)}
    if legend:
        out["legend"] = legend
    if bound:
        out["boundary"] = bound
    if projection:
        out["projection"] = projection
    if hulls:
        out["hulls"] = hulls
    if centroids:
        out["centroids"] = centroids
    return out


def curve(cid: str, label: str, x: Any, y: Any, dash: bool = False,
          color: str | None = None) -> dict[str, Any]:
    xs = [round(float(v), ND) for v in np.asarray(x, dtype=float).ravel()]
    ys = [round(float(v), ND) for v in np.asarray(y, dtype=float).ravel()]
    return {"id": cid, "label": label, "x": xs, "y": ys, "dash": bool(dash),
            "color": color or color_of(hash(cid) % len(PALETTE))}


def lines2d(curves: list[dict[str, Any]], xlab: str, ylab: str,
            diagonal: bool = False, xr: tuple[float, float] | None = None,
            yr: tuple[float, float] | None = None) -> dict[str, Any]:
    xs = [v for c in curves for v in c["x"]]
    ys = [v for c in curves for v in c["y"]]
    if not xs:
        xs, ys = [0.0], [0.0]
    return {
        "curves": curves,
        "axes": {"x": ax(xlab, *(xr or (min(xs), max(xs)))),
                 "y": ax(ylab, *(yr or (min(ys), max(ys))))},
        "diagonal": bool(diagonal),
    }


def bars(labels: list[Any], values: Any, unit: str = "", ylab: str = "值",
         xlab: str = "") -> dict[str, Any]:
    vals = [round(float(v), ND) for v in np.asarray(values, dtype=float).ravel()]
    out: dict[str, Any] = {"labels": [str(l) for l in labels], "values": vals, "unit": unit,
                           "axes": {"y": ax(ylab, min(vals + [0.0]), max(vals + [1.0]))}}
    if xlab:
        out["axes"]["x"] = ax(xlab, 0, max(1, len(labels) - 1))
    return out


def matrix(labels: list[Any], rows: Any, title: str = "", percent: bool = False) -> dict[str, Any]:
    M = np.asarray(rows, dtype=float)
    return {"labels": [str(l) for l in labels],
            "rows": [[round(float(v), ND) for v in row] for row in M],
            "title": title, "percent": bool(percent)}


def tree2d(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    return {"nodes": [clean(n) for n in nodes], "edges": [clean(e) for e in edges]}


def node(nid: int, x: float, y: float, title: str, lines: list[str], leaf: bool) -> dict[str, Any]:
    return {"id": int(nid), "x": num(x), "y": num(y), "title": title,
            "lines": [str(s) for s in lines], "leaf": bool(leaf)}


def edge(src: int, dst: int, label: str = "") -> dict[str, Any]:
    return {"from": int(src), "to": int(dst), "label": str(label)}


def ser(cid: str, label: str, x: Any, y: Any, xlab: str = "step", ylab: str = "值") -> dict[str, Any]:
    xs = [round(float(v), ND) for v in np.asarray(x, dtype=float).ravel()]
    ys = [round(float(v), ND) for v in np.asarray(y, dtype=float).ravel()]
    return {"id": cid, "label": label, "x": xs, "y": ys, "xLabel": xlab, "yLabel": ylab}


def tab(tid: str, title: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = []
    for r in rows:
        row = {"name": str(r.get("name", ""))}
        for k in ("value", "truth", "delta", "note"):
            if r.get(k) is not None:
                row[k] = str(r[k])
        out.append(row)
    return {"id": tid, "title": title, "rows": out}


def visual(key: str, vid: str, data: dict[str, Any]) -> dict[str, Any]:
    """按 VISUAL_SPEC 生成一个 visual：id/kind/title/hint 全部对齐目录。"""
    spec = {s["id"]: s for s in catalog.VISUAL_SPEC[key]}
    if vid not in spec:
        raise ValueError(f"{key} 的 VISUAL_SPEC 里没有 visual「{vid}」，可选：{sorted(spec)}")
    return {"id": vid, "kind": spec[vid]["kind"], "title": spec[vid]["title"],
            "hint": spec[vid].get("hint", ""), "data": clean(data)}


def finish(key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """统一收尾：metrics 清洗 + visuals 对齐目录。

    payload 里的 `visuals` 允许写成 {id: data} 字典，顺序按 VISUAL_SPEC 排。
    """
    payload["metrics"] = {k: metric(v) for k, v in payload.get("metrics", {}).items()}
    vspec = [s["id"] for s in catalog.VISUAL_SPEC[key]]
    raw = payload.pop("visualMap", payload.get("visuals"))
    visuals: dict[str, dict[str, Any]] = {}
    if isinstance(raw, dict):
        for vid, data in raw.items():
            if isinstance(data, dict) and "kind" in data:  # 已是成品
                visuals[vid] = data
            else:
                visuals[vid] = visual(key, vid, data)
    elif isinstance(raw, list):
        for v in raw:
            visuals[str(v.get("id"))] = v
    payload["visuals"] = [visuals[v] for v in vspec if v in visuals] + \
                         [v for vid, v in visuals.items() if vid not in vspec]
    payload.setdefault("series", [])
    payload.setdefault("table", [])
    return payload


# ---------------------------------------------------------------- 评估指标


def accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y = np.asarray(y_true).ravel()
    p = np.asarray(y_pred).ravel()
    return float(np.mean(p == y)) if y.size else 0.0


def f1_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y = np.asarray(y_true).ravel()
    p = np.asarray(y_pred).ravel()
    tp = float(np.sum((p == 1) & (y == 1)))
    fp = float(np.sum((p == 1) & (y == 0)))
    fn = float(np.sum((p == 0) & (y == 1)))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return 2 * prec * rec / (prec + rec) if prec + rec else 0.0


def roc_points(y_true: np.ndarray, score: np.ndarray, cap: int = 60) -> tuple[np.ndarray, np.ndarray, float]:
    """返回 (fpr, tpr, auc)，按阈值降序扫过。"""
    y = np.asarray(y_true).ravel().astype(int)
    s = np.asarray(score, dtype=float).ravel()
    order = np.argsort(-s)
    ys = y[order]
    pos = float(max(ys.sum(), 1))
    neg = float(max(len(ys) - pos, 1))
    tpr = np.cumsum(ys) / pos
    fpr = np.cumsum(1 - ys) / neg
    fpr = np.concatenate(([0.0], fpr))
    tpr = np.concatenate(([0.0], tpr))
    auc = float(np.trapezoid(tpr, fpr)) if hasattr(np, "trapezoid") else float(np.trapz(tpr, fpr))
    idx = np.linspace(0, len(fpr) - 1, min(cap, len(fpr))).astype(int)
    idx = np.unique(np.concatenate((idx, [len(fpr) - 1])))
    return fpr[idx], tpr[idx], auc


def adjusted_rand_index(a: Any, b: Any) -> float:
    ta = np.asarray(a).ravel()
    tb = np.asarray(b).ravel()
    ua, ub = np.unique(ta), np.unique(tb)
    ia = {v: i for i, v in enumerate(ua)}
    ib = {v: i for i, v in enumerate(ub)}
    M = np.zeros((len(ua), len(ub)), dtype=float)
    for x, y in zip(ta, tb, strict=False):
        M[ia[x], ib[y]] += 1
    n = M.sum()
    if n < 2:
        return 0.0
    def comb(v: Any) -> Any:
        return v * (v - 1) / 2.0

    sum_comb = float(comb(M).sum())
    a_term = float(comb(M.sum(axis=1)).sum())
    b_term = float(comb(M.sum(axis=0)).sum())
    total = float(comb(n))
    expected = a_term * b_term / total
    index = sum_comb - expected
    maxindex = 0.5 * (a_term + b_term) - expected
    return float(index / maxindex) if abs(maxindex) > 1e-12 else 0.0


def entropy(p: np.ndarray) -> float:
    p = np.clip(np.asarray(p, dtype=float), 0.0, 1.0)
    p = p[p > 0]
    return float(-np.sum(p * np.log2(p))) if p.size else 0.0


def gini(p: np.ndarray) -> float:
    p = np.clip(np.asarray(p, dtype=float), 0.0, 1.0)
    return float(1.0 - np.sum(p * p))



def sigmoid(z: Any) -> np.ndarray:
    z = np.asarray(z, dtype=float)
    return np.where(z >= 0, 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500))),
                    np.exp(np.clip(z, -500, 500)) / (1.0 + np.exp(np.clip(z, -500, 500))))



