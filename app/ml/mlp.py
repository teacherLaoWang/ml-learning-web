"""多层感知机数值内核：2 → H → 1（隐藏层 Sigmoid/tanh/ReLU，输出层 Sigmoid），
损失 L=(o−y)²，逐样本在线 SGD —— 数学口径与 ../nn-forward-backprop.html 完全一致。

手写反向传播（链式法则）：
    δₒ = ∂L/∂z = 2(o−y)·σ′(z) = 2(o−y)·o(1−o)
    ∂L/∂vᵢ = δₒhᵢ,  ∂L/∂bₒ = δₒ
    δⱼ = δₒ·vⱼ·φ′(zⱼ),  ∂L/∂w₁ⱼ = δⱼx₁,  ∂L/∂w₂ⱼ = δⱼx₂,  ∂L/∂bⱼ = δⱼ
若探测到 PyTorch，就用 autograd 把同一个网络、同一批初值、同一个样本顺序再跑一遍，
两条 loss 必须重合（±1e-5），并把 backend 标成 "torch"；没装则静默走 NumPy。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.ml import datasets, util
from app.ml.backend import torch_state

KEY = "mlp"
N_PER_CLASS = 50


# ---------------------------------------------------------------- 参数打包：[W(2H) | bₕ(H) | v(H) | bₒ(1)]


def n_params(H: int) -> int:
    return 4 * H + 1


def unpack(theta: np.ndarray, H: int):
    return (np.asarray(theta[:2 * H], dtype=float).reshape(H, 2),
            np.asarray(theta[2 * H:3 * H], dtype=float),
            np.asarray(theta[3 * H:4 * H], dtype=float), float(theta[4 * H]))


def pack(W: np.ndarray, bh: np.ndarray, v: np.ndarray, bo: float, H: int) -> np.ndarray:
    return np.concatenate([np.asarray(W, dtype=float).ravel(), np.asarray(bh, dtype=float),
                           np.asarray(v, dtype=float), [float(bo)]])


def _act(z: np.ndarray, kind: int) -> np.ndarray:
    if kind == 0:
        return util.sigmoid(z)
    if kind == 1:
        return np.tanh(z)
    return np.maximum(0.0, z)


def _act_deriv(z: np.ndarray, a: np.ndarray, kind: int) -> np.ndarray:
    if kind == 0:
        return a * (1.0 - a)
    if kind == 1:
        return 1.0 - a * a
    return (z > 0).astype(float)


def forward(theta: np.ndarray, X: np.ndarray, H: int, kind: int) -> dict[str, np.ndarray]:
    W, bh, v, bo = unpack(np.asarray(theta, dtype=float), H)
    X = np.atleast_2d(X)
    Z = X @ W.T + bh
    A = _act(Z, kind)
    o = util.sigmoid(A @ v + bo)
    return {"Z": Z, "A": A, "o": o}


def mean_loss(theta: np.ndarray, X: np.ndarray, t: np.ndarray, H: int, kind: int) -> float:
    o = forward(theta, X, H, kind)["o"]
    return float(np.mean((o - t) ** 2))


def mean_grad(theta: np.ndarray, X: np.ndarray, t: np.ndarray, H: int, kind: int):
    """(批量平均 loss, 批量平均梯度)。批量梯度 = 逐样本梯度的平均，这里一次算完。"""
    f = forward(theta, X, H, kind)
    o, A, Z = f["o"], f["A"], f["Z"]
    _, _, v, _ = unpack(np.asarray(theta, dtype=float), H)
    dzo = 2.0 * (o - t) * o * (1.0 - o) / len(t)  # ∂(平均 loss)/∂z
    dA = dzo[:, None] * v[None, :]
    dz = dA * _act_deriv(Z, A, kind)
    dW = dz.T @ X
    dbh = dz.sum(axis=0)
    dv = A.T @ dzo
    dbo = float(dzo.sum())
    return float(np.mean((o - t) ** 2)), pack(dW, dbh, dv, dbo, H)


def sample_grad(theta: np.ndarray, x: np.ndarray, ti: float, H: int, kind: int) -> np.ndarray:
    """单样本梯度（前向 + 反向各一遍），与参考页 computeSteps() 的每一项一一对应。

    训练循环为了少分配数组把同样的公式内联了（见 _epoch）；两者由测试保证等价
    （批量梯度 = 逐样本梯度的平均）。
    """
    W, bh, v, bo = unpack(np.asarray(theta, dtype=float), H)
    Z = W @ x + bh
    A = _act(Z, kind)
    o = float(util.sigmoid(float(A @ v + bo)))
    d3 = 2.0 * (o - ti) * o * (1.0 - o)
    dH = d3 * v * _act_deriv(Z, A, kind)
    return pack(np.outer(dH, x), dH, d3 * A, d3, H)


def init_theta(H: int, seed: int) -> np.ndarray:
    """与参考页一致：权重均匀落在 (−0.9, 0.9)，偏置全 0。"""
    g = util.rng(seed, 41)
    W = g.uniform(-0.9, 0.9, (H, 2))
    v = g.uniform(-0.9, 0.9, H)
    return pack(W, np.zeros(H), v, 0.0, H)


def data_for(data_kind: int, seed: int, sat: float):
    if data_kind == 0:
        X, y = datasets.blobs(seed, n=2 * N_PER_CLASS, sep=1.0, sigma=0.5, skew=0.35)
    elif data_kind == 1:
        X, y = datasets.xor(seed, n=4 * (N_PER_CLASS // 2), sigma=0.16, amp=0.7)
    else:
        X, y = datasets.circles(seed, n=2 * N_PER_CLASS, ratio=0.45, noise=0.10)
    scale = max(float(np.max(np.abs(X))), 1e-9)
    X = X / scale * 1.15 * float(sat)  # 归一到参考页的 ±1.15 视野，再按输入幅度拉伸
    return X, y.astype(float)


# ---------------------------------------------------------------- 训练（逐样本在线 SGD）


def _epoch(W, bh, v, bo, X, t, order, H, kind, lr):
    """一轮逐样本在线 SGD：每个样本 前向 → 反向 → 立刻更新（参考页 pgStep 的口径）。"""
    tot = 0.0
    for i in order:
        x, ti = X[i], t[i]
        z = W @ x + bh
        a = _act(z, kind)
        o = float(util.sigmoid(float(a @ v + bo)))
        tot += (o - ti) ** 2
        d3 = 2.0 * (o - ti) * o * (1.0 - o)  # ∂L/∂z（输出层）
        dh = d3 * v * _act_deriv(z, a, kind)  # ∂L/∂zⱼ（隐藏层）
        v -= lr * d3 * a
        bo -= lr * d3
        W -= lr * np.outer(dh, x)
        bh -= lr * dh
    return tot, (W, bh, v, bo)


def train_numpy(X, t, H, kind, lr, epochs, seed) -> dict[str, Any]:
    W, bh, v, bo = unpack(init_theta(H, seed), H)
    W, bh, v = W.copy(), bh.copy(), v.copy()
    g = util.rng(seed, 7)
    rec: list[dict[str, Any]] = []
    theta = pack(W, bh, v, bo, H)
    for ep in range(int(epochs)):
        order = g.permutation(len(t))
        tot, (W, bh, v, bo) = _epoch(W, bh, v, bo, X, t, order, H, kind, lr)
        theta = pack(W, bh, v, bo, H)
        if not np.all(np.isfinite(theta)):
            rec.append({"epoch": ep, "loss": float("nan"), "gradnorm": float("nan"),
                        "acc": 0.0, "theta": theta.copy()})
            return {"theta": theta, "rec": rec, "diverged": True}
        _, gr = mean_grad(theta, X, t, H, kind)
        o = forward(theta, X, H, kind)["o"]
        rec.append({"epoch": ep, "loss": tot / len(t), "gradnorm": float(np.linalg.norm(gr)),
                    "acc": float(np.mean((o > 0.5).astype(float) == t)), "theta": theta.copy()})
    return {"theta": theta, "rec": rec, "diverged": False}


def train_torch(X, t, H, kind, lr, epochs, seed) -> dict[str, Any]:
    """autograd 版本：初值、样本顺序、更新式与 NumPy 版逐一对齐。"""
    import torch  # 仅在探测到可用时导入

    W0, bh0, v0, bo0 = unpack(init_theta(H, seed), H)
    W = torch.tensor(W0, dtype=torch.float64, requires_grad=True)
    bh = torch.tensor(bh0, dtype=torch.float64, requires_grad=True)
    v = torch.tensor(v0, dtype=torch.float64, requires_grad=True)
    bo = torch.tensor(bo0, dtype=torch.float64, requires_grad=True)
    ps = [W, bh, v, bo]
    Xt = torch.tensor(X, dtype=torch.float64)
    tt = torch.tensor(t, dtype=torch.float64)

    def act(z):
        if kind == 0:
            return torch.sigmoid(z)
        if kind == 1:
            return torch.tanh(z)
        return torch.relu(z)

    g = util.rng(seed, 7)
    rec: list[dict[str, Any]] = []
    for ep in range(int(epochs)):
        idx = g.permutation(len(t))
        tot = 0.0
        for i in idx:
            x, ti = Xt[int(i)], tt[int(i)]
            o = torch.sigmoid(act(W @ x + bh) @ v + bo)
            loss = (o - ti) ** 2
            grads = torch.autograd.grad(loss, ps)
            tot += float(loss.detach())
            with torch.no_grad():
                for p, gr in zip(ps, grads, strict=True):
                    p -= lr * gr
        with torch.no_grad():
            oo = torch.sigmoid(act(Xt @ W.T + bh) @ v + bo)
            bl = float(torch.mean((oo - tt) ** 2))
            ac = float(torch.mean((oo > 0.5).to(tt.dtype) == tt))
        rec.append({"epoch": ep, "loss": tot / len(t), "batchLoss": bl, "acc": ac})
    theta = pack(W.detach().numpy(), bh.detach().numpy(), v.detach().numpy(), float(bo.detach()), H)
    return {"theta": theta, "rec": rec, "diverged": False}


# ---------------------------------------------------------------- 入口


def run(params: dict[str, Any], seed: int, steps: int) -> dict[str, Any]:
    H = max(1, int(params["hidden"]))
    lr = float(params["lr"])
    kind = int(params["act"])
    data_kind = int(params["data"])
    sat = float(params["sat"])
    epochs = max(2, min(int(steps), 400))

    X, t = data_for(data_kind, seed, sat)
    res = train_numpy(X, t, H, kind, lr, epochs, seed)
    theta, rec = res["theta"], [r for r in res["rec"] if np.isfinite(r["loss"])]
    T = len(rec)
    backend = "numpy"
    tres = None
    if torch_state().get("available"):
        try:
            tres = train_torch(X, t, H, kind, lr, epochs, seed)
            backend = "torch"
        except Exception:
            tres = None

    loss_final = rec[-1]["loss"] if T else float("nan")
    acc = rec[-1]["acc"] if T else 0.0
    gnorm = rec[-1]["gradnorm"] if T else 0.0
    act_name = ["Sigmoid", "tanh", "ReLU"][kind]
    data_name = ["两团 blobs", "异或 XOR", "同心圆"][data_kind]

    # ---- 权重空间切片 (v₁, bₒ)，其余参数冻在训练结束值
    W, bh, v, bo = unpack(theta, H)

    # 切片的解析式：o = σ(a₁·v₁ + (其余项)) —— 与 mean_grad 在冻结参数下的梯度完全一致
    f0 = forward(theta, X, H, kind)
    a1 = f0["A"][:, 0]
    rest = (f0["A"][:, 1:] @ v[1:] + bo) if H > 1 else np.full(len(X), bo)
    m = len(t)

    def slice_at(v1: float, bo_: float) -> tuple[float, tuple[float, float]]:
        o = util.sigmoid(a1 * v1 + rest + bo_)
        dzo = 2.0 * (o - t) * o * (1.0 - o) / m
        return float(np.mean((o - t) ** 2)), (float(np.dot(dzo, a1)), float(dzo.sum()))

    def slice_row(v1: float) -> np.ndarray:
        o = util.sigmoid(a1[:, None] * v1 + rest[:, None] + bg[None, :])
        return np.mean((o - t[:, None]) ** 2, axis=0)

    traj = np.array([[float(r["theta"][3 * H]), float(r["theta"][4 * H])] for r in rec]) \
        if T else np.array([[v[0], bo]])
    v_mid, b_mid = float(np.mean(traj[:, 0])), float(np.mean(traj[:, 1]))
    pad_v = max(float(np.ptp(traj[:, 0])) * 0.6, abs(v_mid) * 0.6, 0.8)
    pad_b = max(float(np.ptp(traj[:, 1])) * 0.6, abs(b_mid) * 0.6, 0.8)
    vg = np.linspace(v_mid - pad_v, v_mid + pad_v, util.GRID)
    bg = np.linspace(b_mid - pad_b, b_mid + pad_b, util.GRID)
    Zs = np.column_stack([slice_row(float(vv)) for vv in vg])
    iopt, jopt = np.unravel_index(int(np.argmin(Zs)), Zs.shape)
    path = [util.trace(v1, b_o, slice_at(v1, b_o)[0], int(r["epoch"]),
                       slice_at(v1, b_o)[1])
            for r, (v1, b_o) in zip(rec, traj, strict=False)]

    # ---- 网络结构图（2→H→1，节点带真实数值，边上带权重）
    f_all = forward(theta, X, H, kind)
    ys = [1.0 - 2.0 * j / max(H - 1, 1) for j in range(H)] if H > 1 else [0.0]
    nodes = [util.node(0, 0.0, 0.55, "x₁", [f"均值 {float(X[:, 0].mean()):.3f}"], False),
             util.node(1, 0.0, -0.55, "x₂", [f"均值 {float(X[:, 1].mean()):.3f}"], False)]
    edges: list[dict[str, Any]] = []
    for j in range(H):
        nid = 2 + j
        nodes.append(util.node(nid, 1.0, ys[j], f"h{j + 1}={act_name[0:1]}(z{j + 1})",
                               [f"a̅={float(f_all['A'][:, j].mean()):+.3f}",
                                f"b{j + 1}={bh[j]:+.3f}",
                                f"‖w·‖={float(np.linalg.norm(W[j])):.3f}"], False))
        for i in range(2):
            edges.append(util.edge(i, nid, f"w{i + 1}{j + 1}={W[j, i]:+.2f}"))
    out_id = 2 + H
    nodes.append(util.node(out_id, 2.0, 0.0, "o = σ(z)",
                           [f"o̅={float(f_all['o'].mean()):+.3f}", f"bₒ={bo:+.3f}",
                            f"激活={act_name}"], True))
    for j in range(H):
        edges.append(util.edge(2 + j, out_id, f"v{j + 1}={v[j]:+.2f}"))

    # ---- 输出曲面（网络学到的那个函数本身）
    lim = 1.6 * sat
    gx = np.linspace(-lim, lim, 41)
    gy = np.linspace(-lim, lim, 41)
    G1, G2 = np.meshgrid(gx, gy, indexing="xy")
    Pgrid = forward(theta, np.column_stack([G1.ravel(), G2.ravel()]), H, kind)["o"].reshape(G1.shape)
    # 散点贴地，曲面高度 = 网络输出 o；否则 100 个点全被曲面埋住
    pts = [util.point3(X[i, 0], X[i, 1], 0.0, int(t[i]), 1.1) for i in range(len(t))]
    logit3d = util.cloud(pts, legend=[{"label": "类别 0", "color": util.color_of(0)},
                                      {"label": "类别 1", "color": util.color_of(1)}],
                         bound=util.boundary(gx, gy, Pgrid, "x₁", "x₂", "输出 o = σ(z)", level=0.5))

    ep = [r["epoch"] for r in rec]
    curves = [util.curve("loss", "训练 loss (o−y)²", ep, [r["loss"] for r in rec], color="#2563eb"),
              util.curve("acc", "准确率 (o>0.5)", ep, [r["acc"] for r in rec], color="#0d9488"),
              util.curve("gradnorm", "‖∇L‖（批量）", ep,
                         [min(r["gradnorm"], 5.0) for r in rec], dash=True, color="#7c3aed")]
    torch_diff = None
    if tres and len(tres["rec"]) == T:
        curves.append(util.curve("torch", "autograd 同网络 loss", ep,
                                 [r["loss"] for r in tres["rec"]], dash=True, color="#dc2626"))
        torch_diff = float(max(abs(a["loss"] - b["loss"]) for a, b in
                               zip(rec, tres["rec"], strict=False)))

    rows = [
        {"name": "结构", "value": f"2→{H}→1", "note": f"隐藏激活 {act_name}，输出 Sigmoid"},
        {"name": "参数量", "value": f"{n_params(H)}", "note": f"W 2·{H} + bₕ {H} + v {H} + bₒ 1"},
        {"name": f"{data_name} · 样本 {len(t)}", "value": f"loss={loss_final:.6f}",
         "truth": f"acc={acc:.4f}", "note": f"逐样本 SGD，η={lr}，{epochs} 轮"},
    ]
    if torch_diff is not None:
        rows.append({"name": "torch/NumPy loss 最大偏差", "value": f"{torch_diff:.2e}",
                     "note": "autograd 与手写反向传播必须一致（阈值 1e-5）"})
    else:
        rows.append({"name": "torch/NumPy loss 最大偏差", "value": "0.00e+00",
                     "note": "未安装 PyTorch（uv sync --extra ml 后可对照 autograd），当前为纯 NumPy 内核"})

    lag = next((int(r["epoch"]) for r in rec if r["loss"] < 0.1 * rec[0]["loss"]), epochs) if T else 0
    climax = (
        f"loss 从 {rec[0]['loss']:.3f} 出发，撑到第 {lag} 轮才降到 1/10 以下——这段「平台期」正是"
        f"Sigmoid 输出配平方损失的代价：o≈0.5 时 ∂L/∂z = 2(o−y)·o(1−o) 被 o(1−o) 压住，"
        f"输入幅度 ×{sat:g} 又把 {act_name} 推向饱和（φ′→0），当前批量 ‖∇L‖={gnorm:.2e}。"
        "另外切片曲面崎岖不是因为局部极小多，而是隐藏神经元可交换：任意排列组合都是同一个解。"
    )

    return util.finish(KEY, {
        "backend": backend,
        "metrics": {"loss": loss_final, "acc": acc, "gradnorm": gnorm},
        "series": [
            util.ser("loss", "逐轮平均 loss", ep, [r["loss"] for r in rec], "epoch", "(o−y)²"),
            util.ser("acc", "准确率", ep, [r["acc"] for r in rec], "epoch", "accuracy"),
            util.ser("gradnorm", "批量梯度范数", ep, [r["gradnorm"] for r in rec], "epoch", "‖∇L‖"),
        ],
        "table": [
            util.tab("net", "网络与训练", rows),
            util.tab("coef", "输出层参数", [
                {"name": f"v{j + 1}", "value": f"{v[j]:.4f}",
                 "note": f"来自 h{j + 1}，其偏置 b{j + 1}={bh[j]:.3f}"} for j in range(H)] +
                [{"name": "bₒ", "value": f"{bo:.4f}"}]),
        ],
        "visualMap": {
            "net": util.tree2d(nodes, edges),
            "logit3d": logit3d,
            "slice": util.surface(vg, bg, Zs, "v₁（h₁→o 的权重）", "bₒ（输出偏置）", "批量 MSE 切片",
                                  path=path,
                                  optimum={"x": util.num(vg[jopt]), "y": util.num(bg[iopt]),
                                           "z": util.num(Zs[iopt, jopt]),
                                           "label": "切片内最低点（不一定等于全局最优）"},
                                  markers=[{"x": util.num(v_mid), "y": util.num(b_mid),
                                            "z": util.num(slice_at(v_mid, b_mid)[0]),
                                            "label": "训练结束位置", "color": "#0d9488"}],
                                  climax=climax),
            "curve": util.lines2d(curves, "epoch", "值", yr=(0.0, 1.05)),
        },
    })
