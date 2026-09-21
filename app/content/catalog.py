"""机器可读的算法目录与参数规格 —— 教学文字在 app/content/lessons/{key}.py，仿真实现在 app/ml/{key}.py。

这里只放「结构」：目录树、每个 ready 算法的参数 id/范围、需要哪些 visual、返回哪些指标。
前端控件、后端校验、ML 实现三方都以本文件为唯一事实来源（见 docs/API-CONTRACT.md）。
"""

from typing import Any

# ---------------------------------------------------------------- 目录（六大类）

FAMILIES: list[dict[str, Any]] = [
    {
        "key": "supervised", "name": "监督学习", "color": "#2563eb",
        "blurb": "给定 (x, y) 学一个映射：标签连续 → 回归，标签离散 → 分类。",
        "items": [
            {"key": "linreg", "name": "线性回归", "status": "ready", "difficulty": 1,
             "tags": ["回归", "最小二乘", "梯度下降", "闭式解"]},
            {"key": "logreg", "name": "逻辑回归", "status": "ready", "difficulty": 1,
             "tags": ["分类", "Sigmoid", "交叉熵", "正则化"]},
            {"key": "knn", "name": "K 近邻", "status": "ready", "difficulty": 1,
             "tags": ["惰性学习", "距离度量", "维度灾难"]},
            {"key": "tree", "name": "决策树", "status": "ready", "difficulty": 2,
             "tags": ["信息增益", "Gini", "剪枝", "可解释"]},
            {"key": "svm", "name": "支持向量机", "status": "ready", "difficulty": 3,
             "tags": ["最大间隔", "核技巧", "软间隔", "对偶"]},
            {"key": "naivebayes", "name": "朴素贝叶斯", "status": "outline", "difficulty": 2,
             "tags": ["贝叶斯定理", "条件独立", "文本分类"]},
            {"key": "ridge", "name": "岭回归与 Lasso", "status": "outline", "difficulty": 2,
             "tags": ["L2", "L1", "稀疏解", "偏差方差"]},
            {"key": "isotonic", "name": "保序回归与校准", "status": "outline", "difficulty": 3,
             "tags": ["概率校准", "Platt", "单调"]},
        ],
    },
    {
        "key": "unsupervised", "name": "无监督学习", "color": "#7c3aed",
        "blurb": "没有标签，找结构：聚类、密度、低维流形。",
        "items": [
            {"key": "kmeans", "name": "K-Means 聚类", "status": "ready", "difficulty": 1,
             "tags": ["EM 思想", "肘部法则", "K-Means++"]},
            {"key": "pca", "name": "主成分分析", "status": "ready", "difficulty": 2,
             "tags": ["特征分解", "方差最大化", "降维"]},
            {"key": "tsne", "name": "t-SNE 流形可视化", "status": "ready", "difficulty": 4,
             "tags": ["概率嵌入", "困惑度", "KL 散度"]},
            {"key": "gmm", "name": "高斯混合模型", "status": "outline", "difficulty": 3,
             "tags": ["EM", "软聚类", "协方差"]},
            {"key": "dbscan", "name": "DBSCAN 密度聚类", "status": "outline", "difficulty": 2,
             "tags": ["ε 邻域", "噪声点", "任意形状"]},
            {"key": "hierarchical", "name": "层次聚类", "status": "outline", "difficulty": 2,
             "tags": ["树状图", "单链/全链", "Ward"]},
            {"key": "umap", "name": "UMAP", "status": "outline", "difficulty": 4,
             "tags": ["流形假设", "模糊单纯复形", "保持全局"]},
            {"key": "fa", "name": "因子分析与 LDA", "status": "outline", "difficulty": 4,
             "tags": ["潜变量", "主题模型", "共轭"]},
        ],
    },
    {
        "key": "ensemble", "name": "集成学习", "color": "#0d9488",
        "blurb": "一群弱学习器：并行降方差（Bagging），串行降偏差（Boosting）。",
        "items": [
            {"key": "bagging", "name": "Bagging 与随机森林", "status": "outline", "difficulty": 2,
             "tags": ["自助采样", "特征随机", "方差"]},
            {"key": "gbdt", "name": "梯度提升 GBDT", "status": "outline", "difficulty": 3,
             "tags": ["函数空间梯度", "残差拟合", "学习率"]},
            {"key": "xgboost", "name": "XGBoost / LightGBM", "status": "outline", "difficulty": 4,
             "tags": ["二阶近似", "正则树", "工程优化"]},
            {"key": "stacking", "name": "Stacking 与 Blending", "status": "outline", "difficulty": 3,
             "tags": ["元学习器", "泄漏", "折外预测"]},
            {"key": "voting", "name": "投票与加权平均", "status": "outline", "difficulty": 1,
             "tags": ["硬投票", "软投票", "多样性"]},
        ],
    },
    {
        "key": "deep", "name": "深度学习", "color": "#ea580c",
        "blurb": "可微分编程：多层非线性 + 反向传播 + 大规模优化。",
        "items": [
            {"key": "mlp", "name": "多层感知机与反向传播", "status": "ready", "difficulty": 3,
             "tags": ["链式法则", "梯度下降", "激活函数", "MSE"]},
            {"key": "cnn", "name": "卷积神经网络", "status": "ready", "difficulty": 4,
             "tags": ["局部感受野", "权值共享", "池化", "特征图"]},
            {"key": "optim", "name": "优化器：动量 / Adam / 学习率", "status": "outline", "difficulty": 3,
             "tags": ["SGD", "Momentum", "AdamW", "Warmup"]},
            {"key": "normalization", "name": "BatchNorm 与 LayerNorm", "status": "outline", "difficulty": 3,
             "tags": ["内部协变量", "归一化", "残差"]},
            {"key": "rnn", "name": "RNN / LSTM / GRU", "status": "outline", "difficulty": 4,
             "tags": ["时序依赖", "梯度消失", "门控"]},
            {"key": "transformer", "name": "Transformer 与注意力", "status": "outline", "difficulty": 5,
             "tags": ["QKV", "多头", "位置编码", "自回归"]},
            {"key": "autoencoder", "name": "自编码器", "status": "outline", "difficulty": 3,
             "tags": ["瓶颈层", "重构损失", "生成"]},
            {"key": "gan", "name": "生成对抗网络", "status": "outline", "difficulty": 5,
             "tags": ["极小极大", "模式崩溃", "判别器"]},
            {"key": "diffusion", "name": "扩散模型", "status": "outline", "difficulty": 5,
             "tags": ["加噪/去噪", "Score", "DDPM"]},
        ],
    },
    {
        "key": "evaluation", "name": "评估与调参", "color": "#db2777",
        "blurb": "模型好不好，取决于你问问题的方式：划分、指标、显著性。",
        "items": [
            {"key": "biasvariance", "name": "偏差-方差与过拟合", "status": "outline", "difficulty": 2,
             "tags": ["学习曲线", "容量", "正则"]},
            {"key": "metrics", "name": "分类指标：AUC / F1 / 混淆矩阵", "status": "outline", "difficulty": 2,
             "tags": ["精确率", "召回率", "ROC", "PR 曲线"]},
            {"key": "cv", "name": "交叉验证与数据划分", "status": "outline", "difficulty": 2,
             "tags": ["K 折", "分层", "泄漏"]},
            {"key": "hpo", "name": "超参数搜索", "status": "outline", "difficulty": 2,
             "tags": ["网格", "随机", "贝叶斯优化"]},
            {"key": "explain", "name": "可解释性 SHAP / LIME", "status": "outline", "difficulty": 4,
             "tags": ["特征归因", "局部代理", "置换重要性"]},
        ],
    },
    {
        "key": "data", "name": "特征工程与进阶范式", "color": "#4f46e5",
        "blurb": "数据决定上限，模型只是逼近它；以及换一种目标函数的 RL。",
        "items": [
            {"key": "scaling", "name": "标准化与编码", "status": "outline", "difficulty": 1,
             "tags": ["Z-score", "MinMax", "One-Hot", "分位数"]},
            {"key": "missing", "name": "缺失值与异常值", "status": "outline", "difficulty": 1,
             "tags": ["MCAR/MNAR", "插补", "稳健缩放"]},
            {"key": "featuresel", "name": "特征选择", "status": "outline", "difficulty": 2,
             "tags": ["过滤法", "包裹法", "互信息"]},
            {"key": "imbalanced", "name": "类别不平衡", "status": "outline", "difficulty": 2,
             "tags": ["重采样", "类别权重", "Focal Loss"]},
            {"key": "rl", "name": "强化学习入门", "status": "outline", "difficulty": 4,
             "tags": ["MDP", "价值函数", "策略梯度", "探索利用"]},
            {"key": "causal", "name": "因果推断基础", "status": "outline", "difficulty": 5,
             "tags": ["混杂", "干预", "双重稳健"]},
        ],
    },
]

