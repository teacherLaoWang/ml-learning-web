"""算法数值内核的正确性测试。

覆盖：
1) 每个 ready key 跑通、visuals 的 id/kind 与 VISUAL_SPEC 完全一致、所有数字有限且原生；
2) 解析梯度 vs 数值差分（linreg / logreg / mlp）；
3) 闭式解 vs 梯度下降终点、K-Means 单调性、PCA 方差守恒与重构误差单调性；
4) 同 seed 可复现。
"""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pytest

from app.content import catalog
from app.ml import datasets, kmeans, linreg, logreg, mlp, registry, util

STEP = 150


def default_params(key: str) -> dict[str, Any]:
    return registry.coerce_params(key, {})


# ---------------------------------------------------------------- 1. 契约合规


def test_ready_keys_cover_catalog():
    assert catalog.READY_KEYS == sorted(
        ["linreg", "logreg", "knn", "kmeans", "pca", "tree", "svm", "mlp", "cnn", "tsne"])


def walk_numbers(obj: Any, path: str = "$") -> list[float]:
    """递归收集所有数字（顺便验证没有非原生类型混进来）。"""
    out: list[float] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert isinstance(k, str), f"{path}: 键必须是 str"
            out += walk_numbers(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += walk_numbers(v, f"{path}[{i}]")
    elif isinstance(obj, bool) or obj is None or isinstance(obj, str):
        pass
    elif isinstance(obj, (int, float)):
        assert type(obj) in (int, float), f"{path}: 非原生数字类型 {type(obj)}"
        out.append(float(obj))
    else:
        raise AssertionError(f"{path}: 非法类型 {type(obj).__name__}，JSON 里不该出现")
    return out


@pytest.mark.parametrize("key", catalog.READY_KEYS)
def test_run_contract(key: str):
    out = registry.run(key, default_params(key), 7, STEP)
    assert out["key"] == key
    assert out["backend"] in ("numpy", "torch")
    assert out["missingVisuals"] == []

    spec = catalog.VISUAL_SPEC[key]
    got = [(v["id"], v["kind"]) for v in out["visuals"]]
    assert got == [(s["id"], s["kind"]) for s in spec], "visuals 的顺序/身份必须与 VISUAL_SPEC 一致"
    for v in out["visuals"]:
        assert v["title"] and isinstance(v["data"], dict)

    # 指标 id 必须用 METRIC_SPEC 里的那些
    assert set(out["metrics"]) == {m["id"] for m in catalog.METRIC_SPEC[key]}
    for val in out["metrics"].values():
        assert val is None or (isinstance(val, float) and math.isfinite(val))

    # series 结构
    for s in out["series"]:
        assert {"id", "label", "x", "y", "xLabel", "yLabel"} <= set(s)
        assert len(s["x"]) == len(s["y"]) > 0

    # 全量数字体检（NaN/Inf/非原生）
    numbers = walk_numbers({"metrics": out["metrics"], "series": out["series"],
                            "table": out["table"], "visuals": out["visuals"]})
    assert numbers, "产物里应该有数字"
    for x in numbers:
        assert math.isfinite(x), "输出里出现非有限值"
    assert util.finite_problems(out) == []
    json.dumps(out, ensure_ascii=False)  # 必须可序列化


@pytest.mark.parametrize("key", catalog.READY_KEYS)
def test_surface_and_cloud_grids(key: str):
    """surface3d/cloud3d.boundary 的 grid.z 形状必须是 [len(y)][len(x)]，分辨率 41~80。

    例外：cnn 的两张 surface3d 画的是像素网格本身（16×16 输入 / O×O 特征图），
    高度场必须与像素一一对应，插值到 41×41 反而会骗人。
    """
    out = registry.run(key, default_params(key), 7, 60)
    for v in out["visuals"]:
        grids = []
        if v["kind"] == "surface3d":
            grids.append(v["data"]["grid"])
        if isinstance(v["data"].get("boundary"), dict):
            grids.append(v["data"]["boundary"]["grid"])
        for g in grids:
            nx, ny = len(g["x"]), len(g["y"])
            assert len(g["z"]) == ny, f"{v['id']}: z 的行数应为 len(y)={ny}"
            assert all(len(row) == nx for row in g["z"]), f"{v['id']}: z 的列数应为 len(x)={nx}"
            if v["kind"] == "surface3d" and key != "cnn":
                assert 41 <= nx <= 80 and 41 <= ny <= 80, f"{v['id']}: 网格 {nx}x{ny} 超出 41~80"
        if v["kind"] == "surface3d":
            for p in v["data"].get("path", []):
                assert {"x", "y", "z", "step", "grad"} <= set(p), "轨迹点必须带 step 与 grad"
                assert len(p["grad"]) == 2 and all(math.isfinite(gg) for gg in p["grad"])
            ax = v["data"]["axes"]
            for d in "xyz":
                assert ax[d]["min"] <= ax[d]["max"]
        if v["kind"] == "cloud3d":
            for p in v["data"]["points"]:
                assert {"x", "y", "z"} <= set(p)
        if v["kind"] == "vector3d":
            for a in v["data"]["arrows"]:
                assert len(a["from"]) == 3 and len(a["to"]) == 3
        if v["kind"] == "tree2d":
            ids = {n["id"] for n in v["data"]["nodes"]}
            assert all(e["from"] in ids and e["to"] in ids for e in v["data"]["edges"])
            assert all({"id", "x", "y", "title", "lines", "leaf"} <= set(n) for n in v["data"]["nodes"])
        if v["kind"] == "bars":
            assert len(v["data"]["labels"]) == len(v["data"]["values"])
        if v["kind"] == "matrix":
            n = len(v["data"]["labels"])
            assert len(v["data"]["rows"]) == n and all(len(r) == n for r in v["data"]["rows"])


@pytest.mark.parametrize("key", catalog.READY_KEYS)
def test_reproducible(key: str):
    a = registry.run(key, default_params(key), 11, 40)
    b = registry.run(key, default_params(key), 11, 40)
    def keep(o):
        return json.dumps({k: o[k] for k in ("metrics", "series", "table", "visuals")},
                              ensure_ascii=False, sort_keys=True)
    assert keep(a) == keep(b), "同 seed 必须完全可复现"


@pytest.mark.parametrize("key", catalog.READY_KEYS)
def test_extreme_params_stay_finite(key: str):
    """极端参数（会发散的 lr、K>n、γ 很大…）也必须给出能看的结果，而不是抛异常。"""
    for raw in ({"lr": 99, "noise": 9, "sep": 0.01}, {"n": 60, "k": 41, "p": 4, "weighted": 1}):
        params = registry.coerce_params(key, raw)
        out = registry.run(key, params, 3, 40)
        assert out["missingVisuals"] == []
        assert util.finite_problems({"visuals": out["visuals"], "metrics": out["metrics"]}) == []


def test_datasets_reproducible_and_seeded():
    X1, y1 = datasets.moons(5, n=120)
    X2, y2 = datasets.moons(5, n=120)
    X3, _ = datasets.moons(6, n=120)
    assert np.array_equal(X1, X2) and np.array_equal(y1, y2)
    assert not np.array_equal(X1, X3)
    for fn, kw in ((datasets.blobs, {"n": 80}), (datasets.circles, {"n": 80}), (datasets.xor, {"n": 80})):
        A, b = fn(1, **kw)
        assert A.shape == (80, 2) and b.shape == (80,)
        assert np.isfinite(A).all() and set(np.unique(b)) <= {0, 1}
    d = datasets.quad_1d(1, n=40, noise=0.1)
    assert len(d["x"]) == 40 and d["truth"]["w1"] == pytest.approx(1.2)
    X3d, lab = datasets.gaussian_blobs3d(1, n=90, k=3, gap=3.4)
    assert X3d.shape == (90, 3) and len(np.unique(lab)) == 3
    a = datasets.anisotropic3d(1, n=200, sx=4.0, sy=1.4, tilt=32)
    assert a["X"].shape == (200, 3)
    assert datasets.cnn_pattern(1).shape == (16, 16)
    assert datasets.cnn_pattern(1).min() >= 0 and datasets.cnn_pattern(1).max() <= 1.0 + 1e-9


# ---------------------------------------------------------------- 2. 梯度正确性


def test_linreg_analytic_grad_matches_finite_difference():
    F, _ = linreg.features(datasets.quad_1d(3, n=35, noise=0.2)["x"], 3.0)
    y = datasets.quad_1d(3, n=35, noise=0.2)["y"]
    for w in (np.zeros(2), np.array([1.3, -0.7])):
        _, g = linreg.loss_grad(F, y, w)
        num = np.zeros(2)
        for j in range(2):
            e = np.zeros(2)
            e[j] = 1e-6
            num[j] = (linreg.loss_grad(F, y, w + e)[0] - linreg.loss_grad(F, y, w - e)[0]) / 2e-6
        assert np.max(np.abs(g - num)) < 1e-6


def test_logreg_analytic_grad_matches_finite_difference():
    X, y = datasets.blobs(3, n=60, sep=1.2, sigma=1.1)
    F = np.column_stack([X, np.ones(len(y))])
    th = np.array([0.4, -0.3, 0.2])
    for l2 in (0.0, 0.35):
        _, g = logreg.loss_grad(F, y, th, l2)
        num = np.array([(logreg.loss_grad(F, y, th + np.eye(3)[j] * 1e-6, l2)[0]
                          - logreg.loss_grad(F, y, th - np.eye(3)[j] * 1e-6, l2)[0])
                         / 2e-6 for j in range(3)])
        assert np.max(np.abs(g - num)) < 1e-6, f"L2={l2} 时解析梯度与数值差分不一致"


def test_mlp_analytic_grad_matches_finite_difference():
    X, y = datasets.xor(2, n=24)
    H, t = 3, y.astype(float)
    for act in (0, 1, 2):
        th = util.rng(4).normal(0, 0.6, mlp.n_params(H))
        _, g = mlp.mean_grad(th, X, t, H, act)
        num = np.zeros_like(th)
        for j in range(len(th)):
            e = np.zeros_like(th)
            e[j] = 1e-6
            num[j] = (mlp.mean_loss(th + e, X, t, H, act)
                      - mlp.mean_loss(th - e, X, t, H, act)) / 2e-6
        assert np.max(np.abs(g - num)) < 1e-6, f"激活 {act} 时反向传播的梯度不对"


# ---------------------------------------------------------------- 3. 单调性 / 一致性


def test_mlp_sample_grad_matches_finite_difference():
    """逐样本梯度（训练循环内联的就是这套公式）也必须与数值差分一致。"""
    X, y = datasets.circles(5, n=40)
    H, act = 3, 0
    x, ti = X[3], float(y[3])
    th = util.rng(9).normal(0, 0.5, mlp.n_params(H))

    def one_loss(t):
        o = mlp.forward(t, x[None, :], H, act)["o"][0]
        return float((o - ti) ** 2)

    g = mlp.sample_grad(th, x, ti, H, act)
    num = np.array([(one_loss(th + np.eye(len(th))[j] * 1e-6)
                     - one_loss(th - np.eye(len(th))[j] * 1e-6)) / 2e-6 for j in range(len(th))])
    assert np.max(np.abs(g - num)) < 1e-6


def test_mlp_batch_grad_is_mean_of_sample_grads():
    X, y = datasets.xor(6, n=20)
    H, act = 4, 1
    t = y.astype(float)
    th = util.rng(2).normal(0, 0.4, mlp.n_params(H))
    per = np.mean([mlp.sample_grad(th, X[i], t[i], H, act) for i in range(len(t))], axis=0)
    _, g = mlp.mean_grad(th, X, t, H, act)
    assert np.max(np.abs(per - g)) < 1e-9


def test_linreg_gd_endpoint_matches_normal_equation():
    params = default_params("linreg")
    data = datasets.quad_1d(7, n=int(params["n"]), noise=float(params["noise"]))
    F, _ = linreg.features(data["x"], params["spread"])
    y = data["y"]
    w_star = np.linalg.solve(F.T @ F + 1e-10 * np.eye(2), F.T @ y)
    out = registry.run("linreg", params, 7, 400)
    rows = {r["name"]: r for t in out["table"] for r in t["rows"]}
    gd = np.array([float(rows["w₁"]["value"]), float(rows["w₂"]["value"])])
    rel = np.linalg.norm(gd - w_star) / max(np.linalg.norm(w_star), 1e-9)
    assert rel < 0.05, f"梯度下降终点离闭式解太远：相对误差 {rel:.3f}"
    assert out["metrics"]["r2"] > 0.9


def test_kmeans_inertia_monotone_non_increasing():
    out = registry.run("kmeans", default_params("kmeans"), 7, 60)
    series = {s["id"]: s for s in out["series"]}
    inert = np.array(series["inertia"]["y"], dtype=float)
    assert len(inert) >= 3, "至少要能看到初值 + 若干轮迭代"
    assert np.all(np.diff(inert) <= 1e-9), "K-Means 的 inertia 必须逐轮不升"
    assert out["metrics"]["inertia"] <= inert[0] + 1e-9
    # 肘部曲线也必须单调不升（K 越大惯性越小）
    elbow = next(v for v in out["visuals"] if v["id"] == "elbow")["data"]
    assert np.all(np.diff(np.array(elbow["values"], dtype=float)) <= 1e-9)
    # 肘部判据必须指回数据里埋的真簇数（Kneedle 弦距）
    knee = next(r for t in out["table"] for r in t["rows"] if r["name"].startswith("肘部位置"))
    assert knee["value"] == f"K={kmeans.TRUE_K}", f"肘部判据跑偏：{knee['value']}"


def test_pca_variance_conservation_and_monotone_error():
    params = default_params("pca")
    out = registry.run("pca", params, 7, 20)
    rows = {r["id"]: r for r in out["visuals"]}
    evr = np.array(rows["ratio"]["data"]["values"], dtype=float)
    assert evr.size == 3
    assert abs(float(evr.sum()) - 1.0) < 1e-4, "解释方差比之和必须为 1（方差守恒）"
    assert np.all(np.diff(evr) <= 1e-9), "特征值必须降序"
    errs = np.array([float(r["value"]) for r in out["table"][0]["rows"]], dtype=float)
    assert np.all(np.diff(errs) < 0), "重构误差必须随主成分数单调下降"
    assert np.allclose(errs, 1 - np.cumsum(evr), atol=1e-5), "未解释方差比 = 1 − 累计解释比"

    # 与手算的特征分解对照（不依赖 sklearn）
    X = datasets.anisotropic3d(7, n=params.get("n", 240), sx=params["sx"], sy=params["sy"],
                               tilt=params["tilt"])["X"]
    Xc = X - X.mean(axis=0)
    lam = np.linalg.eigvalsh(np.cov(Xc.T))[::-1]
    assert abs(lam.sum() - float(np.var(Xc, axis=0, ddof=1).sum())) < 1e-8  # Σλ == 总方差
    assert np.allclose(np.sort(evr)[::-1], lam / lam.sum(), atol=1e-4)


def test_tree_and_svm_and_knn_sanity():
    out = registry.run("tree", default_params("tree"), 7, 60)
    assert out["metrics"]["acc"] >= 0.7
    graph = next(v for v in out["visuals"] if v["id"] == "graph")["data"]
    leaves = [n for n in graph["nodes"] if n["leaf"]]
    assert len(leaves) >= 2 and len(graph["nodes"]) == 2 * len(leaves) - 1

    out = registry.run("svm", default_params("svm"), 7, 300)
    assert out["metrics"]["sv"] >= 2
    assert out["metrics"]["margin"] > 0
    assert out["metrics"]["acc"] >= 0.7

    out = registry.run("knn", default_params("knn"), 7, 20)
    assert 0.5 < out["metrics"]["acc"] <= 1.0
    assert 0.0 <= out["metrics"]["f1"] <= 1.0


def test_cnn_shapes_and_metrics():
    params = registry.coerce_params("cnn", {"kernel": 3, "stride": 1, "pad": 1, "filters": 4})
    out = registry.run("cnn", params, 7, 10)
    I, K, S, P, Fn = 16, 3, 1, 1, 4
    assert out["metrics"]["out"] == (I - K + 2 * P) // S + 1
    assert out["metrics"]["params"] == Fn * (K * K * 1 + 1)
    assert out["metrics"]["rf"] == K
    for v in out["visuals"]:
        if v["id"] in ("input", "map"):
            assert v["data"]["window"]["size"] == K and v["data"]["window"]["stride"] == S
            g = v["data"]["grid"]
            assert len(g["z"]) == len(g["y"]) and len(g["z"][0]) == len(g["x"])
    # 不同 (K,S,P) 下的输出边长都符合公式
    for k, s, p in ((1, 1, 0), (3, 2, 1), (5, 1, 2), (7, 3, 3)):
        pr = registry.coerce_params("cnn", {"kernel": k, "stride": s, "pad": p})
        o = registry.run("cnn", pr, 7, 10)
        assert o["metrics"]["out"] == (16 - k + 2 * p) // s + 1, (k, s, p)


def test_mlp_torch_agreement_or_numpy():
    params = registry.coerce_params("mlp", {"hidden": 3, "data": 1})
    out = registry.run("mlp", params, 7, 60)
    assert out["metrics"]["gradnorm"] is not None
    if out["backend"] == "torch":
        diff = next(r for tbl in out["table"] for r in tbl["rows"] if r["name"] == "torch/NumPy loss 最大偏差")
        assert float(diff["value"]) < 1e-5, "autograd 与手写反向传播的 loss 必须一致"
    curve = next(v for v in out["visuals"] if v["id"] == "curve")["data"]
    assert len(curve["curves"]) >= 2


def test_tsne_returns_trajectory_and_embedding():
    out = registry.run("tsne", default_params("tsne"), 7, 250)
    embed = next(v for v in out["visuals"] if v["id"] == "embed")["data"]
    assert len(embed["curves"]) >= 2
    n_pts = sum(len(c["x"]) for c in embed["curves"] if c["id"] != "trail")
    assert 140 <= n_pts <= 200, "样本量固定在 140~200，避免 O(n²) 爆内存"
    stress = {s["id"]: s for s in out["series"]}
    kl = np.array(stress["kl"]["y"], dtype=float)
    assert kl[-1] < kl[0], "KL 必须下降"
    assert np.all(kl >= -1e-9)
    perp = next(v for v in out["visuals"] if v["id"] == "perp")["data"]
    assert len(perp["labels"]) >= 3


def test_logreg_prob_surface_is_monotone_in_score():
    out = registry.run("logreg", default_params("logreg"), 7, 120)
    prob = next(v for v in out["visuals"] if v["id"] == "prob3d")["data"]
    Z = np.array(prob["boundary"]["grid"]["z"], dtype=float)
    assert Z.min() >= 0.0 and Z.max() <= 1.0
    assert out["metrics"]["auc"] > 0.7
    roc = next(v for v in out["visuals"] if v["id"] == "roc")["data"]
    curve = roc["curves"][0]
    assert np.all(np.diff(curve["x"]) >= -1e-9) and np.all(np.diff(curve["y"]) >= -1e-9)
    assert abs(out["metrics"]["auc"] - float(np.trapezoid(curve["y"], curve["x"]))) < 0.05
