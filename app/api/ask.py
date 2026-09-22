"""/api/ask —— 逐概念提问。SSE 流式，前端 fetch + ReadableStream 读。

响应帧（每行 `data: {json}\\n\\n`）：
  {"type":"delta","text":"…"}     正文增量
  {"type":"done","turns":1,"ms":…,"costUsd":…}
  {"type":"error","message":"…"}  出错（前端原样显示，不降级成假答案）
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app import ai
from app.content import catalog, loader
from app.ml import registry

router = APIRouter(prefix="/api")

MAX_HISTORY = 8


class AskRequest(BaseModel):
    key: str = Field(description="教案 key，决定服务端取哪段原文当上下文")
    section: dict[str, Any] = Field(default_factory=dict, description="{'kind': 'intuition', 'index': 0}")
    question: str = Field(min_length=1, max_length=ai.MAX_QUESTION)
    params: dict[str, Any] = Field(default_factory=dict, description="学生当前的滑块值（可选）")
    history: list[dict[str, str]] = Field(default_factory=list, description="本小节内前几轮问答")

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        """min_length 拦不住全是空格的输入，这里补一刀，免得白跑一次模型。"""
        stripped = v.strip()
        if not stripped:
            raise ValueError("问题不能是空白")
        return stripped


@router.get("/ask/status")
def get_ask_status() -> dict[str, Any]:
    return ai.ask_status()


def _fmt_params(key: str, raw: dict[str, Any]) -> str:
    specs = catalog.PARAM_SPECS.get(key) or []
    if not specs or not raw:
        return ""
    try:
        vals = registry.coerce_params(key, raw)
    except Exception:  # 参数不合法不影响提问，丢掉这段上下文即可
        return ""
    labels = {s["id"]: s.get("label", s["id"]) for s in specs}
    return "；".join(f"{labels.get(k, k)}={v}" for k, v in sorted(vals.items()))


def _lookup(payload: dict[str, Any], section: dict[str, Any]) -> tuple[str, str]:
    """返回 (小节标题, 上下文原文)。取不到就 404 —— 别拿空上下文去问模型。"""
    kind = str(section.get("kind") or "page")
    idx = section.get("index")
    if kind == "story":
        return "故事", payload.get("story", "")
    if kind == "formula":
        f = payload.get("formula") or {}
        lines = [f.get("text", "")]
        lines += [f"{v.get('sym')}：{v.get('zh')}" for v in f.get("vars") or []]
        return "公式", "\n".join(x for x in lines if x)
    if kind == "intuition":
        items = payload.get("intuition") or []
        i = _need_index(idx, len(items), "直觉")
        return f"直觉 · 第 {i + 1} 段", items[i]
    if kind == "derivation":
        items = payload.get("derivation") or []
        i = _need_index(idx, len(items), "推导")
        d = items[i]
        body = f"{d.get('title', '')}\n{d.get('body', '')}"
        if d.get("formula"):
            body += f"\n公式：{d['formula']}"
        return f"推导 · 第 {i + 1} 步（{d.get('title', '')}）", body
    if kind == "term":
        want = str(section.get("term") or "")
        for t in payload.get("terms") or []:
            if t.get("term") == want:
                full = f"（{t['full']}）" if t.get("full") else ""
                return f"术语 · {t['term']}{full}", f"{t['term']}{full}：{t.get('explain', '')}"
        raise HTTPException(404, f"这篇教案里没有术语「{want}」")
    if kind == "pitfall":
        items = payload.get("pitfalls") or []
        i = _need_index(idx, len(items), "常见坑")
        return f"常见坑 · 第 {i + 1} 条", items[i]
    if kind == "visual":
        want = str(section.get("id") or "")
        for v in payload.get("visuals") or []:
            if v.get("id") == want:
                return f"图形 · {v.get('title', '')}", f"{v.get('title')}：{v.get('hint', '')}"
        raise HTTPException(404, f"没有这个图表面板：{want}")
    if kind == "param":
        want = str(section.get("id") or "")
        for s in payload.get("params") or []:
            if s.get("id") == want:
                return (
                    f"参数 · {s.get('label', want)}",
                    f"{s.get('label')}：范围 {s.get('min')}~{s.get('max')}，默认 {s.get('default')}。{s.get('hint', '')}",
                )
        raise HTTPException(404, f"没有这个参数：{want}")
    if kind == "page":
        return (
            "整页概览",
            "\n".join(
                x
                for x in [
                    payload.get("tagline", ""),
                    payload.get("story", ""),
                    "\n".join(payload.get("intuition") or [])[:2000],
                ]
                if x
            ),
        )
    raise HTTPException(400, f"不认识的小节类型：{kind}")


def _need_index(idx: Any, n: int, label: str) -> int:
    try:
        i = int(idx)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise HTTPException(400, f"{label}小节必须给 index") from None
    if not 0 <= i < n:
        raise HTTPException(404, f"{label}小节下标越界：{i}（共 {n} 项）")
    return i


@router.post("/ask")
async def post_ask(req: AskRequest) -> Any:
    status = ai.ask_status()
    if not status["ready"]:
        raise HTTPException(503, status["reason"])
    try:
        payload = loader.payload(req.key)
    except KeyError:
        raise HTTPException(404, f"没有这个算法：{req.key}") from None

    label, context = _lookup(payload, req.section)
    if not context.strip():
        raise HTTPException(404, f"「{label}」这一节还没有正文，没什么可问的")
    extra = _fmt_params(req.key, req.params)
    if extra:
        context += f"\n\n学生当前把参数设成：{extra}"
    prompt = ai.build_prompt(
        question=req.question,
        context=context[: ai.MAX_CONTEXT],
        section_label=label,
        algo_name=payload.get("name", req.key),
        history=req.history[-MAX_HISTORY:],
    )

    async def frame() -> AsyncIterator[str]:
        async for ev in ai.ask_stream(prompt):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(frame(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