# ------------------------------------------------------- ready 算法的交互参数规格

PARAM_SPECS: dict[str, list[dict[str, Any]]] = {
    "linreg": [
        {"id": "lr", "label": "学习率 η", "min": 0.01, "max": 0.9, "step": 0.01, "default": 0.12,
         "hint": "太大 → 沿梯度方向冲过头，轨迹在谷底两侧震荡"},
        {"id": "spread", "label": "特征尺度比", "min": 1, "max": 12, "step": 1, "default": 4,
         "hint": "两维特征尺度差得越多，损失碗越扁，梯度下降越走「之」字"},
        {"id": "n", "label": "样本数", "min": 12, "max": 240, "step": 1, "default": 60},
        {"id": "noise", "label": "噪声 σ", "min": 0, "max": 1.2, "step": 0.05, "default": 0.25},
    ],
    "logreg": [
        {"id": "lr", "label": "学习率 η", "min": 0.02, "max": 3.0, "step": 0.02, "default": 0.5},
        {"id": "l2", "label": "L2 强度 λ", "min": 0.0, "max": 1.0, "step": 0.01, "default": 0.0},
        {"id": "sep", "label": "类别重叠度", "min": 0.4, "max": 3.0, "step": 0.1, "default": 1.2},
        {"id": "n", "label": "样本数", "min": 40, "max": 400, "step": 20, "default": 160},
    ],
    "knn": [
        {"id": "k", "label": "邻居数 K", "min": 1, "max": 41, "step": 2, "default": 5,
         "hint": "K=1 记住噪声（高方差）；K 太大把边界抹平（高偏差）"},
        {"id": "p", "label": "距离阶数 p", "min": 1, "max": 4, "step": 1, "default": 2},
        {"id": "weighted", "label": "距离加权", "min": 0, "max": 1, "step": 1, "default": 0},
        {"id": "n", "label": "样本数", "min": 60, "max": 400, "step": 20, "default": 180},
    ],
    "kmeans": [
        {"id": "k", "label": "簇数 K", "min": 2, "max": 8, "step": 1, "default": 3},
        {"id": "init", "label": "初始化", "min": 0, "max": 1, "step": 1, "default": 1,
         "options": [{"value": 0, "label": "随机取点"}, {"value": 1, "label": "K-Means++"}]},
        {"id": "gap", "label": "簇间距", "min": 1.0, "max": 7.0, "step": 0.2, "default": 3.4},
        {"id": "n", "label": "样本数", "min": 60, "max": 400, "step": 20, "default": 210},
    ],
    "pca": [
        {"id": "sx", "label": "第一主方向方差", "min": 0.5, "max": 6.0, "step": 0.1, "default": 4.0},
        {"id": "sy", "label": "第二主方向方差", "min": 0.3, "max": 4.0, "step": 0.1, "default": 1.4},
        {"id": "tilt", "label": "倾斜角 θ", "min": 0, "max": 90, "step": 1, "default": 32},
        {"id": "whiten", "label": "白化", "min": 0, "max": 1, "step": 1, "default": 0},
    ],
    "tree": [
        {"id": "depth", "label": "最大深度", "min": 1, "max": 10, "step": 1, "default": 3},
        {"id": "leaf", "label": "叶最少样本", "min": 1, "max": 40, "step": 1, "default": 6},
        {"id": "crit", "label": "分裂准则", "min": 0, "max": 1, "step": 1, "default": 0,
         "options": [{"value": 0, "label": "Gini"}, {"value": 1, "label": "信息熵"}]},
        {"id": "n", "label": "样本数", "min": 60, "max": 400, "step": 20, "default": 200},
    ],
    "svm": [
        {"id": "C", "label": "惩罚系数 C", "min": 0.02, "max": 60, "step": 0.02, "default": 1.0,
         "hint": "C 越大越不容忍错分 → 间隔变窄、方差升高"},
        {"id": "kernel", "label": "核函数", "min": 0, "max": 1, "step": 1, "default": 1,
         "options": [{"value": 0, "label": "线性核"}, {"value": 1, "label": "RBF 高斯核"}]},
        {"id": "gamma", "label": "RBF γ", "min": 0.05, "max": 6.0, "step": 0.05, "default": 0.9},
        {"id": "noise", "label": "类别重叠", "min": 0.2, "max": 2.4, "step": 0.1, "default": 0.8},
    ],
    "mlp": [
        {"id": "hidden", "label": "隐藏神经元数", "min": 1, "max": 8, "step": 1, "default": 4},
        {"id": "lr", "label": "学习率 η", "min": 0.02, "max": 3.0, "step": 0.02, "default": 0.8},
        {"id": "act", "label": "激活函数", "min": 0, "max": 2, "step": 1, "default": 0,
         "options": [{"value": 0, "label": "Sigmoid"}, {"value": 1, "label": "tanh"}, {"value": 2, "label": "ReLU"}]},
        {"id": "data", "label": "数据集", "min": 0, "max": 2, "step": 1, "default": 1,
         "options": [{"value": 0, "label": "两团 blobs"}, {"value": 1, "label": "异或 XOR"}, {"value": 2, "label": "同心圆"}]},
        {"id": "sat", "label": "输入幅度（饱和压力）", "min": 0.5, "max": 6.0, "step": 0.1, "default": 1.2},
    ],
    "cnn": [
        {"id": "kernel", "label": "卷积核尺寸", "min": 1, "max": 7, "step": 2, "default": 3},
        {"id": "stride", "label": "步长", "min": 1, "max": 3, "step": 1, "default": 1},
        {"id": "pad", "label": "零填充", "min": 0, "max": 3, "step": 1, "default": 1},
        {"id": "filters", "label": "卷积核个数", "min": 1, "max": 8, "step": 1, "default": 3},
        {"id": "pattern", "label": "输入图案", "min": 0, "max": 3, "step": 1, "default": 1,
         "options": [{"value": 0, "label": "斜边"}, {"value": 1, "label": "圆环"}, {"value": 2, "label": "棋盘"}, {"value": 3, "label": "字母"}]},
    ],
    "tsne": [
        {"id": "perp", "label": "困惑度 perplexity", "min": 2, "max": 50, "step": 1, "default": 12,
         "hint": "它决定局部/全局的取舍，而不是「簇数」"},
        {"id": "lr", "label": "优化学习率", "min": 10, "max": 800, "step": 10, "default": 200},
        {"id": "clusters", "label": "真值簇数", "min": 2, "max": 6, "step": 1, "default": 4},
        {"id": "dim", "label": "原始维度", "min": 3, "max": 12, "step": 1, "default": 5},
    ],
}

