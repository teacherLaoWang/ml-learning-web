"""ML 交互式学习站后端入口。

开发：  uv run uvicorn app.main:app --reload --port 8200   （前端 npm run dev 走 5173 代理）
生产：  cd frontend && npm run build，然后只跑本端口即可（离线、单端口）
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.ask import router as ask_router
from app.api.routes import router as api_router
from app.content import catalog, loader

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "frontend" / "dist"

app = FastAPI(
    title="机器学习 3D 仿真学习站",
    description="FastAPI + NumPy/PyTorch 真跑训练，Vue3 + three.js 立体演示",
    version="0.1.0",
)

# 只给本地 vite dev server 开 CORS；生产是同源静态文件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ask_router)


@app.get("/api/summary")
def summary() -> dict[str, object]:
    cat = catalog.catalog_payload()
    ready = [loader.payload(k) for k in catalog.READY_KEYS]
    return {
        "total": cat["totalCount"],
        "ready": cat["readyCount"],
        "families": [{k: f[k] for k in ("key", "name", "color")} for f in cat["families"]],
        "incompleteLessons": [
            {"key": r["key"], "missing": r.get("missingText", []) + ([r["contentError"]] if r.get("contentError") else [])}
            for r in ready if r.get("missingText") or r.get("contentError")
        ],
    }


if DIST.is_dir():
    # dist/assets 里的文件名带内容哈希 → 长期缓存；index.html 必须每次回源，
    # 否则 npm run build 之后浏览器还在要旧哈希的分片，路由会白屏
    @app.middleware("http")
    async def cache_headers(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path in ("/", "/index.html"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> object:
        candidate = (DIST / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(DIST.resolve()):
            return FileResponse(candidate)
        if not path:
            return FileResponse(DIST / "index.html")
        if "." in path:
            # 看起来是静态资源却找不到：给明确 404，别返回 HTML（浏览器会按 MIME 报错）
            return JSONResponse(status_code=404, content={"detail": f"没有这个静态文件：{path}"})
        # 前端是 hash 路由（/#/algo/mlp），深链一律回到根路径，
        # 这样 index.html 里的相对资源路径 ./assets/… 才能正确解析
        return RedirectResponse(url="/", status_code=307)
else:
    @app.get("/", include_in_schema=False)
    def not_built() -> JSONResponse:
        return JSONResponse(
            status_code=200,
            content={
                "message": "后端已就绪，前端还没构建。开发模式：cd frontend && npm install && npm run dev（5173）；"
                           "或 npm run build 后刷新本页。",
                "api": ["/api/env", "/api/catalog", "/api/algorithms", "/api/algorithms/{key}",
                        "/api/algorithms/{key}/fit", "/api/glossary", "/api/summary"],
                "ready": catalog.READY_KEYS,
            },
        )
