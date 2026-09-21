# 机器学习 3D 仿真学习站（ml-learning-web）

把「机器学习算法」做成一个可以**亲手调参、亲眼看到优化过程在三维地形上流动**的学习站。
后端 FastAPI 用 NumPy（可选 PyTorch）**真跑**训练并返回轨迹数据，前端 Vue 3 + three.js 把损失曲面、
决策边界、主成分方向、卷积滑窗渲染成可旋转、可播放、可单步的立体仿真。

- 覆盖范围：六大类 **41 个条目**的目录与讲解，其中 **10 个算法**做成了完整的 3D 交互仿真
  （线性回归、逻辑回归、K 近邻、K-Means、PCA、t-SNE、决策树、SVM、多层感知机 + 反向传播、卷积神经网络）。
- 教案写法：每个概念都给「公式 + 变量释义 + 代入真实数字的算例」，术语有英文全称与速查表。
- 完全离线可用：`npm run build` 之后由 FastAPI 单端口托管全部静态资源，不依赖任何 CDN。

## 快速开始

```bash
cd ml-learning-web

# 1) 后端依赖（NumPy 打底，全部演示都能跑）
uv sync

# 1b) 可选：装真训练内核（torch，约几百 MB）；装了之后 MLP/CNN 演示走 autograd，没装自动退回 NumPy
uv sync --extra ml

# 2) 前端依赖与构建（国内镜像）
cd frontend
npm --registry=https://registry.npmmirror.com install
npm run build
cd ..

# 3) 启动：单端口，浏览器打开 http://127.0.0.1:8200
uv run uvicorn app.main:app --host 127.0.0.1 --port 8200
```

开发模式（前端热更新）：

```bash
uv run uvicorn app.main:app --reload --port 8200     # 终端 A
cd frontend && npm run dev                            # 终端 B → http://127.0.0.1:5173（/api 自动代理到 8200）
```

> 注意：后端在**启动时**才决定是否挂载 `frontend/dist`。如果先起了服务再 `npm run build`，
> 需要重启一次 uvicorn 才能看到新构建的前端页面。

自检：`uv run python -m tools.probe`（把 10 个 ready 算法各跑一遍，检查 visual 是否齐全、
有没有 NaN/Inf/非 JSON 类型、返回体积与耗时），加 `--sweep` 会把每个参数的上下端点都跑一遍。

只想起后端先看数据接口：访问 `http://127.0.0.1:8200/docs`（FastAPI 自带 Swagger）。

## 目录结构

```
app/
  main.py              FastAPI 入口：/api 路由 + frontend/dist 静态托管
  api/routes.py        HTTP 层：参数校验、中文错误、耗时统计
  content/
    catalog.py         机读事实：六大类目录、每个 ready 算法的参数范围/可视化清单/指标
    loader.py          教案装载与合成（ready ← lessons/，outline ← outline.py）
    lessons/{key}.py   10 篇精做教案（纯文字 + 数字算例）
    outline.py         31 张概念卡片（有讲解、无仿真）
  ml/
    backend.py         PyTorch 可用性探测（MPS/CUDA/CPU）
    registry.py        参数钳制、结果规范化、visual 校验
    datasets.py        可复现的合成数据集（blobs/moons/xor/circles/…）
    {key}.py           各算法实现：run(params, seed, steps) → 契约负载
docs/API-CONTRACT.md   前后端数据契约（改接口必须先改这里）
frontend/              Vue 3 + Vite + TS + three.js
tests/                 pytest：内容一致性、数值正确性、HTTP 契约
```

## 数据接口

| 端点 | 用途 |
| --- | --- |
| `GET /api/env` | Python / NumPy / PyTorch 状态 |
| `GET /api/catalog` | 六大类全景目录 |
| `GET /api/algorithms/{key}` | 单个算法完整教案 |
| `POST /api/algorithms/{key}/fit` | 用给定参数真跑，返回 metrics + series + table + visuals |
| `POST /api/algorithms/{key}/step` | 推进到第 N 步（同 seed 同轨迹，可复现） |
| `GET /api/glossary` | 全站术语速查 |
| `GET /api/summary` | 内容完成度自检（哪些教案还缺字段） |

请求示例：

```bash
curl -s localhost:8200/api/algorithms/mlp/fit \
  -H 'content-type: application/json' \
  -d '{"params":{"hidden":2,"lr":0.5,"act":0,"data":1},"seed":7,"steps":60}' | head -c 400
```

## 测试

```bash
uv run pytest            # 内容一致性 + 数值正确性 + HTTP 契约
uv run ruff check app tests
cd frontend && npm run typecheck && npm run build
```

## 设计与教学约定（改动前请读）

1. **参数与可视化清单的唯一事实来源是 `app/content/catalog.py`**；前端控件、后端校验、数值实现三方都从它派生，
   不要在别处硬编码算法专属逻辑。
2. **动画必须由时间驱动**（轨迹插值、卷积窗口滑动、聚类收缩），不接受「只换颜色」式的伪动画；
   页面不可见时自动暂停渲染。
3. **图形不得互相遮挡**：绘制顺序固定为 连线 → 实体 → 坐标轴 → 文字（带半透明底板衬底）；
   标签要按索引错开，浮窗要自动避让视口边缘。
4. 前端有 **mock 兜底**：后端未启动时用 `frontend/src/fixtures/*.json` 照常演示，并在界面顶部标注「离线演示数据」。
5. 站点只监听 `127.0.0.1`，不涉及远程访问。

## 已知限制

- `outline` 状态的条目只有概念卡片，没有可调参的仿真（`simHint` 字段记录了后续要做的 3D 仿真设想）。
- t-SNE 是 O(n²) 实现，样本量固定在 140~200；不是用来跑真数据的。
- SVM 走 primal 简化求解，大规模/难分数据上的表现不代表真实库（如 LIBSVM）的实现质量。
- PyTorch 是可选 extra：未安装时深度学习页会退回纯 NumPy 手写实现（数学口径一致，但速度较慢）。