# 每个 ready 算法需要哪些可视化（顺序即前端展示顺序）
VISUAL_SPEC: dict[str, list[dict[str, str]]] = {
    "linreg": [
        {"id": "landscape", "kind": "surface3d", "title": "损失地形与下降轨迹", "hint": "拖动旋转，观察 η 如何决定「走之字」还是「直冲谷底」"},
        {"id": "fit", "kind": "line2d", "title": "拟合曲线 vs 真实关系", "hint": "噪声与样本数如何改变你学到的那条线"},
        {"id": "residual", "kind": "bars", "title": "逐点残差 |ŷ−y|", "hint": "残差有没有系统性结构"},
    ],
    "logreg": [
        {"id": "prob3d", "kind": "cloud3d", "title": "Sigmoid 概率曲面", "hint": "z 轴 = 预测概率，看它如何把重叠的两团「切」开"},
        {"id": "landscape", "kind": "surface3d", "title": "交叉熵地形", "hint": "逻辑损失是凸的：没有局部极小，只有条件数问题"},
        {"id": "roc", "kind": "line2d", "title": "ROC 曲线", "hint": "阈值扫过的真正代价"},
    ],
    "knn": [
        {"id": "boundary", "kind": "cloud3d", "title": "3D 决策区域", "hint": "高度 = 投票结果，K 改变时边界的粗糙程度随之改变"},
        {"id": "votes", "kind": "bars", "title": "查询点的邻居投票", "hint": "距离加权如何改写多数决"},
        {"id": "errvs", "kind": "line2d", "title": "误差 vs K", "hint": "偏差-方差交换的经典 U 形"},
    ],
    "kmeans": [
        {"id": "clusters", "kind": "cloud3d", "title": "聚类过程（3D）", "hint": "质点被吸入最近的中心，直到不再改变"},
        {"id": "inertia", "kind": "line2d", "title": "惯性 inertia 随轮次下降", "hint": "每步必降：这是 K-Means 的单调性保证"},
        {"id": "elbow", "kind": "bars", "title": "肘部法则：inertia vs K", "hint": "拐点之前每加一簇都大赚，之后收益锐减"},
    ],
    "pca": [
        {"id": "axes", "kind": "vector3d", "title": "主成分方向", "hint": "找方差最大的方向：特征向量的几何意义"},
        {"id": "proj", "kind": "cloud3d", "title": "投影与重构误差", "hint": "降维丢掉了多少信息，一目了然"},
        {"id": "ratio", "kind": "bars", "title": "解释方差比", "hint": "累计过 90% 需要几个主成分"},
        {"id": "corr", "kind": "matrix", "title": "特征相关矩阵", "hint": "PCA 本质是在对角化它"},
    ],
    "tree": [
        {"id": "graph", "kind": "tree2d", "title": "树结构", "hint": "每个节点都是一次「if」"},
        {"id": "partition", "kind": "cloud3d", "title": "空间被轴平行超平面切碎", "hint": "叶子 = 空间中的一块长方体"},
        {"id": "overfit", "kind": "line2d", "title": "深度 vs 训练/验证误差", "hint": "过拟合长什么样"},
        {"id": "imp", "kind": "bars", "title": "特征重要性", "hint": "按不纯度下降累计"},
    ],
    "svm": [
        {"id": "margin", "kind": "cloud3d", "title": "最大间隔超平面", "hint": "只有支持向量在说话"},
        {"id": "decision", "kind": "surface3d", "title": "决策函数 f(x) 曲面", "hint": "线性核是平面，RBF 核是局部 bumps 之和"},
        {"id": "gamma", "kind": "line2d", "title": "γ / C vs 泛化误差", "hint": "容量与误差的U形"},
    ],
    "mlp": [
        {"id": "net", "kind": "tree2d", "title": "网络结构与参数", "hint": "2→H→1：先看清有几个数要学"},
        {"id": "logit3d", "kind": "cloud3d", "title": "输出 logit 曲面", "hint": "网络学到的那个函数本身"},
        {"id": "slice", "kind": "surface3d", "title": "权重空间切片", "hint": "9 维损失的 2 维切面：为什么反向传播有效但曲面崎岖"},
        {"id": "curve", "kind": "line2d", "title": "损失与准确率", "hint": "Sigmoid 饱和时的平台期"},
    ],
    "cnn": [
        {"id": "input", "kind": "surface3d", "title": "输入「图像」= 高度场", "hint": "灰度值当作高度看，更容易理解卷积核在扫什么"},
        {"id": "map", "kind": "surface3d", "title": "特征图（激活后）", "hint": "窗口在滑动，响应最强的位置会「长高」"},
        {"id": "size", "kind": "line2d", "title": "输出边长 / 参数量", "hint": "O = (I − K + 2P)/S + 1"},
        {"id": "params", "kind": "bars", "title": "各层参数量", "hint": "权值共享为什么省参数"},
    ],
    "tsne": [
        {"id": "raw", "kind": "cloud3d", "title": "高维原始数据（3D 切片）", "hint": "簇间距离在三维里其实分得很开"},
        {"id": "embed", "kind": "line2d", "title": "t-SNE 二维嵌入", "hint": "梯度下降在最小化 KL(Q‖P)"},
        {"id": "stress", "kind": "line2d", "title": "KL 散度下降", "hint": "早期夸张系数（early exaggeration）的作用"},
        {"id": "perp", "kind": "bars", "title": "困惑度 vs 簇的松紧", "hint": "同一个数据，不同 perplexity 讲不同的故事"},
    ],
}

