"""CART 分类树数值内核：轴平行分裂 + Gini/熵不纯度 + max_depth/min_samples_leaf 早停。

教学主线：
* 每个内部节点都是一次「if xⱼ ≤ t」，叶 = 特征空间里的一块长方体；
* 深度↑ → 训练误差↓、验证误差先降后升（过拟合长什么样）；
* 特征重要性 = 各特征累计的不纯度下降（加权到样本占比）。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.ml import datasets, util

KEY = "tree"
MAX_CAND = 32  # 每个节点最多试这么多个候选阈值（中点），保证 400 样本也秒级完成


def impurity(y: np.ndarray, crit: int) -> float:
    if len(y) == 0:
        return 0.0
    _, cnt = np.unique(y, return_counts=True)
    p = cnt / cnt.sum()
    return util.gini(p) if crit == 0 else util.entropy(p)


def best_split(X: np.ndarray, y: np.ndarray, min_leaf: int, crit: int):
    """在所有 (特征, 阈值) 里找加权不纯度最低的一刀；返回 (feat, thr, gain, 左右索引)。"""
    n = len(y)
    parent = impurity(y, crit)
    best = None
    for j in range(X.shape[1]):
        col = np.sort(np.unique(X[:, j]))
        if len(col) < 2:
            continue
        mids = (col[:-1] + col[1:]) / 2.0
        if len(mids) > MAX_CAND:
            mids = mids[np.linspace(0, len(mids) - 1, MAX_CAND).astype(int)]
        for t in mids:
            li = X[:, j] <= t
            nl = int(li.sum())
            if nl < min_leaf or n - nl < min_leaf:
                continue
            gl = impurity(y[li], crit)
            gr = impurity(y[~li], crit)
            weighted = (nl * gl + (n - nl) * gr) / n
            gain = parent - weighted
            if best is None or gain > best[2] + 1e-12:
                best = (j, float(t), float(gain), li)
    return best


def build(X: np.ndarray, y: np.ndarray, crit: int, max_depth: int, min_leaf: int,
          depth: int = 0, nid: int = 0, importance=None) -> dict[str, Any]:
    """递归建树，同时给每个节点登记 (样本数, 类分布, 不纯度)。"""
    node = {"id": nid, "n": len(y), "depth": depth,
            "counts": {int(c): int(np.sum(y == c)) for c in np.unique(y)},
            "imp": impurity(y, crit), "leaf": True,
            "pred": np.argmax([np.sum(y == c) for c in (0, 1)]) if len(y) else 0}
    if depth >= max_depth or len(y) < 2 * max(min_leaf, 1) or node["imp"] <= 1e-12:
        return node
    sp = best_split(X, y, min_leaf, crit)
    if sp is None or sp[2] <= 1e-12:
        return node
    j, t, gain, li = sp
    if importance is not None:
        importance[j] += gain * len(y)
    node.update({"leaf": False, "feature": j, "thr": t, "gain": gain})
    node["left"] = build(X[li], y[li], crit, max_depth, min_leaf, depth + 1, nid * 2 + 1, importance)
    node["right"] = build(X[~li], y[~li], crit, max_depth, min_leaf, depth + 1, nid * 2 + 2, importance)
    return node


def predict(node: dict[str, Any], x: np.ndarray) -> int:
    while not node["leaf"]:
        node = node["left"] if x[node["feature"]] <= node["thr"] else node["right"]
    return int(node["pred"])


def predict_matrix(node: dict[str, Any], Q: np.ndarray) -> np.ndarray:
    return np.array([predict(node, q) for q in Q], dtype=int)


def layout(node: dict[str, Any], counter: list[int], nodes: list, edges: list):
    """按层级给坐标：叶按访问顺序占一格，内部节点取两个孩子的中点，y = 深度。"""
    if node["leaf"]:
        x = float(counter[0])
        counter[0] += 1
    else:
        lx = layout(node["left"], counter, nodes, edges)
        rx = layout(node["right"], counter, nodes, edges)
        x = 0.5 * (lx + rx)
    name = f"x{node.get('feature', 0) + 1} ≤ {node.get('thr', 0):.2f}"
    label = (f"叶：类 {node['pred']}" if node["leaf"] else name)
    nodes.append(util.node(node["id"], x, float(node["depth"]), label,
                           [f"n={node['n']}",
                            f"{{0,1}}={node['counts'].get(0, 0)}/{node['counts'].get(1, 0)}",
                            f"{'Gini' if node.get('_crit', 0) == 0 else '熵'}={node['imp']:.3f}"],
                           bool(node["leaf"])))
    if not node["leaf"]:
        edges.append(util.edge(node["id"], node["left"]["id"], "是 ≤"))
        edges.append(util.edge(node["id"], node["right"]["id"], "否 >"))
    return x


def prune_stats(node: dict[str, Any]) -> tuple[int, int, int]:
    if node["leaf"]:
        return 1, 1, 0
    ln, ll, ld = prune_stats(node["left"])
    rn, rl, rd = prune_stats(node["right"])
    return ln + rn + 1, ll + rl, max(ld, rd) + 1


def run(params: dict[str, Any], seed: int, steps: int) -> dict[str, Any]:
    max_depth = max(1, int(params["depth"]))
    min_leaf = max(1, int(params["leaf"]))
    crit = int(params["crit"])
    n = int(params["n"])

    X, y = datasets.moons(seed, n=n, noise=0.3)
    g = util.rng(seed, 5)
    order = g.permutation(len(y))
    n_val = max(10, len(y) // 3)
    va, tr = order[:n_val], order[n_val:]
    Xtr, ytr = X[tr], y[tr]
    Xva, yva = X[va], y[va]

    importance = np.zeros(X.shape[1])
    tree = build(Xtr, ytr, crit, max_depth, min_leaf, importance=importance)
    train_pred = predict_matrix(tree, Xtr)
    val_pred = predict_matrix(tree, Xva)
    acc = float(np.mean(train_pred == ytr))
    acc_val = float(np.mean(val_pred == yva))
    n_nodes, n_leaves, real_depth = prune_stats(tree)

    # 深度扫描：过拟合曲线
    depths = list(range(1, 11))
    tr_err, va_err = [], []
    for d in depths:
        imp2 = np.zeros(X.shape[1])
        t2 = build(Xtr, ytr, crit, d, min_leaf, importance=imp2)
        tr_err.append(float(1 - np.mean(predict_matrix(t2, Xtr) == ytr)))
        va_err.append(float(1 - np.mean(predict_matrix(t2, Xva) == yva)))
    best_d = depths[int(np.argmin(va_err))]
    best_va = min(va_err)
    gap = va_err[-1] - tr_err[-1]

    # 空间被轴平行超平面切碎：网格上的预测类别
    gx = np.linspace(float(X[:, 0].min()) - 0.35, float(X[:, 0].max()) + 0.35, 41)
    gy = np.linspace(float(X[:, 1].min()) - 0.35, float(X[:, 1].max()) + 0.35, 41)
    G1, G2 = np.meshgrid(gx, gy, indexing="xy")
    Q = np.column_stack([G1.ravel(), G2.ravel()])
    Z = predict_matrix(tree, Q).reshape(G1.shape).astype(float)
    # 点贴地（z=0），高度只用来表达「叶的长方体」属于哪一类，避免点被块埋住
    points = [util.point3(X[i, 0], X[i, 1], 0.0, int(y[i]), 1.1) for i in range(len(y))]
    partition = util.cloud(points,
                           legend=[{"label": "类别 0", "color": util.color_of(0)},
                                   {"label": "类别 1", "color": util.color_of(1)}],
                           bound=util.boundary(gx, gy, Z, "x₁", "x₂", "预测类别（叶的长方体）", level=0.5))

    nodes: list = []
    edges: list = []
    _annotate(tree, crit)
    layout(tree, [0], nodes, edges)

    tot = float(importance.sum())
    imp_rel = importance / tot if tot > 1e-12 else importance

    return util.finish(KEY, {
        "backend": "numpy",
        "metrics": {"acc": acc, "acc_val": acc_val},
        "series": [
            util.ser("train_err", "训练误差 vs 深度", depths, tr_err, "max_depth", "error"),
            util.ser("val_err", "验证误差 vs 深度", depths, va_err, "max_depth", "error"),
        ],
        "table": [
            util.tab("size", "树的规模", [
                {"name": "节点 / 叶 / 实际深度", "value": f"{n_nodes} / {n_leaves} / {real_depth}"},
                {"name": "分裂准则", "value": "Gini" if crit == 0 else "信息熵",
                 "note": f"min_samples_leaf = {min_leaf}"},
                {"name": "训练准确率", "value": f"{acc:.4f}", "truth": f"验证 {acc_val:.4f}",
                 "delta": f"{abs(acc - acc_val):.4f}"},
                {"name": "过拟合差距（depth=10：验证−训练）", "value": f"{gap:+.4f}",
                 "note": "正数=记住了训练集的噪声；深度越深这个数越靠右"},
                {"name": "验证误差最低的深度", "value": f"{best_d}",
                 "note": f"该深度验证误差 {best_va:.3f}，当前深度 {max_depth} 时 {va_err[max_depth - 1]:.3f}"},
            ]),
            util.tab("splits", "前几次分裂", _top_splits(tree, 5)),
        ],
        "visualMap": {
            "graph": util.tree2d(nodes, edges),
            "partition": partition,
            "overfit": util.lines2d(
                [util.curve("train", "训练误差", depths, tr_err, color="#2563eb"),
                 util.curve("val", "验证误差", depths, va_err, color="#ea580c"),
                 util.curve("now", f"当前 depth={max_depth}", [max_depth] * 2,
                            [tr_err[max_depth - 1], va_err[max_depth - 1]], dash=True, color="#0d9488")],
                "最大深度", "错误率", xr=(1, 10), yr=(0.0, max(0.5, max(va_err) * 1.1))),
            "imp": util.bars([f"x{i + 1}" for i in range(X.shape[1])], imp_rel,
                              ylab="不纯度下降占比", xlab="特征"),
        },
    })


def _annotate(node: dict[str, Any], crit: int):
    node["_crit"] = crit
    if not node["leaf"]:
        _annotate(node["left"], crit)
        _annotate(node["right"], crit)


def _top_splits(node: dict[str, Any], cap: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stack = [node]
    while stack and len(rows) < cap:
        nd = stack.pop(0)
        if nd["leaf"]:
            continue
        rows.append({"name": f"深度 {nd['depth']}：x{nd['feature'] + 1} ≤ {nd['thr']:.3f}",
                     "value": f"Δ={nd['gain']:.4f}",
                     "note": f"n={nd['n']} → 左 {nd['left']['n']} / 右 {nd['right']['n']}，"
                             f"不纯度 {nd['imp']:.3f}"})
        stack = [nd["left"], nd["right"]] + stack
    return rows
