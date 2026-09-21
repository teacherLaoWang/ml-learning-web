"""t-SNE 数值内核：纯 NumPy 的 KD96 变体。

流水线（每一步都是教学要点）：
  1) 高维配对平方距离 Dᵢⱼ；
  2) 逐点二分搜索 βᵢ，使条件分布 P_{j|i} 的熵恰为 log2(perplexity)（困惑度=有效邻居数）；
  3) P 对称化 Pᵢⱼ = (P_{j|i}+P_{i|j})/(2n)，前 100 步乘 early exaggeration ×4；
  4) 低维用学生 t 分布 Qᵢⱼ ∝ (1+‖yᵢ−yⱼ‖²)⁻¹（重尾 → 天然撑开「拥挤问题」）；
  5) 梯度 ∂KL/∂yᵢ = 4Σⱼ(pᵢⱼ−qᵢⱼ)(yᵢ−yⱼ)(1+‖yᵢ−yⱼ‖²)⁻¹，带动量的梯度下降。
样本量固定 168（140~200 之间）：距离矩阵是 O(n²)，这是浏览器可交互的量级上限。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.ml import datasets, util
from app.ml.kmeans import lloyd

KEY = "tsne"
N_POINTS = 168
EARLY_EXAG = 4.0
EARLY_ITERS = 100


def sq_pairwise(Y: np.ndarray) -> np.ndarray:
    d2 = np.sum(Y * Y, axis=1)
    return np.maximum(d2[:, None] + d2[None, :] - 2.0 * (Y @ Y.T), 0.0)


def joint_from_affinities(D: np.ndarray, perp: float) -> tuple[np.ndarray, np.ndarray]:
    """逐点 β 的二分搜索（指数扩界 + 折半），再对称化归一。返回 (P, β)。"""
    n = D.shape[0]
    target = np.log2(max(float(perp), 1.0001))
    Di = D.copy()
    np.fill_diagonal(Di, np.inf)  # p_ii = 0
    beta = np.ones(n)
    bmin = np.full(n, 1e-12)
    bmax = np.full(n, 1e12)
    Pcond = np.zeros((n, n))
    for _ in range(60):
        Pcond = _cond(np.exp(-beta[:, None] * np.minimum(Di, 1e8)))
        H = _entropy_bits(Pcond)
        too_flat = H > target  # 熵太大 → 分布太平 → β 太小
        bmin = np.where(too_flat, beta, bmin)
        bmax = np.where(too_flat, bmax, beta)
        beta = np.where(too_flat, beta * 2.0, beta / 2.0)
        beta = np.clip(beta, 1e-12, 1e12)
        if np.all(np.abs(H - target) < 1e-5):
            break
    beta = 0.5 * (bmin + np.where(bmax > 1e11, beta, bmax))
    Pcond = _cond(np.exp(-beta[:, None] * np.minimum(Di, 1e8)))
    P = (Pcond + Pcond.T) / (2.0 * n)
    P = np.maximum(P, 1e-12)
    np.fill_diagonal(P, 0.0)
    P = P / P.sum()
    return P, beta


def _cond(Pk: np.ndarray) -> np.ndarray:
    """按行归一化；整行全 0（β 过大）时退化为均匀分布，避免 NaN。"""
    Pk = np.where(np.isfinite(Pk), Pk, 0.0)
    np.fill_diagonal(Pk, 0.0)
    Z = Pk.sum(axis=1)
    bad = Z < 1e-300
    out = Pk / np.where(bad, 1.0, Z)[:, None]
    if bad.any():
        out[bad] = 1.0 / max(Pk.shape[0] - 1, 1)
        np.fill_diagonal(out, 0.0)
    return out


def _entropy_bits(P: np.ndarray) -> np.ndarray:
    """按行的熵（bit）：0·log0 记为 0，用 1e-300 下限避免 log2(0) 警告。"""
    Pc = np.clip(P, 1e-300, None)
    return -np.sum(Pc * np.log2(Pc), axis=1)


def gradient(Y: np.ndarray, P: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    """教科书式梯度：∂C/∂yᵢ = 4Σⱼ(pᵢⱼ−qᵢⱼ)(yᵢ−yⱼ)(1+‖yᵢ−yⱼ‖²)⁻¹。"""
    num = 1.0 / (1.0 + sq_pairwise(Y))
    np.fill_diagonal(num, 0.0)
    Z = max(float(num.sum()), 1e-12)
    Q = num / Z
    kl = float(np.sum(P * np.log(np.maximum(P, 1e-12) / np.maximum(Q, 1e-12))))
    M = (P - Q) * num
    grad = 4.0 * (M.sum(axis=1)[:, None] * Y - M @ Y)
    return grad, kl, Q


def optimize(P: np.ndarray, eta: float, iters: int, seed: int, dims: int = 2):
    """带动量的梯度下降 + early exaggeration；返回最终嵌入与每步 (kl, gradnorm)。"""
    g = util.rng(seed, 91)
    n = P.shape[0]
    Y = g.normal(0.0, 1e-4, (n, dims))
    vel = np.zeros_like(Y)
    out = []
    for it in range(int(iters)):
        scale = EARLY_EXAG if it < min(EARLY_ITERS, int(iters)) else 1.0
        grad, kl, _ = gradient(Y, P * scale)
        mom = 0.5 if it < EARLY_ITERS else 0.8
        vel = mom * vel - eta * grad
        gn = float(np.linalg.norm(grad))
        if not np.isfinite(gn):
            break
        Y = Y + vel
        Y -= Y.mean(axis=0)
        out.append({"it": it, "kl": float(min(kl, 1e6)), "gnorm": gn,
                    "Y": Y.copy(), "exag": scale > 1.0})
    return Y, out


def run(params: dict[str, Any], seed: int, steps: int) -> dict[str, Any]:
    perp = float(params["perp"])
    eta = float(params["lr"])
    k = max(2, int(params["clusters"]))
    dim = max(3, int(params["dim"]))
    iters = max(20, min(int(steps), 400))

    X, truth = datasets.cluster_gaussians(seed, n=N_POINTS, k=k, dim=dim, sep=6.0, sigma=1.0)
    D = sq_pairwise(X)
    P, beta = joint_from_affinities(D, perp)
    Y, hist = optimize(P, eta, iters, seed)
    T = len(hist)
    kl_final = hist[-1]["kl"] if T else float("nan")

    # 嵌入上的 ARI：拿 K-Means(k=真簇数) 给二维坐标贴标签，衡量「团还认不认得出来」
    res = lloyd(Y, k, 1, seed, 30)
    ari = util.adjusted_rand_index(truth, res["labels"])

    # ---- 困惑度对比：同一份数据，不同 perplexity 各跑一次，看簇的松紧
    grid = [2, 5, 12, 25, 50]
    tight: list[float] = []
    for pp in grid:
        Pi, _ = joint_from_affinities(D, pp)
        Yi, _ = optimize(Pi, eta, min(iters, 150), seed)
        cen = np.array([Yi[truth == c].mean(axis=0) for c in range(k)])
        intra = float(np.mean([np.linalg.norm(Yi[truth == c] - cen[c], axis=1).mean()
                               for c in range(k)]))
        inter = float(np.mean([np.linalg.norm(cen[a] - cen[b])
                               for a in range(k) for b in range(a + 1, k)]))
        tight.append(intra / max(inter, 1e-9))

    # ---- 高维原始数据的 3D 切片（取方差最大的三个方向，等价于先看 PCA 再 t-SNE）
    Xc = X - X.mean(axis=0)
    lam, vec = np.linalg.eigh(Xc.T @ Xc / max(len(X) - 1, 1))
    order = np.argsort(lam)[::-1][:3]
    V = vec[:, order]
    raw3 = Xc @ V
    var_share = lam[order] / lam.sum()
    pts = [util.point3(raw3[i, 0], raw3[i, 1], raw3[i, 2], int(truth[i]), 1.1)
           for i in range(len(raw3))]
    raw = util.cloud(pts, legend=[{"label": f"真值簇 {c}", "color": util.color_of(c)} for c in range(k)],
                     projection={"origin": [0.0, 0.0, 0.0],
                                 "normal": [util.num(v) for v in vec[:, order[2]]],
                                 "label": "被切掉的方向"})

    ep = [h["it"] for h in hist]
    embed_curves = [util.curve(f"c{c}", f"簇 {c}（{int(np.sum(truth == c))} 点）",
                               Y[truth == c, 0], Y[truth == c, 1], color=util.color_of(c))
                    for c in range(k)]
    # 单点轨迹：把跑得最远的那个点画出来，前端可以顺着它做动画
    moves = np.linalg.norm(hist[-1]["Y"] - hist[0]["Y"], axis=1) if T > 1 else np.zeros(len(Y))
    star = int(np.argmax(moves))
    embed_curves.append(util.curve("trail", f"移动最远的点 #{star} 的轨迹",
                                   [h["Y"][star, 0] for h in hist],
                                   [h["Y"][star, 1] for h in hist], dash=True, color="#111827"))
    lim = float(max(np.abs(Y).max(), 1e-3))
    embed = util.lines2d(embed_curves, "嵌入维度 1", "嵌入维度 2",
                         xr=(-lim, lim), yr=(-lim, lim))

    brk = float(min(EARLY_ITERS, iters) - 1)
    kl_max = max([h["kl"] for h in hist] or [1.0])
    stress = util.lines2d(
        [util.curve("kl", "KL(Q‖P)", ep, [h["kl"] for h in hist], color="#7c3aed"),
         util.curve("exag", "early exaggeration 结束", [brk, brk], [0.0, kl_max],
                    dash=True, color="#94a3b8")],
        "迭代步", "KL 散度", xr=(0, float(iters - 1)), yr=(0.0, kl_max))

    knn_eff = float(np.exp2(target_entropy(beta, D, perp))) if T else 0.0
    return util.finish(KEY, {
        "backend": "numpy",
        "metrics": {"kl": kl_final, "ari": ari},
        "series": [
            util.ser("kl", "KL(Q‖P)", ep, [h["kl"] for h in hist], "iter", "KL"),
            util.ser("gradnorm", "梯度范数", ep, [h["gnorm"] for h in hist], "iter", "‖∂KL/∂Y‖"),
            util.ser("cost", "每步下降量", ep,
                     [0.0] + [hist[i]["kl"] - hist[i + 1]["kl"] for i in range(len(hist) - 1)],
                     "iter", "ΔKL"),
        ],
        "table": [
            util.tab("p", "高维概率 P（困惑度→β 二分搜索）", [
                {"name": "perplexity", "value": f"{perp:g}",
                 "note": f"目标熵 = log₂{perp:g} = {np.log2(max(perp, 1.0001)):.4f} bit"},
                {"name": "β 最小 / 中位 / 最大", "value": f"{beta.min():.4g} / {np.median(beta):.4g}"
                         f" / {beta.max():.4g}",
                 "note": "β 大=只看见最近的邻居（簇紧），β 小=视野宽（簇松）"},
                {"name": "有效邻居数（几何平均）", "value": f"{knn_eff:.2f}"},
                {"name": "Σpᵢⱼ（对称化并归一后）", "value": f"{float(P.sum()):.4f}"},
                {"name": "max Pᵢⱼ", "value": f"{float(P.max()):.6f}",
                 "note": "孤独点自己给自己分配了大质量（p_ii=0 后仍留痕）"},
            ]),
            util.tab("opt", "优化", [
                {"name": "迭代 / 学习率 η / 动量", "value": f"{T} / {eta:g} / 0.5→0.8"},
                {"name": "early exaggeration", "value": f"×{EARLY_EXAG:g}，前 {EARLY_ITERS} 步",
                 "note": "把 P 放大 → 吸引力变强 → 先把团压紧，再松开细看结构"},
                {"name": "最终 KL", "value": f"{kl_final:.4f}", "truth": f"初始 {hist[0]['kl']:.4f}",
                 "delta": f"{hist[0]['kl'] - kl_final:.4f}"},
                {"name": "原始维度 / 样本数", "value": f"{dim} → 2",
                 "note": f"n={N_POINTS}，距离矩阵 {N_POINTS}×{N_POINTS}（O(n²) 是硬约束）"},
                {"name": "嵌入 ARI（K-Means 后与真值比）", "value": f"{ari:.4f}"},
                {"name": "3D 切片保留的高维方差", "value": f"{float(var_share.sum()) * 100:.1f}%",
                 "note": "切片方向 λ = " + ", ".join(f"{v:.2f}" for v in var_share)
                         + "（先 PCA 再看 t-SNE，簇分得开不开一目了然）"},
            ]),
        ],
        "visualMap": {
            "raw": raw,
            "embed": embed,
            "stress": stress,
            "perp": util.bars([f"perp={p}" for p in grid], tight, unit="",
                              ylab="类内半径 / 类间距", xlab="困惑度"),
        },
    })


def target_entropy(beta: np.ndarray, D: np.ndarray, perp: float) -> float:
    """实际达到的平均熵（bit），用来核对二分搜索准不准。"""
    Di = D.copy()
    np.fill_diagonal(Di, np.inf)
    Pk = np.exp(-beta[:, None] * np.minimum(Di, 1e6))
    Pcond = Pk / np.maximum(Pk.sum(axis=1, keepdims=True), 1e-300)
    return float(np.mean(_entropy_bits(Pcond)))