METRIC_SPEC: dict[str, list[dict[str, str]]] = {
    "linreg": [{"id": "mse", "label": "MSE"}, {"id": "r2", "label": "R²"}],
    "logreg": [{"id": "loss", "label": "交叉熵"}, {"id": "acc", "label": "准确率"}, {"id": "auc", "label": "AUC"}],
    "knn": [{"id": "acc", "label": "准确率"}, {"id": "f1", "label": "F1"}],
    "kmeans": [{"id": "inertia", "label": "惯性"}, {"id": "ari", "label": "ARI"}],
    "pca": [{"id": "evr", "label": "首成分解释比"}, {"id": "err", "label": "重构误差"}],
    "tree": [{"id": "acc", "label": "训练准确率"}, {"id": "acc_val", "label": "验证准确率"}],
    "svm": [{"id": "acc", "label": "准确率"}, {"id": "margin", "label": "几何间隔"}, {"id": "sv", "label": "支持向量数"}],
    "mlp": [{"id": "loss", "label": "MSE"}, {"id": "acc", "label": "准确率"}, {"id": "gradnorm", "label": "‖∇L‖"}],
    "cnn": [{"id": "params", "label": "参数量"}, {"id": "out", "label": "输出边长"}, {"id": "rf", "label": "感受野"}],
    "tsne": [{"id": "kl", "label": "KL(Q‖P)"}, {"id": "ari", "label": "嵌入 ARI"}],
}

READY_KEYS = sorted(k for k in PARAM_SPECS)


def find_item(key: str) -> dict[str, Any] | None:
    for fam in FAMILIES:
        for it in fam["items"]:
            if it["key"] == key:
                return {**it, "family": fam["key"], "familyName": fam["name"], "color": fam["color"]}
    return None


def catalog_payload() -> dict[str, Any]:
    from app.content import loader  # 延迟导入，避免循环依赖

    fams = []
    for fam in FAMILIES:
        items = []
        for it in fam["items"]:
            tagline = ""
            if it["key"] in PARAM_SPECS:
                try:
                    tagline = loader.payload(it["key"]).get("tagline", "")
                except Exception:
                    tagline = ""
            items.append({
                "key": it["key"], "name": it["name"], "status": it["status"],
                "difficulty": it["difficulty"], "tags": it["tags"], "tagline": tagline,
            })
        fams.append({**{k: fam[k] for k in ("key", "name", "color", "blurb")}, "items": items})
    return {"families": fams, "readyCount": len(READY_KEYS),
            "totalCount": sum(len(f["items"]) for f in FAMILIES)}
