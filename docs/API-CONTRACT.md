# 数据契约（前后端共同遵守，改动需同步三处：`app/content/registry.py`、`app/ml/*`、`frontend/src/types.ts`）

## 0. 通用约定

- Base：`/api`。所有响应 `application/json`，NumPy 数组一律先 `tolist()`；浮点在服务端 round 到 6 位。
- 出错：HTTP 4xx/5xx + `{"detail": "中文错误信息"}`。
- 三维坐标一律右手系、单位无量纲；前端负责归一化到可视尺度。

## 1. 端点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/env` | 运行环境：NumPy / PyTorch 是否可用 |
| GET | `/api/catalog` | 算法全景目录（六大类 + 每类条目） |
| GET | `/api/algorithms/{key}` | 单个算法的完整教案（内容 + 参数定义 + 需要的可视化类型） |
| POST | `/api/algorithms/{key}/fit` | 用给定参数真跑训练/拟合，返回一批 `visuals` |
| POST | `/api/algorithms/{key}/step` | 只推进 `n` 步（前端「单步」按钮），返回同结构 + `resumed:true` |

### GET /api/env

```json
{"python":"3.12.13","numpy":"2.1.0","torch":{"available":false,"version":null,"device":null},
 "hint":"安装可选内核：uv sync --extra ml"}
```

### GET /api/catalog

```json
{"families":[
  {"key":"supervised","name":"监督学习","blurb":"有标签：拟合 y=f(x)","color":"#2563eb",
   "items":[{"key":"linreg","name":"线性回归","tagline":"最小二乘拟合一条直线","status":"ready","difficulty":1,"tags":["回归","闭式解","梯度下降"]}]}
]}
```
`status`：`ready`（v1 精做，有 3D 仿真）| `outline`（仅目录 + 概念卡片，无仿真）。

### GET /api/algorithms/{key}

```json
{
 "key":"linreg","name":"线性回归","family":"supervised","status":"ready",
 "tagline":"用一条直线/超平面去拟合连续标签",
 "story":"从高斯的最小二乘（1805）到今天的回归基线……",
 "formula":{"text":"ŷ = w·x + b","latexish":"","vars":[{"sym":"w","zh":"权重（斜率）"},{"sym":"b","zh":"偏置（截距）"}]},
 "intuition":["段落一","段落二"],
 "derivation":[{"title":"损失函数","body":"说明文字","formula":"MSE = (1/n)Σ(ŷᵢ − yᵢ)²"}],
 "terms":[{"term":"OLS","full":"Ordinary Least Squares","explain":"普通最小二乘……"}],
 "params":[{"id":"lr","label":"学习率 η","min":0.001,"max":1.0,"step":0.001,"default":0.1,"hint":"太大发散"}],
 "presets":[{"id":"demo","label":"演示","params":{"lr":0.1}}],
 "metrics":[{"id":"r2","label":"R²"}],
 "visuals":[{"id":"landscape","kind":"surface3d","title":"损失地形","hint":"拖动旋转，观察下降轨迹"}],
 "pitfalls":["……"], "seeAlso":["logreg","svm"],
 "quiz":{"q":"问题","options":["a","b"],"answer":1,"why":"解释"}
}
```
`visuals[].kind` 只声明需要哪几种；具体数据由 `/fit` 返回。

### POST /api/algorithms/{key}/fit

请求：`{"params":{"lr":0.1,"degree":3},"seed":7,"steps":150}`
（`steps` 上限 400；`params` 未给的用 `params[].default`）

响应：

```json
{
 "key":"linreg","backend":"numpy","elapsedMs":18.4,"steps":150,"seed":7,
 "params":{"lr":0.1},
 "metrics":{"loss":0.083,"r2":0.974,"accuracy":null,"f1":null,"epoch":150,"note":"…"},
 "series":[{"id":"loss","label":"损失","x":[0,1,2],"y":[1.9,1.2,0.8],"xLabel":"epoch","yLabel":"MSE"}],
 "table":[{"id":"coef","title":"参数","rows":[{"name":"w","value":"1.21","truth":"1.20","delta":"0.01"}]}],
 "visuals":[ /* 见 §2 */ ]
}
```

## 2. visual 负载（`visuals[]` 每项 = `{id, kind, title, hint?, data}`）

前端按 `kind` 分派组件；`data` 结构如下。坐标维度：`surface3d/cloud3d/vector3d` 的 x/y/z 为三维；`line2d/bars/matrix/tree2d` 为二维 SVG。

**surface3d** — 三维曲面 + 动画轨迹（损失地形、分类置信面等）
```json
{"axes":{"x":{"label":"w","min":-3,"max":3},"y":{"label":"b","min":-3,"max":3},"z":{"label":"MSE","min":0,"max":2}},
 "grid":{"x":[-3,-2.9],"y":[-3,-2.9],"z":[[0.1,0.2],[0.3,0.4]]},
 "levels":[0.2,0.5,1.0],
 "path":[{"x":1.2,"y":-0.4,"z":0.9,"step":0,"grad":[0.1,-0.2]}],
 "optimum":{"x":1.0,"y":0.0,"z":0.02,"label":"全局最优"},
 "markers":[{"x":0.5,"y":0.5,"z":1.0,"label":"起点","color":"#f97316"}],
 "window":{"size":3,"stride":1,"x":0,"y":0,"label":"3×3 卷积核"},
 "climaxNote":"山腰的平地把梯度压成了 0"}
```
`grid.z` 形状固定为 `[len(y)][len(x)]`；`len(x)==len(y)` 不是必须。`path` 是动画主角。
`window` 为可选字段：存在时前端要画一个沿网格从左到右、从上到下逐格滑动的线框（卷积演示用），
`size` 是核边长（标量；也接受 `[宽, 高]`），`x`/`y` 只是服务端给的起始提示，动画进度由前端时间轴决定。

