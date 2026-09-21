"""卷积神经网络数值内核：手写 conv2d（stride / padding / kernel / filters）+ ReLU。

输入是 datasets.cnn_pattern 生成的 16×16 程序化图案（当成高度场看，灰度=海拔）；
卷积核全部零均值化 ⇒ 它们是高通滤波器，对「均匀亮度」不响应，只对边缘/纹理响应，
这样特征图上的峰才真的有教学意义（哪里长高 = 哪里匹配这个核）。

尺寸公式：O = ⌊(I − K + 2P)/S⌋ + 1；参数量 = F·(K·K·C_in + 1)；单层感受野 = K。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.ml import datasets, util

KEY = "cnn"
IMG = 16


def make_kernels(F: int, K: int, seed: int) -> np.ndarray:
    """F 个 K×K 核：随机初始化后逐核减均值（零均值=高通，只对边缘响应），再归一化到 ‖W‖F=K。

    K=1 时零均值会把核压成 0，所以退化成「逐像素亮度缩放」，不做中心化。
    """
    g = util.rng(seed, 61)
    W = g.uniform(-1.0, 1.0, (F, K, K))
    if K > 1:
        W = W - W.mean(axis=(1, 2), keepdims=True)
    nrm = np.linalg.norm(W.reshape(F, -1), axis=1)
    return W * (float(K) / np.maximum(nrm, 1e-9))[:, None, None]


def conv2d(img: np.ndarray, W: np.ndarray, stride: int, pad: int) -> np.ndarray:
    """朴素单层卷积：C_in=1。输出 (F, O, O)，O = ⌊(I−K+2P)/S⌋+1。"""
    I = img.shape[0]
    F, K = W.shape[0], W.shape[1]
    S, P = max(int(stride), 1), int(pad)
    O = (I - K + 2 * P) // S + 1
    if O <= 0:
        return np.zeros((F, 0, 0))
    if P > 0:
        src = np.pad(img, P, mode="constant")
    else:
        src = img
    out = np.zeros((F, O, O))
    for f in range(F):
        for i in range(O):
            r0 = i * S
            for j in range(O):
                c0 = j * S
                out[f, i, j] = float(np.sum(src[r0:r0 + K, c0:c0 + K] * W[f]))
    return out


def relu(a: np.ndarray) -> np.ndarray:
    return np.maximum(0.0, a)


def maxpool2d(a: np.ndarray, size: int = 2, stride: int = 2) -> np.ndarray:
    H, Wd = a.shape
    oh, ow = (H - size) // stride + 1, (Wd - size) // stride + 1
    out = np.empty((oh, ow))
    for i in range(oh):
        for j in range(ow):
            out[i, j] = a[i * stride:i * stride + size, j * stride:j * stride + size].max()
    return out


def run(params: dict[str, Any], seed: int, steps: int) -> dict[str, Any]:
    K = max(1, int(params["kernel"]))
    S = max(1, int(params["stride"]))
    P = max(0, int(params["pad"]))
    F = max(1, int(params["filters"]))
    pattern = int(params["pattern"])

    img = datasets.cnn_pattern(pattern, IMG)
    Wk = make_kernels(F, K, seed)
    pre = conv2d(img, Wk, S, P)
    post = relu(pre)
    O = max(0, int(pre.shape[2]))
    n_params = int(F * (K * K * 1 + 1))
    rf = K  # 单层感受野 = 核尺寸
    pool_out = (O - 2) // 2 + 1 if O >= 2 else 0

    # 同一个 (K,S,P) 叠 4 层的塔：尺寸 / 感受野 / 参数量
    sizes, rfs, pcount = [], [], []
    side, jump, rf_acc, tot_p = IMG, 1, 1, 0
    for d in range(4):
        side = max((side - K + 2 * P) // S + 1, 0)
        rf_acc += (K - 1) * jump
        jump *= S
        tot_p += F * (K * K * (1 if d == 0 else F) + 1)
        sizes.append(float(side))
        rfs.append(float(rf_acc))
        pcount.append(float(F * (K * K * (1 if d == 0 else F) + 1)))
    fc_params = float((sizes[-1] ** 2) * F * 10) if sizes[-1] > 0 else 0.0

    idx = np.arange(len(sizes)) + 1
    size_line = util.lines2d(
        [util.curve("size", "输出边长 O（逐层）", idx, sizes, color="#2563eb"),
         util.curve("rf", "累计感受野 RF（逐层）", idx, rfs, color="#ea580c")],
        "层序号", "像素：边长 / 感受野", xr=(1, 4))

    bars_params = util.bars([f"conv{d + 1}" for d in range(4)] + ["若展平接 FC→10 类"],
                            pcount + [fc_params], ylab="参数量", xlab="层")

    win = {"size": K, "stride": S, "x": 0, "y": 0, "label": f"{K}×{K} 卷积核（步长 {S}，填充 {P}）"}
    input_surf = util.surface(np.arange(IMG), np.arange(IMG), img,
                              "列 j", "行 i", "灰度（高度）",
                              levels=[0.25, 0.5, 0.75],
                              window=win,
                              climax=f"输入 {IMG}×{IMG}，共 {IMG * IMG} 个数；"
                                     f"卷积核只有 {K * K} 个权重，被平移到每个位置——这就是权值共享。")
    peak = np.unravel_index(int(np.argmax(post[0])), post[0].shape) if O > 0 else (0, 0)
    map_surf = util.surface(np.arange(max(O, 1)), np.arange(max(O, 1)),
                            post[0] if O > 0 else np.zeros((1, 1)),
                            "输出列", "输出行", "filter 1 激活（ReLU 后）",
                            markers=[{"x": float(peak[1]), "y": float(peak[0]),
                                      "z": util.num(post[0].max()) if O > 0 else 0.0,
                                      "label": f"最强响应 ({peak[1]},{peak[0]})",
                                      "color": "#dc2626"}],
                            window=win,
                            climax=f"O = (I − K + 2P)/S + 1 = ({IMG} − {K} + 2·{P})/{S} + 1 = {O}，"
                                   f"所以特征图是 {O}×{O}。"
                                   + ("窗口滑不到第二个位置（O≤1）：核太大或步长太猛，信息被裁掉了。"
                                      if O < 2 else ""))

    flat = [pre[f, :, :].ravel() for f in range(min(F, 2))]

    means = [float(post[f].mean()) for f in range(F)]
    maxima = [float(post[f].max()) if post[f].size else 0.0 for f in range(F)]
    fired = [float(np.mean(pre[f] > 0)) for f in range(F)]

    return util.finish(KEY, {
        "backend": "numpy",
        "metrics": {"params": n_params, "out": float(O), "rf": float(rf)},
        "series": [util.ser("scan", "filter 1 的滑动响应 z", range(len(flat[0])), flat[0],
                            "窗口序号", "z")],
        "table": [
            util.tab("shape", "尺寸与公式", [
                {"name": "输出边长 O", "value": f"{O}",
                 "truth": f"({IMG} − {K} + 2·{P})/{S} + 1",
                 "note": "整除取 floor；O≤0 表示这一层什么都剩不下"},
                {"name": "参数量", "value": f"{n_params}",
                 "truth": f"{F}×({K}²×1+1)", "note": "每个核 K² 个权重 + 1 个偏置（这里偏置含在零均值化里）"},
                {"name": "单层感受野", "value": f"{rf}",
                 "note": f"叠 4 层同样配置后可看到 {rfs[-1]:.0f}×{rfs[-1]:.0f}"},
                {"name": "再接 2×2 max-pool", "value": f"{pool_out}",
                 "note": f"⌊({O} − 2)/2⌋ + 1"},
            ]),
            util.tab("filters", "每个 filter 的统计", [
                {"name": f"filter {f + 1}", "value": f"均值 {means[f]:.3f}",
                 "truth": f"峰值 {maxima[f]:.3f}", "delta": f"激活率 {fired[f]:.2f}",
                 "note": "ReLU 后为 0 的位置=该核在这个窗口没找到匹配的边缘"}
                for f in range(F)]),
        ],
        "visualMap": {
            "input": input_surf,
            "map": map_surf,
            "size": size_line,
            "params": bars_params,
        },
    })
