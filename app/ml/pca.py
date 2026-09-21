"""PCA 数值内核：协方差矩阵特征分解（numpy.linalg.eigh），方差最大化视角。

教学主线：
* 主成分 = 协方差矩阵的正交特征向量，解释方差比 = λᵢ / Σλ（所以 Σ=1，方差守恒）；
* 数据是「可调方差 + 可调倾斜角」的椭球，PC₁ 应当精确指回真主轴；
* 降到 k 维的重构误差 = 剩下的特征值之和 / 总方差，只跟 λ 有关，跟旋转无关。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.ml import datasets, util

KEY = "pca"
N_SAMPLES = 240


def decompose(X: np.ndarray) -> dict[str, Any]:
    mu = X.mean(axis=0)
    Xc = X - mu
    cov = (Xc.T @ Xc) / max(len(X) - 1, 1)
    lam, vec = np.linalg.eigh(cov)  # 对称矩阵：eigh 给出实特征值 + 正交特征向量
    order = np.argsort(lam)[::-1]
    lam = np.maximum(lam[order], 0.0)
    vec = vec[:, order]
    for j in range(vec.shape[1]):  # 固定符号，让同 seed 的图不翻转（方向指向 +x 分量较大的一侧）
        jmax = int(np.argmax(np.abs(vec[:, j])))
        if vec[jmax, j] < 0:
            vec[:, j] = -vec[:, j]
    total = float(lam.sum())
    return {"mu": mu, "Xc": Xc, "cov": cov, "lam": lam, "vec": vec,
            "evr": lam / max(total, 1e-12), "total": total}


def run(params: dict[str, Any], seed: int, steps: int) -> dict[str, Any]:
    whiten = bool(int(params["whiten"]))
    d = datasets.anisotropic3d(seed, n=N_SAMPLES, sx=float(params["sx"]),
                               sy=float(params["sy"]), tilt=float(params["tilt"]))
    X = d["X"]
    msq_total = float(np.mean(np.sum((X - X.mean(axis=0)) ** 2, axis=1)))
    dec = decompose(X)
    lam, vec, mu, total = dec["lam"], dec["vec"], dec["mu"], dec["total"]
    evr = dec["evr"]

    scores = dec["Xc"] @ vec  # 旋转后的坐标
    scaled = scores / np.sqrt(np.maximum(lam, 1e-12)) if whiten else scores

    # 重构：X̂ₖ = μ + Σ_{i≤k} tᵢ vᵢ；未解释方差比 = Σ_{i>k} λᵢ / Σλ
    recon_rows = []
    errs = []
    for kk in (1, 2, 3):
        Xhat = mu + scores[:, :kk] @ vec[:, :kk].T
        sse = float(np.mean(np.sum((X - Xhat) ** 2, axis=1)))  # ddof=0 的均方残差
        ratio = float(np.clip(sse / max(msq_total, 1e-12), 0.0, 1.0))
        theory = float(np.clip(1.0 - evr[:kk].sum(), 0.0, 1.0))
        errs.append(ratio)
        recon_rows.append({"name": f"保留 {kk} 个主成分", "value": f"{ratio:.6f}",
                           "truth": f"{theory:.6f}", "delta": f"{abs(ratio - theory):.6f}",
                           "note": f"重构后平均距离 ‖x−x̂‖ = {np.sqrt(max(sse, 0.0)):.3f}"})

    ang = np.degrees(float(np.arccos(np.clip(abs(np.dot(vec[:, 0], d["trueAxes"][:, 0])), 0, 1))))
    corr = np.corrcoef(X.T)

    # ---- 主成分方向（箭头长度 = 3σ = 3√λ）
    arrows = []
    for j in range(3):
        v = vec[:, j] * (3.0 * float(np.sqrt(lam[j])))
        arrows.append({"from": [util.num(mu[0]), util.num(mu[1]), util.num(mu[2])],
                       "to": [util.num(mu[i] + v[i]) for i in range(3)],
                       "color": ["#dc2626", "#2563eb", "#0d9488"][j],
                       "label": f"PC{j + 1}（方差 {lam[j]:.2f}，解释 {evr[j] * 100:.1f}%）",
                       "dash": j == 2})
    sub = np.linspace(0, len(X) - 1, min(140, len(X))).astype(int)
    pts = [util.point3(X[i, 0], X[i, 1], X[i, 2], 0, 0.8) for i in sub]
    axes_vis = {"arrows": arrows, "points": pts,
                "axes": {"x": "x₁", "y": "x₂", "z": "x₃"}}

    # ---- 投影面：PC₁–PC₂ 张成的平面（用 x₃ = f(x₁,x₂) 表达；法向是 PC₃）
    nrm = vec[:, 2]
    gx = np.linspace(float(X[:, 0].min()), float(X[:, 0].max()), 41)
    gy = np.linspace(float(X[:, 1].min()), float(X[:, 1].max()), 41)
    if abs(nrm[2]) < 1e-3:  # 投影面垂直于 (x₁,x₂) 平面时改画法向本身
        Z = np.zeros((len(gy), len(gx)))
    else:
        Z = mu[2] - (nrm[0] * (gx[None, :] - mu[0]) + nrm[1] * (gy[:, None] - mu[1])) / nrm[2]
    Xhat2 = mu + scores[:, :2] @ vec[:, :2].T
    shadow = [util.point3(Xhat2[i, 0], Xhat2[i, 1], Xhat2[i, 2], 1, 0.9) for i in sub]
    proj = util.cloud(pts + shadow,
                      legend=[{"label": "原始点", "color": util.color_of(0)},
                              {"label": "降到 2 维后的重构点", "color": util.color_of(1)}],
                      bound=util.boundary(gx, gy, Z, "x₁", "x₂", "PC₁–PC₂ 投影面"),
                      projection={"origin": [util.num(mu[0]), util.num(mu[1]), util.num(mu[2])],
                                  "normal": [util.num(v) for v in nrm],
                                  "label": f"被丢弃的方向 PC₃（方差 {lam[2]:.2f}）"})

    return util.finish(KEY, {
        "backend": "numpy",
        "metrics": {"evr": float(evr[0]), "err": errs[1]},
        "series": [
            util.ser("cum", "累计解释方差比", [1, 2, 3], np.cumsum(evr), "主成分数 k", "累计 evr"),
            util.ser("eig", "特征值 λᵢ（各方向方差）", [1, 2, 3], lam, "主成分序号", "λ"),
        ],
        "table": [
            util.tab("recon", "重构误差（降维丢掉了多少信息）", recon_rows),
            util.tab("axis", "主轴核对", [
                {"name": "PC₁ 方向", "value": "(" + ", ".join(f"{v:.3f}" for v in vec[:, 0]) + ")"},
                {"name": "真主轴方向", "value": "(" + ", ".join(f"{v:.3f}" for v in d["trueAxes"][:, 0]) + ")"},
                {"name": "两者夹角", "value": f"{ang:.2f}°", "note": "倾斜角参数 θ = "
                        f"{params['tilt']}°；夹角越小说明特征分解越准"},
                {"name": "Σλ / 总方差", "value": f"{total:.4f}",
                 "truth": f"{float(np.var(X, axis=0).sum()):.4f}"},
                {"name": "各维得分方差（均值）", "value": f"{float(np.var(scaled, axis=0).mean()):.4f}",
                 "note": "已白化：除以 √λ，把椭球捏回单位球（每维方差 = 1）" if whiten
                         else "未白化：这个均值就是 (λ₁+λ₂+λ₃)/3，各维方差差别极大"},
            ]),
        ],
        "visualMap": {
            "axes": axes_vis,
            "proj": proj,
            "ratio": util.bars([f"PC{i + 1}" for i in range(3)], evr, unit="",
                               ylab="解释方差比", xlab="主成分"),
            "corr": util.matrix(["x₁", "x₂", "x₃"], corr, title="特征相关矩阵（PCA 在对角化它）"),
        },
    })