**cloud3d** — 三维散点 + 可选分割面/投影面
```json
{"legend":[{"label":"类别 0","color":"#2563eb"}],
 "points":[{"x":0.1,"y":0.2,"z":0.3,"label":0,"size":1}],
 "boundary":{"axes":{"x":{"label":"f₁","min":-2,"max":2},"y":{"label":"f₂","min":-2,"max":2},"z":{"label":"决策函数"}},
             "grid":{"x":[],"y":[],"z":[[]]}, "contour0":true, "level":0.5},
 "projection":{"origin":[0,0,0],"normal":[0.7,0.7,0],"label":"判别方向"},
 "centroids":[{"x":0.1,"y":0.2,"z":0.3,"label":0,"size":1.4,"step":5}],
 "hulls":[{"label":"质心 0 的移动轨迹","color":"#2563eb","mode":"path","points":[[0,0,0]]}]}
```
`points[].label` 可为类别整数（走 legend 配色）或 `null`（单色点）。
`boundary.grid.z` 里可以放回归值（概率/logit）或类别编码（0、1）；`contour0:true` 表示要画一条分界等高线，
位置由 `level` 决定 —— **概率/投票率面必须显式发 `level: 0.5`**（logreg、mlp、knn、tree 都属此类），
决策函数面（svm）留空即按 0。
`hulls[].mode`：`path` = 有序轨迹（K-Means 质心移动路径，不闭合，前端在末端点标记收敛点）；
缺省 `loop` = 首尾相连的轮廓。`centroids` 给的是最终质心，前端会标「中心 j」并参与收缩动画。

**vector3d** — 向量/箭头场（PCA 主成分、梯度场）
```json
{"arrows":[{"from":[0,0,0],"to":[1,0,0],"color":"#dc2626","label":"PC1 (方差 62%)","dash":false}],
 "points":[{"x":0.2,"y":0.1,"z":0.0,"label":0}],
 "axes":{"x":"x₁","y":"x₂","z":"x₃"}}
```

**line2d** — 多条二维曲线（ROC、学习曲线、激活函数）
```json
{"curves":[{"id":"roc","label":"ROC","x":[0,0.5,1],"y":[0,0.9,1],"dash":false,"color":"#2563eb"}],
 "axes":{"x":{"label":"FPR","min":0,"max":1},"y":{"label":"TPR","min":0,"max":1}},"diagonal":true}
```

**bars** — 柱状（特征重要性、混淆计数）
```json
{"labels":["x₁","x₂"],"values":[0.72,0.11],"unit":"%","axes":{"y":{"label":"重要性"}}}
```

**matrix** — 混淆矩阵 / 相关矩阵
```json
{"labels":["0","1"],"rows":[[12,3],[2,18]],"title":"混淆矩阵","percent":false}
```

**tree2d** — 通用节点-连线图（决策树结构、神经网络结构都用它）
```json
{"nodes":[{"id":0,"x":0,"y":0,"title":"x₂ ≤ 0.35","lines":["n=120","Gini 0.44"],"leaf":false,"color":"#8b5cf6","shape":"circle"}],
 "edges":[{"from":0,"to":1,"label":"是"}],
 "layers":[["x1","x2"],["h1","h2"],["o"]]}
```
`x`/`y` 由服务端算好（前端只做等距缩放渲染，不负责布局）；`lines` 是节点下方的次要说明文字。
`shape` 可选 `circle|rect`；网络结构图用 `layers` 给出分层分组（可选），决策树不填。


## 3. 前端渲染约定（避免「遮挡/不流动」两类老问题）

1. 绘制/层叠顺序固定：网格线 → 实体 → 轴 → 文字与标签底板。任何文字都要有半透明底板衬底，禁止与线重叠。
2. 动画必须由时间驱动（`requestAnimationFrame` 推进插值/相位），不得只换颜色；页面不可见时自动暂停以省电。
3. 关键词（NN/SGD/MSE/Gini…）统一走 `TermTip`：悬浮即解释，且自动避让视口边缘。
4. 所有 `visual` 面板支持 `mock` 模式：`frontend/src/fixtures/{key}.json` 与 `/fit` 响应结构完全一致，后端未启动时前端仍可离线演示。

## 4. 内容规范（教学部分）

- 中文为主，术语首次出现给英文全称；公式一律给「符号 + 变量释义 + 代入真实数字的算例」三件套。
- 每个 `ready` 算法至少：1 段直觉、3 步以上推导或流程、6 条以上术语、1 个可调参数组（含会让它失败的极端值）、2 个 visual。
- 常见坑（`pitfalls`）要具体到「什么现象 → 为什么 → 怎么办」。
