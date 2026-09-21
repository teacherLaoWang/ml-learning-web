"""逻辑回归数值内核：σ(w·x+b) + 交叉熵 + L2，全批量梯度下降。

数据是「只在 x₁ 上分得开」的两团高斯（x₂ 是纯噪声特征），于是：
* 损失面在 (w₁, b) 上是严格凸的，可以直接画全地形 + 轨迹；
* w₂ 的真值是 0，L2 强度一调大就能看到它被压向原点——正则化最直观的一张图。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.ml import datasets, util

KEY = "logreg"
EPS = 1e-12


def loss_grad(F: np.ndarray, y: np.ndarray, th: np.ndarray, l2: float) -> tuple[float, np.ndarray]:
    """交叉熵 + (λ/2)(w₁²+w₂²)（偏置不罚）；返回 (loss, ∇)。"""
    z = np.clip(F @ th, -60.0, 60.0)
    p = util.sigmoid(z)
    ll = float(-np.mean(y * np.log(p + EPS) + (1 - y) * np.log(1 - p + EPS)))
    pen = 0.5 * float(l2) * float(np.sum(th[:2] ** 2))
    g = F.T @ (p - y) / len(y) + float(l2) * np.r_[th[:2], 0.0]
    return ll + pen, g


def _slice_fn(F: np.ndarray, y: np.ndarray, w2: float, l2: float):
    """固定 w₂ 后的二维损失 L(w₁, b)：凸、可 Newton 求极小。"""
    A = np.column_stack([F[:, 0], F[:, 2]])

    def fn(v: np.ndarray) -> tuple[float, np.ndarray]:
        th = np.array([v[0], w2, v[1]])
        L, g = loss_grad(F, y, th, l2)
        return L, g[[0, 2]]

    def hess(v: np.ndarray) -> np.ndarray:
        p = util.sigmoid(A @ v)
        H = A.T @ (A * (p * (1 - p))[:, None]) / len(y)
        return H + l2 * np.diag([1.0, 0.0])

    return fn, hess


def _newton_min(fn, hess, v0: np.ndarray, iters: int = 40) -> np.ndarray:
    v = np.array(v0, dtype=float)
    for _ in range(iters):
        _, g = fn(v)
        H = hess(v) + 1e-8 * np.eye(2)
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            step = g
        for back in (1.0, 0.5, 0.25, 0.1):
            cand = v - back * step
            if np.isfinite(cand).all() and fn(cand)[0] <= fn(v)[0] + 1e-12:
                v = cand
                break
        else:
            break
        if np.linalg.norm(step) < 1e-10:
            break
    return v


def run(params: dict[str, Any], seed: int, steps: int) -> dict[str, Any]:
    lr = float(params["lr"])
    l2 = float(params["l2"])
    overlap = float(params["sep"])
    n = int(params["n"])

    # 「类别重叠度」→ 中心距：参数越大两团越糊在一起
    dist = max(4.2 - 1.1 * overlap, 0.2)
    X, y = datasets.blobs(seed, n=n, sep=dist / 2.0, sigma=1.0, skew=0.0)
    F = np.column_stack([X, np.ones(len(y))])

    th = np.zeros(3)
    hist = []
    for _ in range(int(steps)):
        L, g = loss_grad(F, y, th, l2)
        if not np.isfinite(L) or not np.all(np.isfinite(th)):
            break
        hist.append({"th": th.copy(), "L": L, "g": g.copy(),
                     "acc": float(np.mean((F @ th > 0).astype(int) == y))})
        th = th - lr * g
    th = hist[-1]["th"] if hist else th
    T = len(hist)

    w2_fixed = float(th[1])
    fn, hess = _slice_fn(F, y, w2_fixed, l2)
    v_star = _newton_min(fn, hess, np.array([th[0], th[2]]))
    v0 = np.array([hist[0]["th"][0], hist[0]["th"][2]])
    traj2 = np.array([[h["th"][0], h["th"][2]] for h in hist]) if hist else v0[None, :]
    pts = np.vstack([v0, traj2, v_star])
    pad = 0.4 * (pts.max(axis=0) - pts.min(axis=0) + 0.8)
    lo, hi = pts.min(axis=0) - pad, pts.max(axis=0) + pad
    w1g = np.linspace(lo[0], hi[0], util.GRID)
    bg = np.linspace(lo[1], hi[1], util.GRID)
    Z = np.empty((len(bg), len(w1g)))
    base = F[:, 2] + w2_fixed * F[:, 1]  # 偏置 + 固定住的 w₂x₂
    for j, a in enumerate(w1g):
        lin = base + a * F[:, 0]
        Pm = util.sigmoid(lin[:, None] + bg[None, :])  # (n, len(b))
        ce = -np.mean(y[:, None] * np.log(Pm + EPS) + (1 - y[:, None]) * np.log(1 - Pm + EPS),
                      axis=0)
        Z[:, j] = ce + 0.5 * l2 * (a * a + w2_fixed * w2_fixed)
    path = []
    for k, h in enumerate(hist):
        v = np.array([h["th"][0], h["th"][2]])
        Lv, gv = fn(v)
        path.append(util.trace(v[0], v[1], Lv, k, gv))
    optimum = {"x": util.num(v_star[0]), "y": util.num(v_star[1]),
               "z": util.num(fn(v_star)[0]), "label": "交叉熵唯一极小（凸）"}
    markers = [{"x": util.num(v0[0]), "y": util.num(v0[1]), "z": util.num(fn(v0)[0]),
                "label": "起点 (0,0)", "color": "#f97316"},
               {"x": util.num(th[0]), "y": util.num(th[2]),
                "z": util.num(fn(np.array([th[0], th[2]]))[0]),
                "label": f"第 {T} 步", "color": "#0d9488"}]

    # ---- 概率曲面（z = σ(w·x+b)）：墙沿着无关特征 x₂ 延伸，一眼看出它没被用上
    x1r = (float(X[:, 0].min()) - 0.6, float(X[:, 0].max()) + 0.6)
    x2r = (float(X[:, 1].min()) - 0.6, float(X[:, 1].max()) + 0.6)
    gx = np.linspace(*x1r, 41)
    gy = np.linspace(*x2r, 41)
    score = th[0] * gx[None, :] + th[2]
    P = util.sigmoid(th[1] * gy[:, None] + score)
    # 散点贴地（z=0），曲面高度才是预测概率——否则点会被曲面盖住
    points = [util.point3(X[i, 0], X[i, 1], 0.0, int(y[i]), 1.0) for i in range(len(y))]
    bound = util.boundary(gx, gy, P, "x₁（有用特征）", "x₂（噪声特征）", "预测概率 σ(z)",
                                        contour0=True, level=0.5)
    prob3d = util.cloud(points, legend=[{"label": "类别 0", "color": util.color_of(0)},
                                        {"label": "类别 1", "color": util.color_of(1)}],
                        bound=bound,
                        projection={"origin": [0.0, 0.0, 0.0],
                                    "normal": [util.num(th[0]), util.num(th[1]), 0.0],
                                    "label": "判别方向 w"})

    fpr, tpr, auc = util.roc_points(y, F @ th)
    acc = float(np.mean((F @ th > 0).astype(int) == y))
    final_L = hist[-1]["L"]
    climax = (
        "交叉熵对 θ 是凸的，所以这里没有局部极小，只有条件数问题：两团一重叠，"
        "p(1−p) 普遍偏小 → Hessian 变平 → 同样的 η 走得更快不到最优点附近就爬不动。"
        f"当前 w₂={w2_fixed:+.3f} 对应的 x₂ 是纯噪声特征，把 L2 强度 λ 调大它会被压向 0。"
    )

    return util.finish(KEY, {
        "backend": "numpy",
        "metrics": {"loss": final_L, "acc": acc, "auc": auc},
        "series": [
            util.ser("loss", "交叉熵损失", range(T), [h["L"] for h in hist], "epoch", "CE"),
            util.ser("acc", "训练准确率", range(T), [h["acc"] for h in hist], "epoch", "accuracy"),
            util.ser("gradnorm", "梯度范数 ‖∇L‖", range(T),
                     [float(np.linalg.norm(h["g"])) for h in hist], "epoch", "‖∇L‖"),
            util.ser("wnorm", "权重范数 ‖w‖₂", range(T),
                     [float(np.hypot(h["th"][0], h["th"][1])) for h in hist], "epoch", "‖w‖"),
        ],
        "table": [
            util.tab("coef", "学到的参数", [
                {"name": "w₁（有用特征）", "value": f"{th[0]:.4f}", "truth": f"{v_star[0]:.4f}",
                 "delta": f"{abs(th[0] - v_star[0]):.4f}"},
                {"name": "w₂（噪声特征）", "value": f"{th[1]:.4f}", "truth": "0.0000",
                 "delta": f"{abs(th[1]):.4f}"},
                {"name": "b（偏置）", "value": f"{th[2]:.4f}", "truth": f"{v_star[1]:.4f}",
                 "delta": f"{abs(th[2] - v_star[1]):.4f}"},
                {"name": "L2 强度 λ", "value": f"{l2:.2f}", "note": "偏置不参与惩罚"},
            ]),
            util.tab("sep", "数据与阈值", [
                {"name": "类别中心距", "value": f"{dist:.2f}",
                 "note": f"重叠度参数 {overlap} → 中心距 = 4.2 − 1.1×{overlap} = {dist:.2f}"},
                {"name": "判阈值", "value": "0.5000", "note": "σ(z)>0.5 ⇔ z>0 ⇔ w·x+b>0"},
                {"name": "AUC（与阈值无关）", "value": f"{auc:.4f}"},
            ]),
        ],
        "visualMap": {
            "prob3d": prob3d,
            "landscape": util.surface(w1g, bg, Z, "w₁", "b（偏置）", "交叉熵",
                                      path=path, optimum=optimum, markers=markers, climax=climax),
            "roc": util.lines2d([util.curve("roc", "ROC（阈值扫描）", fpr, tpr, color="#2563eb"),
                                 util.curve("diag", "瞎猜 AUC=0.5", [0.0, 1.0], [0.0, 1.0],
                                           dash=True, color="#94a3b8")],
                                "FPR", "TPR", diagonal=True, xr=(0, 1), yr=(0, 1)),
        },
    })
