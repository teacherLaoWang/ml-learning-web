"""线性回归数值内核：ŷ = w₁f₁ + w₂f₂（f₁=标准化 x，f₂=标准化 x² 再除以「特征尺度比」）。

教学主线：损失碗的条件数（由特征尺度比控制）如何决定轨迹形状。
教案口径见 app/content/lessons/linreg.py：L = MSE = (1/n)Σ(ŷᵢ−yᵢ)²，∇L = (2/n)Xᵀ(Xw−y)。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.ml import datasets, util

KEY = "linreg"


def features(x: np.ndarray, spread: float) -> tuple[np.ndarray, dict[str, float]]:
    """两个特征都零均值单位方差化，第二个再除以 `spread`：std(f₁)/std(f₂) 恰为尺度比。"""
    xs = x * x
    z1 = (x - x.mean()) / max(float(x.std()), 1e-9)
    z2 = (xs - xs.mean()) / max(float(xs.std()), 1e-9)
    F = np.column_stack([z1, z2 / max(float(spread), 1e-9)])
    info = {"sd1": float(x.std()), "sd2": float(xs.std()) * max(float(spread), 1e-9)}
    return F, info


def loss_grad(F: np.ndarray, y: np.ndarray, w: np.ndarray) -> tuple[float, np.ndarray]:
    r = F @ w - y
    return float(np.mean(r * r)), (2.0 / len(y)) * (F.T @ r)


def trajectory(F: np.ndarray, y: np.ndarray, w0: np.ndarray, lr: float, steps: int):
    """每步的 (参数, 损失, 梯度)——前端 3D 动画就吃这三样。"""
    w = np.array(w0, dtype=float)
    ws, ls, gs = [], [], []
    for _ in range(int(steps)):
        L, g = loss_grad(F, y, w)
        ws.append(w.copy())
        ls.append(L)
        gs.append(g.copy())
        w = w - lr * g
        if not np.all(np.isfinite(w)) or L > 1e8:  # 数值炸了就停在最后一个有限点
            break
    ws.append(w.copy())
    return np.array(ws), np.array(ls), np.array(gs)


def run(params: dict[str, Any], seed: int, steps: int) -> dict[str, Any]:
    lr = float(params["lr"])
    spread = float(params["spread"])
    n = int(params["n"])
    noise = float(params["noise"])

    data = datasets.quad_1d(seed, n=n, noise=noise)
    x, y = data["x"], data["y"]
    F, info = features(x, spread)

    # 闭式解（正规方程）：带极小岭项防奇异
    w_star = np.linalg.solve(F.T @ F + 1e-10 * np.eye(2), F.T @ y)
    gram = (2.0 / len(y)) * (F.T @ F)
    eig = np.linalg.eigvalsh(gram)
    lam_max, lam_min = float(eig[-1]), float(max(eig[0], 1e-9))

    W, Lhist, Ghist = trajectory(F, y, np.zeros(2), lr, int(steps))
    T = len(Lhist)
    wT = W[-1]
    mse_final, _ = loss_grad(F, y, wT)
    r2 = 1.0 - mse_final / max(float(np.mean((y - y.mean()) ** 2)), 1e-12)

    # ---- 损失曲面：范围覆盖起点 + 轨迹 + 最优点
    pts = np.vstack([np.zeros(2), W[:T], w_star])
    pad = 0.35 * (pts.max(axis=0) - pts.min(axis=0) + 0.4)
    lo, hi = pts.min(axis=0) - pad, pts.max(axis=0) + pad
    wg = np.linspace(lo[0], hi[0], util.GRID)
    wb = np.linspace(lo[1], hi[1], util.GRID)
    # grid.z 形状必须是 [len(y)][len(x)]
    Z = np.empty((len(wb), len(wg)), dtype=float)
    for j, w1 in enumerate(wg):
        r = F[:, 0][:, None] * w1 + np.outer(F[:, 1], wb) - y[:, None]
        Z[:, j] = np.mean(r * r, axis=0)

    path = [util.trace(W[i, 0], W[i, 1], Lhist[i], i, Ghist[i]) for i in range(T)]
    optimum = {"x": util.num(w_star[0]), "y": util.num(w_star[1]),
               "z": util.num(loss_grad(F, y, w_star)[0]), "label": "全局最优 (XᵀX)⁻¹Xᵀy"}
    markers = [{"x": 0.0, "y": 0.0, "z": util.num(Lhist[0]), "label": "起点 w=(0,0)",
                "color": "#f97316"}]
    climax = (
        f"同一个碗，两个方向的曲率差 {lam_max / lam_min:.0f} 倍（λmax={lam_max:.2f}, λmin={lam_min:.3f}）。"
        f"稳定要求 η < 2/λmax = {2.0 / lam_max:.3f}；当前 η={lr} 在最平方向每步只推进 "
        f"{lr * lam_min:.4f}，于是轨迹贴着谷底走「之」字——这就是要标准化的原因。"
    )

    # ---- 回到 x 的原尺度，与真值 y = 1.2x + 0.35x² 直接可比
    def to_original(w: np.ndarray) -> tuple[float, float]:
        return float(w[0] / info["sd1"]), float(w[1] / info["sd2"])

    xg = np.linspace(float(x.min()), float(x.max()), 61)
    aT, bT = to_original(wT)
    y_model = aT * xg + bT * xg * xg
    y_truth = data["truth"]["w1"] * xg + data["truth"]["w2"] * xg * xg
    resid = F @ wT - y
    idx = np.unique(np.linspace(0, len(y) - 1, min(48, len(y))).astype(int))
    err = float(np.linalg.norm(wT - w_star))

    return util.finish(KEY, {
        "backend": "numpy",
        "metrics": {"mse": mse_final, "r2": r2},
        "series": [
            util.ser("loss", "损失 MSE", range(T), Lhist, "epoch", "MSE"),
            util.ser("gradnorm", "梯度范数 ‖∇L‖", range(T),
                     [float(np.linalg.norm(g)) for g in Ghist], "epoch", "‖∇L‖"),
        ],
        "table": [
            util.tab("coef", "学到的权重（归一化特征空间）", [
                {"name": "w₁", "value": f"{wT[0]:.4f}", "truth": f"{w_star[0]:.4f}",
                 "delta": f"{abs(wT[0] - w_star[0]):.4f}"},
                {"name": "w₂", "value": f"{wT[1]:.4f}", "truth": f"{w_star[1]:.4f}",
                 "delta": f"{abs(wT[1] - w_star[1]):.4f}"},
                {"name": "还原：ŷ = a·x + b·x² 的 a", "value": f"{aT:.4f}", "truth": "1.2000",
                 "delta": f"{abs(aT - 1.2):.4f}"},
                {"name": "还原：b", "value": f"{bT:.4f}", "truth": "0.3500",
                 "delta": f"{abs(bT - 0.35):.4f}"},
            ]),
            util.tab("normal", "正规方程 vs 梯度下降", [
                {"name": "λmax((2/n)XᵀX)", "value": f"{lam_max:.4f}",
                 "note": f"稳定上限 η* = 2/λmax = {2.0 / lam_max:.4f}"},
                {"name": "λmin", "value": f"{lam_min:.6f}",
                 "note": f"条件数 κ = λmax/λmin = {lam_max / lam_min:.2f}"},
                {"name": "‖w_GD − w_闭式‖", "value": f"{err:.5f}",
                 "note": f"相对误差 {err / max(float(np.linalg.norm(w_star)), 1e-9) * 100:.2f}%"},
            ]),
        ],
        "visualMap": {
            "landscape": util.surface(wg, wb, Z, "w₁（x 的权重）", "w₂（x² 的权重）", "MSE",
                                      path=path, optimum=optimum, markers=markers, climax=climax),
            "fit": util.lines2d(
                [util.curve("truth", "真实关系 1.2x+0.35x²", xg, y_truth, dash=True, color="#94a3b8"),
                 util.curve("model", "学到的 ŷ(x)", xg, y_model, color="#2563eb"),
                 util.curve("samples", "带噪样本 (x, y)", x, y, color="#ea580c")],
                "x", "y", xr=(float(xg.min()), float(xg.max()))),
            "residual": util.bars([f"{x[i]:.2f}" for i in idx], np.abs(resid[idx]),
                                  ylab="|ŷ − y|", xlab="样本 x"),
        },
    })
