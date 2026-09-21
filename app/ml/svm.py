"""支持向量机数值内核：primal 形式 (λ/2)‖u‖² + (1/n)Σ max(0,1−yᵢfᵢ)²，FISTA 加速 prox 梯度。

线性核：f = Xu + b（u 就是 w）；RBF 核：f = Ku + b（核矩阵上的 primal 形式，
即 PSVM 口径——惩罚的是预映射向量的欧氏范数，所以间隔会比理论值略小，教案里写清楚了）。
平方 hinge 让目标处处可导，于是能用梯度法稳定求解并给出完整下降轨迹；
C 与 λ 的换算是 λ = 1/(C·n)（把 ½‖u‖² + CΣξ 整体除以 Cn）。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.ml import datasets, util

KEY = "svm"


def rbf_kernel(A: np.ndarray, B: np.ndarray, gamma: float) -> np.ndarray:
    d2 = np.sum(A * A, 1)[:, None] + np.sum(B * B, 1)[None, :] - 2.0 * (A @ B.T)
    return np.exp(-float(gamma) * np.maximum(d2, 0.0))


def lam_max(M: np.ndarray, iters: int = 60) -> float:
    v = np.ones(M.shape[1]) / np.sqrt(M.shape[1])
    for _ in range(iters):
        nv = M @ v
        n = float(np.linalg.norm(nv))
        if n < 1e-15:
            return 0.0
        v = nv / n
    return float(v @ (M @ v))


def solve(Z: np.ndarray, y: np.ndarray, lam: float, iters: int):
    """FISTA：min (λ/2)‖u‖² + (1/n)Σmax(0,1−yᵢ(Zᵢu+b))²，偏置不罚。"""
    n, d = Z.shape
    L = lam + 2.0 * lam_max((Z.T @ Z) / n) if d <= 400 else lam + 2.0 * float(np.trace(Z.T @ Z) / n)
    lr = 1.0 / max(L, 1e-9)
    u = np.zeros(d)
    b = 0.0
    z = u.copy()
    zb = b
    tk = 1.0
    hist = []
    for t in range(int(iters)):
        f = Z @ z + zb
        h = np.maximum(0.0, 1.0 - y * f)
        gy = -(2.0 / n) * h * y
        gu = Z.T @ gy
        gb = float(gy.sum())
        loss = float(0.5 * lam * float(u @ u) + np.mean(h * h))
        hist.append({"loss": loss, "obj": loss + 0.5 * lam * float(u @ u),
                     "gnorm": float(np.hypot(gu[0] + lam * u[0], gb)), "u": u.copy(), "b": b})
        tn = 0.5 * (1.0 + np.sqrt(1.0 + 4.0 * tk * tk))
        un = (z - lr * gu) / (1.0 + lr * lam)
        bn = zb - lr * gb
        z = un + ((tk - 1.0) / tn) * (un - u)
        zb = bn + ((tk - 1.0) / tn) * (bn - b)
        u, b, tk = un, bn, tn
    return {"u": u, "b": b, "hist": hist, "L": L}


def kernel_grad_norm(X: np.ndarray, u: np.ndarray, gamma: float, Q: np.ndarray) -> np.ndarray:
    """RBF 决策函数在 Q 各点的输入空间梯度范数：
    ∇f(x) = Σⱼ uⱼ ∇ₓk(x,xⱼ) = Σⱼ uⱼ(−2γ)(x−xⱼ)k(x,xⱼ)。
    """
    diff = Q[:, None, :] - X[None, :, :]  # (m, n, d)
    k = np.exp(-gamma * np.maximum((diff ** 2).sum(axis=2), 0.0))
    w = np.einsum("j,ij,ijc->ic", u, k, diff) * (-2.0 * gamma)
    return np.linalg.norm(w, axis=1)


def run(params: dict[str, Any], seed: int, steps: int) -> dict[str, Any]:
    C = float(params["C"])
    kernel = int(params["kernel"])
    gamma = float(params["gamma"])
    overlap = float(params["noise"])
    iters = max(30, min(int(steps), 400))

    X, y0 = datasets.moons(seed, n=200, noise=0.10 + 0.28 * overlap)
    g = util.rng(seed, 21)
    order = g.permutation(len(y0))
    n_val = 60
    va, tr = order[:n_val], order[n_val:]
    Xtr, ytr = X[tr], 2.0 * y0[tr] - 1.0
    Xva, yva = X[va], 2.0 * y0[va] - 1.0
    mu = Xtr.mean(axis=0)
    sd = np.maximum(Xtr.std(axis=0), 1e-9)
    Xtr_s = (Xtr - mu) / sd
    Xva_s = (Xva - mu) / sd
    n = len(ytr)
    lam = 1.0 / max(C * n, 1e-9)

    if kernel == 0:
        Ztr, Zva = Xtr_s, Xva_s
    else:
        Ztr = rbf_kernel(Xtr_s, Xtr_s, gamma)
        Zva = rbf_kernel(Xva_s, Xtr_s, gamma)
    sol = solve(Ztr, ytr, lam, iters)
    u, b = sol["u"], sol["b"]
    f_tr = Ztr @ u + b
    f_va = Zva @ u + b
    acc = float(np.mean(np.sign(f_va) == yva))
    acc_tr = float(np.mean(np.sign(f_tr) == ytr))
    sv_mask = (ytr * f_tr) < 1.0 + 1e-3
    n_sv = int(sv_mask.sum())

    # 几何间隔：逐点 margin = y·f / ‖∇ₓf‖（线性核就是 y(wx+b)/‖w‖，精确）
    gradn = (np.full(n, float(np.linalg.norm(u))) if kernel == 0
             else np.maximum(kernel_grad_norm(Xtr_s, u, gamma, Xtr_s), 1e-9))
    pt_margin = ytr * f_tr / gradn
    correct = pt_margin[ytr * f_tr > 0]
    margin = float(np.min(correct)) if correct.size else 0.0

    # ---- 决策函数网格（原尺度坐标，前端直接叠上散点）
    gx = np.linspace(float(X[:, 0].min()) - 0.5, float(X[:, 0].max()) + 0.5, 41)
    gy = np.linspace(float(X[:, 1].min()) - 0.5, float(X[:, 1].max()) + 0.5, 41)
    G1, G2 = np.meshgrid(gx, gy, indexing="xy")
    Qs = (np.column_stack([G1.ravel(), G2.ravel()]) - mu) / sd
    if kernel == 0:
        Fgrid = (Qs @ u + b).reshape(G1.shape)
    else:
        Fgrid = (rbf_kernel(Qs, Xtr_s, gamma) @ u + b).reshape(G1.shape)
    Fgrid = np.clip(Fgrid, -6.0, 6.0)

    pts = []
    for i in range(len(X)):
        istrain = i in set(tr.tolist())
        lab = int(y0[i])
        is_sv = istrain and sv_mask[np.flatnonzero(tr == i)[0]] if istrain else False
        pts.append({"x": util.num(X[i, 0]), "y": util.num(X[i, 1]), "z": 0.0,
                    "label": lab + (2 if is_sv else 0), "size": 2.0 if is_sv else 1.0})
    hulls = [{"label": "间隔边界 f=+1", "points": _level_curve(gx, gy, Fgrid, 1.0)},
             {"label": "间隔边界 f=−1", "points": _level_curve(gx, gy, Fgrid, -1.0)},
             {"label": "决策面 f=0", "points": _level_curve(gx, gy, Fgrid, 0.0)}]
    hulls = [h for h in hulls if len(h["points"]) >= 2]
    margin_cloud = util.cloud(pts,
                              legend=[{"label": "类别 0", "color": util.color_of(0)},
                                      {"label": "类别 1", "color": util.color_of(1)},
                                      {"label": "类别 0 支持向量", "color": "#f97316"},
                                      {"label": "类别 1 支持向量", "color": "#dc2626"}],
                              bound=util.boundary(gx, gy, Fgrid, "x₁", "x₂",
                                                  "决策函数 f(x)", contour0=True),
                              hulls=hulls)
    sv_marks = [util.marker(Xtr[i, 0], Xtr[i, 1], float(f_tr[i]),
                            f"SV y·f={float(ytr[i] * f_tr[i]):.2f}", "#dc2626")
                for i in np.flatnonzero(sv_mask)[:24]]

    # ---- 容量扫描：C（当前核）与 γ（RBF 核）各自的泛化曲线
    C_grid = [0.02, 0.05, 0.2, 1.0, 5.0, 20.0, 60.0]
    gam_grid = [0.05, 0.15, 0.4, 0.9, 2.0, 4.0, 6.0]
    c_tr, c_va = _sweep(C_grid, Xtr_s, ytr, Xva_s, yva, kernel, gamma, iters=90)
    g_tr, g_va = _sweep(gam_grid, Xtr_s, ytr, Xva_s, yva, 1, gamma, iters=90,
                        vary="gamma", base_C=C)
    gamma_line = util.lines2d(
        [util.curve("c_val", "验证误差 vs log₁₀C", np.log10(C_grid), c_va, color="#2563eb"),
         util.curve("c_train", "训练误差 vs log₁₀C", np.log10(C_grid), c_tr, dash=True, color="#94a3b8"),
         util.curve("g_val", "RBF 核：验证误差 vs log₁₀γ", np.log10(gam_grid), g_va, color="#ea580c"),
         util.curve("g_train", "RBF 核：训练误差 vs log₁₀γ", np.log10(gam_grid), g_tr,
                    dash=True, color="#f97316"),
         util.curve("now", f"当前 C={C:g}, γ={gamma:g}", [np.log10(C)], [acc_val_of(c_va, C_grid, C)],
                    color="#0d9488")],
        "log₁₀(超参数)", "错误率", xr=(-2.0, 1.9), yr=(0.0, 0.6))

    hist = sol["hist"]
    T = len(hist)
    climax = (
        ("线性核：f(x)=w·x+b 是一个平面，只有落在间隔内侧的点（支持向量）在拉动解；"
         f"当前 {n_sv} 个支持向量决定这条间隔带（几何间隔 {margin:.3f}）。C→∞ 时它会退回硬间隔。")
        if kernel == 0 else
        (f"RBF 核：f(x)=Σᵢ uᵢ e^(−{gamma:g}‖x−xᵢ‖²)+b，每个支持向量顶起一个局部 bump。"
         f"γ 太小 → bump 宽得像直线（高偏差）；γ 太大 → 每个点自成孤岛，训练误差 0 但验证误差飙升。"))

    return util.finish(KEY, {
        "backend": "numpy",
        "metrics": {"acc": acc, "margin": margin, "sv": n_sv},
        "series": [
            util.ser("loss", "primal 目标 (λ/2)‖u‖² + 平均平方 hinge", range(T),
                     [h["obj"] for h in hist], "iter", "目标值"),
            util.ser("hinge", "平方 hinge 损失 (1/n)Σh²", range(T),
                     [float(np.mean(np.maximum(0.0, 1 - ytr * (Ztr @ h["u"] + h["b"])) ** 2))
                      for h in hist], "iter", "hinge²"),
            util.ser("gradnorm", "‖∇‖", range(T), [h["gnorm"] for h in hist], "iter", "‖∇‖"),
        ],
        "table": [
            util.tab("model", "解", [
                {"name": "核", "value": "线性" if kernel == 0 else f"RBF γ={gamma:g}"},
                {"name": "C / λ=1/(Cn)", "value": f"{C:g} / {lam:.6f}"},
                {"name": "支持向量数", "value": f"{n_sv} / {n}",
                 "note": "定义：y·f < 1，即落在间隔内侧或被错分的点"},
                {"name": "几何间隔 min y·f/‖∇ₓf‖", "value": f"{margin:.4f}",
                 "note": "线性核等于 1/‖w‖；这里 ‖w‖="
                         f"{float(np.linalg.norm(u)):.3f}"},
                {"name": "训练 / 验证准确率", "value": f"{acc_tr:.4f}", "truth": f"{acc:.4f}",
                 "delta": f"{abs(acc_tr - acc):.4f}"},
                {"name": "迭代 / Lipschitz 上界", "value": f"{T}", "note": f"L≈{sol['L']:.2f}，η=1/L"},
            ]),
        ],
        "visualMap": {
            "margin": margin_cloud,
            "decision": util.surface(gx, gy, Fgrid, "x₁", "x₂", "f(x) 决策函数",
                                      levels=[-1.0, 0.0, 1.0], markers=sv_marks, climax=climax),
            "gamma": gamma_line,
        },
    })


def acc_val_of(curve, grid, value):
    i = int(np.argmin([abs(np.log10(g) - np.log10(max(value, 1e-9))) for g in grid]))
    return float(curve[i])


def _sweep(grid, Xtr, ytr, Xva, yva, kernel, gamma, iters=90, vary="C", base_C=1.0, gam=None):
    """扫一遍超参，返回 (train err, val err)。"""
    tr, va = [], []
    n = len(ytr)
    for v in grid:
        Cv = v if vary == "C" else base_C
        gv = gamma if vary == "C" else v
        lam = 1.0 / max(Cv * n, 1e-9)
        if kernel == 0:
            Ztr, Zva = Xtr, Xva
        else:
            Ztr = rbf_kernel(Xtr, Xtr, gv)
            Zva = rbf_kernel(Xva, Xtr, gv)
        s = solve(Ztr, ytr, lam, iters)
        ftr = np.sign(Ztr @ s["u"] + s["b"])
        fva = np.sign(Zva @ s["u"] + s["b"])
        tr.append(float(np.mean(ftr != ytr)))
        va.append(float(np.mean(fva != yva)))
    return tr, va


def _level_curve(gx: np.ndarray, gy: np.ndarray, Z: np.ndarray, level: float) -> list[list[float]]:
    """逐行找 Z=row 上 f=level 的穿越点（线性插值）——画出间隔带。"""
    out: list[list[float]] = []
    for i in range(Z.shape[0]):
        d = Z[i] - level
        hits = np.flatnonzero(np.sign(d[:-1]) != np.sign(d[1:]))
        if hits.size == 0:
            continue
        j = int(hits[np.argmin(np.abs(d[hits]))])
        t = d[j] / (d[j] - d[j + 1]) if abs(d[j] - d[j + 1]) > 1e-12 else 0.0
        out.append([util.num(gx[j] + t * (gx[j + 1] - gx[j])), util.num(gy[i]), 0.0])
    return out
