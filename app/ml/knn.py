"""K 近邻数值内核：Minkowski 距离 + 多数表决（可选距离加权），没有训练参数只有「查表」。

教学主线：K 是唯一的容量旋钮——K=1 记住噪声（高方差），K 太大把边界抹平（高偏差），
误差随 K 呈 U 形；决策区域在 3D 里就是一堆高度为投票率的台阶。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.ml import datasets, util

KEY = "knn"


def dist_matrix(A: np.ndarray, B: np.ndarray, p: float) -> np.ndarray:
    """|Aᵢ − Bⱼ|_p：p=1 曼哈顿、p=2 欧氏、p=4 已经很像切比雪夫（维度灾难的来源）。"""
    d = np.abs(A[:, None, :] - B[None, :, :]) ** float(p)
    return d.sum(axis=2) ** (1.0 / float(p))


def vote(train_y: np.ndarray, D: np.ndarray, k: int, weighted: bool) -> tuple[np.ndarray, np.ndarray]:
    """返回 (类别 1 的投票率, 邻居索引)。k 超过样本数时自动退化为用全部样本。

    距离加权用 1/(d+ε)：无穷远的点（留一法里的自身）权重自然为 0。
    """
    k = max(1, min(int(k), len(train_y)))
    idx = np.argsort(D, axis=1)[:, :k]
    dd = np.take_along_axis(D, idx, axis=1)
    w = 1.0 / (dd + 1e-6) if weighted else np.ones_like(dd)
    hit = (np.asarray(train_y)[idx] == 1).astype(float)
    prob = (w * hit).sum(axis=1) / np.maximum(w.sum(axis=1), 1e-12)
    return prob, idx


def run(params: dict[str, Any], seed: int, steps: int) -> dict[str, Any]:
    k = max(1, int(params["k"]))
    p = max(1.0, float(params["p"]))
    weighted = bool(int(params["weighted"]))
    n = int(params["n"])

    X, y = datasets.moons(seed, n=n, noise=0.22)
    g = util.rng(seed, 3)
    order = g.permutation(len(y))
    n_test = max(12, len(y) // 4)
    te, tr = order[:n_test], order[n_test:]
    Xtr, ytr = X[tr], y[tr]
    Xte, yte = X[te], y[te]

    D_tr = dist_matrix(Xtr, Xtr, p)
    np.fill_diagonal(D_tr, np.inf)  # 留一法：自己不能投自己
    D_te = dist_matrix(Xte, Xtr, p)

    prob, _picked = vote(ytr, D_te, k, weighted)
    pred = (prob >= 0.5).astype(int)
    acc = float(np.mean(pred == yte))
    f1 = util.f1_score(yte, pred)

    ks = sorted({1, 3, 5, 7, 9, 11, 15, 21, 31, 41, k if k % 2 else k + 1})
    loo = [float(np.mean((vote(ytr, D_tr, kk, weighted)[0] >= 0.5).astype(int) != ytr)) for kk in ks]
    hold = [float(np.mean((vote(ytr, D_te, kk, weighted)[0] >= 0.5).astype(int) != yte)) for kk in ks]

    # 决策区域：41×41 网格上的软投票率（分块算，避免 (m·n) 级内存）
    xr = (float(X[:, 0].min()) - 0.5, float(X[:, 0].max()) + 0.5)
    yr = (float(X[:, 1].min()) - 0.5, float(X[:, 1].max()) + 0.5)
    gx, gy = np.linspace(*xr, 41), np.linspace(*yr, 41)
    G1, G2 = np.meshgrid(gx, gy, indexing="xy")
    Q = np.column_stack([G1.ravel(), G2.ravel()])
    Zflat = np.empty(Q.shape[0])
    for i in range(0, len(Q), 300):
        chunk = Q[i:i + 300]
        Zflat[i:i + len(chunk)] = vote(ytr, dist_matrix(chunk, Xtr, p), k, weighted)[0]
    points = [util.point3(X[i, 0], X[i, 1], 0.0, int(y[i]), 1.2) for i in range(len(y))]
    boundary = util.cloud(
        points, legend=[{"label": "类别 0", "color": util.color_of(0)},
                        {"label": "类别 1", "color": util.color_of(1)}],
        bound=util.boundary(gx, gy, Zflat.reshape(G1.shape), "x₁", "x₂", "类别 1 的投票率", level=0.5))

    # 查询点：挑投票率最接近 0.5 的那个测试样本——只有边界上的点值得放大看
    qi = int(np.argmin(np.abs(prob - 0.5)))
    dq = D_te[qi]
    order_q = np.argsort(dq)[:k]
    wq = 1.0 / (dq[order_q] + 1e-6) if weighted else np.ones(len(order_q))
    share = wq / max(float(wq.sum()), 1e-12)  # 归一化后的实际投票份额（柱状图用原始权重更能看出差别）
    lab_cls = np.asarray(ytr)[order_q]
    votes_bars = util.bars(
        [f"#{i + 1} 类{int(c)} d={dq[j]:.2f}" for i, (j, c) in enumerate(zip(order_q, lab_cls))],
        wq, ylab="投票权重 1 或 1/d", xlab="按距离排序的邻居")
    sum1 = float(share[lab_cls == 1].sum())
    sum0 = float(share[lab_cls == 0].sum())

    errvs = util.lines2d(
        [util.curve("loo", "留一法误差", ks, loo, color="#2563eb"),
         util.curve("hold", "留出测试集误差", ks, hold, color="#ea580c"),
         util.curve("now", f"当前 K={k}", [k, k], [min(loo + hold), max(loo + hold)],
                    dash=True, color="#0d9488")],
        "邻居数 K", "错误率", xr=(1, max(ks)), yr=(0.0, max(1.0, max(loo + hold) * 1.1)))

    return util.finish(KEY, {
        "backend": "numpy",
        "metrics": {"acc": acc, "f1": f1},
        "series": [
            util.ser("loo_err", "留一法误差 vs K", ks, loo, "K", "error"),
            util.ser("test_err", "测试集误差 vs K", ks, hold, "K", "error"),
        ],
        "table": [
            util.tab("setup", "本次查询", [
                {"name": "K / p / 距离加权", "value": f"{k} / {p:g} / {'是' if weighted else '否'}"},
                {"name": "训练点 / 查询点", "value": f"{len(ytr)} / {len(yte)}"},
                {"name": "查询点邻居平均距离", "value": f"{float(np.mean(dq[order_q])):.4f}",
                 "note": f"该点类别 1 投票率 {prob[qi]:.3f}（最接近 0.5 的模糊点）"},
                {"name": "类别 1 权重合计", "value": f"{sum1:.4f}",
                 "note": f"类别 0 = {sum0:.4f} → 判为 {int(sum1 >= sum0)}"},
                {"name": "查询点上的错误数", "value": f"{int(np.sum(pred != yte))} / {len(yte)}"},
                {"name": "最优 K（留一法）", "value": f"{int(ks[int(np.argmin(loo))])}",
                 "note": f"LOO 误差 {min(loo):.3f}"},
            ]),
        ],
        "visualMap": {"boundary": boundary, "votes": votes_bars, "errvs": errvs},
    })
