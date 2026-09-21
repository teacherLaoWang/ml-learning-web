"""教学演示数据集：全部可复现（`numpy.random.default_rng(seed)`），同 seed 同数据。

约定：所有函数返回 NumPy 数组，特征为 `(n, d)`，标签为 `(n,)`；
`salt` 只在同一个算法内部派生副流（例如训练/验证拆分、初始化）时使用。
"""

from __future__ import annotations

import numpy as np


def _gen(seed: int, salt: int = 0) -> np.random.Generator:
    return np.random.default_rng([abs(int(seed)) % (2**31), abs(int(salt))])


# ---------------------------------------------------------------- 回归


def quad_1d(seed: int, n: int = 60, noise: float = 0.25, span: float = 2.0) -> dict:
    """真实关系 y = 1.2x + 0.35x² + ε（app/content/lessons/linreg.py 的口径）。

    模型只有两个待学参数：ŷ = w₁·x + w₂·(x²)，损失面因此是一个可以在 (w₁,w₂) 平面上
    画全的二次碗。`spread`（特征尺度比）在算法侧乘到第二个特征上。
    """
    g = _gen(seed)
    x = np.sort(g.uniform(-span, span, int(n)))
    truth = {"w1": 1.2, "w2": 0.35}
    y = truth["w1"] * x + truth["w2"] * x * x + g.normal(0.0, float(noise), int(n))
    return {"x": x, "y": y, "truth": truth}


# ---------------------------------------------------------------- 二维分类


