"""K-Means 数值内核：Lloyd 交替最小化（指派步 + 更新步），支持随机 / K-Means++ 初始化。

教学主线：
* 目标函数 J = Σ‖xᵢ−μ_{cᵢ}‖² 在两步中都只降不升 ⇒ inertia 曲线单调不升；
* 初始化决定收在哪个局部极小（K-Means++ 用 D² 采样把中心撒开）；
* 肘部法则：数据里其实只有 4 个真簇，K=4 之后每加一簇收益锐减。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.ml import datasets, util

KEY = "kmeans"
TRUE_K = 4  # 数据里埋的真簇数：肘部就在它这里拐弯


def sq_dist(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    d = A[:, None, :] - B[None, :, :]
    return np.einsum("ijk,ijk->ij", d, d)


def init_centers(X: np.ndarray, k: int, mode: int, g: np.random.Generator) -> np.ndarray:
    if mode == 0:  # 随机取点
        idx = g.choice(len(X), size=min(k, len(X)), replace=False)
        return X[idx].copy()
    # K-Means++：D² 加权采样，先离群再撒点
    first = int(g.integers(len(X)))
    centers = [X[first]]
    d2 = sq_dist(X, np.array([X[first]])).ravel()
    for _ in range(min(k, len(X)) - 1):
        tot = float(d2.sum())
        if tot <= 1e-12:
            centers.append(X[int(g.integers(len(X)))])
            d2 = np.minimum(d2, sq_dist(X, np.array([centers[-1]])).ravel())
            continue
        p = d2 / tot
        j = int(g.choice(len(X), p=p))
        centers.append(X[j])
        d2 = np.minimum(d2, sq_dist(X, np.array([X[j]])).ravel())
    return np.array(centers)


def assign(X: np.ndarray, C: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    D = sq_dist(X, C)
    lab = np.argmin(D, axis=1)
    return lab, D[np.arange(len(X)), lab]


def lloyd(X: np.ndarray, k: int, mode: int, seed: int, steps: int) -> dict[str, Any]:
    """返回完整轨迹：每轮的质心、inertia、指派。"""
    g = util.rng(seed, 11)
    C = init_centers(X, k, mode, g)
    labels, dmin = assign(X, C)
    traj = [{"C": C.copy(), "labels": labels.copy(),
             "inertia": float(np.sum(dmin)), "shift": float("nan"), "delta": float("nan")}]
    for it in range(int(steps)):
        newC = np.array([X[labels == j].mean(axis=0) if np.any(labels == j) else C[j]
                         for j in range(len(C))])
        shift = float(np.linalg.norm(newC - C))
        labels, dmin = assign(X, newC)
        inertia = float(np.sum(dmin))
        traj.append({"C": newC.copy(), "labels": labels.copy(), "inertia": inertia,
                     "shift": shift, "delta": inertia - traj[-1]["inertia"]})
        C = newC
        if shift < 1e-9:
            break
    return {"centers": C, "labels": labels, "traj": traj}


def elbow_point(ks: list[int], inertia: list[float]) -> int:
    """肘部 = 归一化曲线上离「首尾弦」最远的点（Kneedle 判据，比「最大降幅」稳）。

    inertia 是凸递减曲线：归一化 y=(J−Jmin)/(Jmax−Jmin) 后整条曲线落在弦 1−x 的**下方**，
    弦与曲线间距最大处就是「再加一簇突然不划算」的那个 K。
    """
    ys = np.asarray(inertia, dtype=float)
    span = float(ys.max() - ys.min())
    if span <= 1e-12 or len(ys) < 3:
        return int(ks[0])
    x = (np.asarray(ks, dtype=float) - ks[0]) / max(ks[-1] - ks[0], 1)
    y = (ys - float(ys.min())) / span
    return int(ks[int(np.argmax((1.0 - x) - y))])


def run(params: dict[str, Any], seed: int, steps: int) -> dict[str, Any]:
    k = max(1, int(params["k"]))
    mode = int(params["init"])
    gap = float(params["gap"])
    n = int(params["n"])

    X, truth = datasets.gaussian_blobs3d(seed, n=n, k=TRUE_K, gap=gap)
    res = lloyd(X, k, mode, seed, max(6, min(int(steps), 120)))
    traj = res["traj"]
    labels = res["labels"]
    ari = util.adjusted_rand_index(truth, labels)

    # 随机初始化有时会退化（空簇/局部极小）：把两种初始化都跑一遍做对照
    alt = lloyd(X, k, 1 - mode, seed, max(6, min(int(steps), 120)))

    inertia = [t["inertia"] for t in traj]
    shifts = [0.0 if np.isnan(t["shift"]) else t["shift"] for t in traj]

    # 肘部法则：同一份数据，K=1..8 各跑一次
    ks = list(range(1, 9))
    elbows = []
    for kk in ks:
        r = lloyd(X, kk, 1, seed, 40)
        elbows.append(r["traj"][-1]["inertia"])
    knee = elbow_point(ks, elbows)

    points = [util.point3(X[i, 0], X[i, 1], X[i, 2], int(labels[i]), 1.0) for i in range(len(X))]
    hulls = [{"label": f"质心 {j} 的移动轨迹", "mode": "path", "color": util.color_of(j),
              "points": [[util.num(t["C"][j, 0]), util.num(t["C"][j, 1]), util.num(t["C"][j, 2])]
                         for t in traj if j < t["C"].shape[0]]}
             for j in range(k)]
    legend = [{"label": f"簇 {j}（{int(np.sum(labels == j))} 点）", "color": util.color_of(j)}
              for j in range(k)]
    centroids = [{"x": util.num(c[0]), "y": util.num(c[1]), "z": util.num(c[2]),
                  "label": j, "size": 1.4, "step": len(traj) - 1}
                 for j, c in enumerate(traj[-1]["C"])]
    clusters = util.cloud(points, legend=legend, hulls=hulls, centroids=centroids)

    inert_line = util.lines2d(
        [util.curve("inertia", f"K={k} · {'K-Means++' if mode else '随机'}初始化",
                    range(len(inertia)), inertia, color="#2563eb"),
         util.curve("alt", f"对照：{'随机' if mode else 'K-Means++'}初始化",
                    range(len(alt["traj"])), [t["inertia"] for t in alt["traj"]],
                    dash=True, color="#ea580c")],
        "迭代轮次", "inertia Σ‖x−μ‖")

    return util.finish(KEY, {
        "backend": "numpy",
        "metrics": {"inertia": inertia[-1], "ari": ari},
        "series": [
            util.ser("inertia", "惯性 inertia", range(len(inertia)), inertia, "iter", "inertia"),
            util.ser("shift", "质心位移 ‖Δμ‖", range(len(shifts)), shifts, "iter", "‖Δμ‖"),
            util.ser("delta", "每轮下降量 ΔJ", range(len(inertia)),
                     [0.0] + [inertia[i] - inertia[i + 1] for i in range(len(inertia) - 1)],
                     "iter", "Δinertia"),
        ],
        "table": [
            util.tab("clusters", "各簇规模与紧凑度", [
                {"name": f"簇 {j}", "value": f"{int(np.sum(labels == j))} 点",
                 "truth": f"{int(np.sum(truth == j))} 点" if j < TRUE_K else None,
                 "note": (f"质心 ({res['centers'][j, 0]:.2f}, {res['centers'][j, 1]:.2f}, "
                          f"{res['centers'][j, 2]:.2f})，半径 "
                          f"{float(np.sqrt(np.mean(sq_dist(X[labels == j], res['centers'][j:j + 1])))) if np.any(labels == j) else 0.0:.2f}")}
                for j in range(k)]),
            util.tab("run", "本次运行", [
                {"name": "迭代轮数", "value": f"{len(traj) - 1}"},
                {"name": "最终 inertia", "value": f"{inertia[-1]:.4f}",
                 "truth": f"另一种初始化 {alt['traj'][-1]['inertia']:.4f}",
                 "delta": f"{abs(inertia[-1] - alt['traj'][-1]['inertia']):.4f}"},
                {"name": "肘部位置（离首尾弦最远）", "value": f"K={knee}",
                 "note": f"数据里真实簇数 = {TRUE_K}；两者一致时说明肘部判据可信"},
                {"name": "ARI（与真值簇的一致性）", "value": f"{ari:.4f}"},
            ]),
        ],
        "visualMap": {
            "clusters": clusters,
            "inertia": inert_line,
            "elbow": util.bars([f"K={kk}" for kk in ks], elbows, ylab="inertia", xlab="簇数 K"),
        },
    })