def blobs(seed: int, n: int = 160, sep: float = 1.6, sigma: float = 1.0,
          skew: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """两个各向同性高斯团。`sep`=中心距，`skew` 控制第二维是否也分开。

    `skew=0` 时两个类只在 x₁ 上不同（x₂ 成为纯噪声特征），逻辑回归用它演示
    「无关特征会抖，但改变不了决策，只有正则化能把它的权重压小」。
    """
    g = _gen(seed)
    n = int(n)
    n0 = n // 2
    c = np.array([[-sep, -sep * skew], [sep, sep * skew]])
    X = np.vstack([g.normal(c[0], sigma, (n0, 2)), g.normal(c[1], sigma, (n - n0, 2))])
    y = np.r_[np.zeros(n0, dtype=int), np.ones(n - n0, dtype=int)]
    return X, y


def moons(seed: int, n: int = 200, noise: float = 0.18) -> tuple[np.ndarray, np.ndarray]:
    """双月牙（sklearn make_moons 的同款几何）：线性不可分，KNN/核方法的经典素材。"""
    g = _gen(seed)
    n = int(n)
    n0 = n // 2
    n1 = n - n0
    t0 = np.linspace(0.0, np.pi, n0)
    t1 = np.linspace(0.0, np.pi, n1)
    outer = np.column_stack([np.cos(t0) + 1.0, np.sin(t0)])
    inner = np.column_stack([-np.cos(t1), -np.sin(t1) + 0.5])
    X = np.vstack([outer, inner]) + g.normal(0.0, noise, (n, 2))
    y = np.r_[np.zeros(n0, dtype=int), np.ones(n1, dtype=int)]
    return X, y


def circles(seed: int, n: int = 200, ratio: float = 0.45, noise: float = 0.12) -> tuple[np.ndarray, np.ndarray]:
    """同心圆：内圈=0，外环=1。"""
    g = _gen(seed)
    n = int(n)
    n0 = n // 2
    r0 = g.uniform(0.0, ratio, n0)
    r1 = g.uniform(0.75, 1.0, n - n0)
    a0, a1 = g.uniform(0, 2 * np.pi, n0), g.uniform(0, 2 * np.pi, n - n0)
    X = np.vstack([np.column_stack([np.cos(a0) * r0, np.sin(a0) * r0]),
                   np.column_stack([np.cos(a1) * r1, np.sin(a1) * r1])])
    X = X + g.normal(0.0, noise, X.shape)
    y = np.r_[np.zeros(n0, dtype=int), np.ones(n - n0, dtype=int)]
    return X, y


def xor(seed: int, n: int = 120, sigma: float = 0.18, amp: float = 0.7) -> tuple[np.ndarray, np.ndarray]:
    """四角异或：与 nn-forward-backprop.html 的 XOR 数据同口径（角点 (±amp, ±amp)）。

    标签：右上/左下 = 0，左上/右下 = 1。
    """
    g = _gen(seed)
    n = int(n)
    corners = np.array([[-amp, -amp, 0.0], [-amp, amp, 1.0], [amp, -amp, 1.0], [amp, amp, 0.0]])
    per = max(n // 4, 1)
    X = np.vstack([g.normal(c[:2], sigma, (per, 2)) for c in corners])
    y = np.repeat(corners[:, 2].astype(int), per)
    extra = n - len(y)
    if extra > 0:  # 余数补在前 extra 个角点上，保持标签与位置一致
        X = np.vstack([X, g.normal(corners[:extra, :2], sigma, (extra, 2))])
        y = np.r_[y, corners[:extra, 2].astype(int)]
    elif extra < 0:
        X, y = X[:n], y[:n]
    return X, y


# ---------------------------------------------------------------- 三维点云


def gaussian_blobs3d(seed: int, n: int = 210, k: int = 3, gap: float = 3.4,
                     sigma: float = 0.85) -> tuple[np.ndarray, np.ndarray]:
    """K-Means 用：真值簇放在正多边形 + 交替高度上，`gap` 控制簇间距（肘部法则的自变量）。"""
    g = _gen(seed)
    n, k = int(n), max(2, int(k))
    ang = np.arange(k) * 2 * np.pi / k
    centers = np.column_stack([np.cos(ang) * gap, np.sin(ang) * gap,
                               np.linspace(-gap * 0.5, gap * 0.5, k)])
    per = np.full(k, n // k)
    per[: n - int(per.sum())] += 1
    X = np.vstack([g.normal(centers[i], sigma, (int(per[i]), 3)) for i in range(k)])
    y = np.repeat(np.arange(k), per)
    return X, y


def anisotropic3d(seed: int, n: int = 240, sx: float = 4.0, sy: float = 1.4,
                  tilt: float = 32.0) -> dict:
    """PCA 用：可调方差 + 可调倾斜角的椭球（真主轴已知，方便核对特征向量）。"""
    g = _gen(seed)
    n = int(n)
    th = np.deg2rad(float(tilt))
    rot = np.array([[np.cos(th), -np.sin(th), 0.0],
                    [np.sin(th), np.cos(th), 0.0],
                    [0.0, 0.0, 1.0]])
    scales = np.array([float(sx), float(sy), 0.55])  # 第三轴固定很扁：天然适合降到二维
    A = rot @ np.diag(scales)
    X = g.normal(0, 1, (n, 3)) @ A.T + g.normal(0, 0.15, (n, 3)) * 0.2
    cov = A @ A.T
    ev, evec = np.linalg.eigh(cov)
    order = np.argsort(ev)[::-1]
    return {"X": X, "A": A, "eigvals": ev[order], "eigvecs": evec[:, order],
            "trueAxes": rot, "varTotal": float(np.trace(cov))}


def cluster_gaussians(seed: int, n: int = 168, k: int = 4, dim: int = 5,
                      sep: float = 6.0, sigma: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """t-SNE 用：`dim` 维空间里 k 团高斯（簇间距离在三维切片里依然分得开）。"""
    g = _gen(seed)
    n, k, dim = int(n), max(2, int(k)), max(2, int(dim))
    step = 2 * np.pi / k
    centers = np.zeros((k, dim))
    for i in range(k):
        a, b = i * step, (i * step) * 0.7 + 0.4
        centers[i, 0] = np.cos(a) * sep
        centers[i, 1] = np.sin(a) * sep
        if dim > 2:
            centers[i, 2] = np.cos(b) * sep * 0.8
        if dim > 3:
            centers[i, 3:] = np.sin(b + np.arange(dim - 3) * 0.8) * sep * 0.6
    per = np.full(k, n // k)
    per[: n - int(per.sum())] += 1
    X = np.vstack([g.normal(centers[i], sigma, (int(per[i]), dim)) for i in range(k)])
    y = np.repeat(np.arange(k), per)
    return X, y


# ---------------------------------------------------------------- 卷积演示


def cnn_pattern(kind: int, size: int = 16) -> np.ndarray:
    """程序化 16×16 灰度图案：无随机数，纯几何，便于解释卷积核在扫什么。"""
    idx = np.arange(size)
    yy, xx = np.meshgrid(idx, idx, indexing="ij")
    cx = cy = (size - 1) / 2.0
    k = int(kind) % 4
    if k == 0:  # 斜边
        img = np.clip((xx - yy + size * 0.25) / (size * 0.5), 0.0, 1.0)
    elif k == 1:  # 圆环
        r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (size * 0.5)
        img = np.exp(-((r - 0.62) ** 2) / 0.02)
    elif k == 2:  # 棋盘
        img = ((xx // 3 + yy // 3) % 2).astype(float) * 0.9 + 0.05
    else:  # 字母「L」+ 笔画
        img = np.zeros((size, size))
        img[3:13, 4:6] = 1.0
        img[10:12, 4:11] = 1.0
        img[2:4, 9:14] = 0.6
    return img.astype(float)
