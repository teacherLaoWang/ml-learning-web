"""Qoder Agent SDK 适配层：把「某个概念 + 学生的问题」变成一次流式教学问答。

设计约束（这个站是教学站，不是聊天玩具）：

1. **模型只能看见我们给的那段教案**。上下文由服务端从 loader 里取，
   前端只传 key + 章节定位，不传正文 —— 免得有人改包体注入 prompt。
2. **不给任何工具**（`tools=[]`）。它只回答问题，不读文件、不跑命令。
3. **凭证只在环境变量里**（`QODER_PERSONAL_ACCESS_TOKEN`，或复用本机 qodercli 登录态）。
   前端永远拿不到 token，仓库里也永远不该出现。
4. SDK 是可选 extra（`uv sync --extra ai`）。没装/没配就明确报「未启用」，
   绝不静默返回假答案。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

MAX_QUESTION = 800
MAX_CONTEXT = 6000
HISTORY_TURNS = 4
TIMEOUT_S = 90.0
_CLI_TTL_S = 300.0


class AskUnavailable(RuntimeError):
    """SDK 没装 / 没凭证 —— 路由据此返回 503，前端显示配置指引。"""


SYSTEM_PROMPT = """你是一名机器学习助教，在一个交互式教学站上回答学生的问题。

学生的问题总是针对某一小节（一段直觉、一步推导、一条术语、一个公式）。你手里有那一小节的原文，\
回答时的硬性要求：

- 中文，口语化，短句。先一句话给结论，再解释为什么。
- 学生是自学神经网络的人，抽象描述对他没用：给一个能看见的画面或类比，再给一个具体数字算例。
- 能用本页的交互说清楚就说「把 xx 滑块拉到最大，你会看到……」，参数名用你看到的原文里的。
- 数学用 $...$ 行内、$$...$$ 独立成段，前端用 KaTeX 渲染；不要输出 Markdown 表格。
- 不确定的事实说不确定，不要编造数据集、论文或数值。
- 长度：默认 150-300 字。学生说「详细点」再展开。
- 如果学生问的超出这一小节，先答这一小节能答的，再用一句话指出该看站内哪一节。"""


def load_sdk() -> dict[str, Any]:
    """惰性导入。没装 extra 时返回 {'ok': False, 'reason': ...}，不抛异常。"""
    try:
        import qoder_agent_sdk as sdk
    except ImportError as exc:
        return {"ok": False, "reason": f"没装 qoder-agent-sdk：{exc}", "sdk": None}
    return {"ok": True, "reason": "", "sdk": sdk}


def auth_options(sdk: Any) -> tuple[Any, str]:
    """优先环境变量 PAT；退一步复用本机 qodercli 登录态。"""
    env_var = "QODER_PERSONAL_ACCESS_TOKEN"
    if os.environ.get(env_var):
        return sdk.access_token_from_env(env_var), "pat"
    ok, _ = cli_status()
    if ok:
        return sdk.qodercli_auth(), "qodercli"
    raise AskUnavailable(
        f"未配置凭证：设置环境变量 {env_var}"
        "（PAT 在 https://qoder.com/account/integrations 生成），"
        "或在终端跑一次 qodercli login"
    )


_CLI_STATE: dict[str, Any] = {"tick": -1.0, "ok": False, "why": ""}


def cli_status() -> tuple[bool, str]:
    """本机 qodercli 是否已登录。探测要起子进程，所以缓存 5 分钟。"""
    if time.monotonic() - _CLI_STATE["tick"] >= _CLI_TTL_S:
        _CLI_STATE.update(tick=time.monotonic(), **_probe_cli_login())
    return bool(_CLI_STATE["ok"]), str(_CLI_STATE["why"])


def _probe_cli_login() -> dict[str, Any]:
    cli = _qodercli_path()
    if not cli:
        return {"ok": False, "why": "找不到 qodercli（没装 SDK 或 PATH 里没有）"}
    try:
        r = subprocess.run(
            [cli, "status", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "why": f"qodercli status 跑不动：{exc}"}
    blob = (r.stdout or "").strip()
    account = ""
    try:
        data = json.loads(blob)
        if isinstance(data, dict):
            account = str(data.get("account") or data.get("username") or "")
    except json.JSONDecodeError:
        m = re.search(r"Account:\s*(.+)", blob)
        account = m.group(1).strip() if m else ""
    if not account or account.lower() == "not logged in":
        return {"ok": False, "why": "本机 qodercli 未登录"}
    return {"ok": True, "why": account}


def _qodercli_path() -> str | None:
    """优先用 SDK 自带的 CLI，其次 PATH 上的 qodercli。"""
    try:
        import qoder_agent_sdk

        bundled = Path(qoder_agent_sdk.__file__).parent / "_bundled" / "qodercli"
        if bundled.is_file() and os.access(bundled, os.X_OK):
            return str(bundled)
    except ImportError:  # pragma: no cover - 没装 extra 时走这里
        pass
    return shutil.which("qodercli")


def ask_status() -> dict[str, Any]:
    """/api/ask/status 的返回体：前端据此决定要不要显示提问入口。"""
    loaded = load_sdk()
    if not loaded["ok"]:
        return {"ready": False, "sdkInstalled": False, "reason": loaded["reason"]}
    try:
        _, mode = auth_options(loaded["sdk"])
    except AskUnavailable as exc:
        return {"ready": False, "sdkInstalled": True, "reason": str(exc)}
    return {
        "ready": True,
        "sdkInstalled": True,
        "mode": mode,
        "model": os.environ.get("QODER_MODEL") or "auto",
        "note": "答案由大模型生成，教学站正文是人工校对过的，两者不一致时以正文为准。",
    }


def build_prompt(
    question: str, context: str, section_label: str, algo_name: str, history: list[dict[str, str]]
) -> str:
    parts = [
        f"【站点】机器学习交互教学站\n【算法】{algo_name}\n【小节】{section_label}",
        f"【这一小节的原文】\n{context}",
    ]
    tail = [h for h in history if h.get("role") in ("user", "assistant")][-HISTORY_TURNS:]
    if tail:
        lines = ["【前面的问答】"]
        for h in tail:
            lines.append(f"{'学生' if h['role'] == 'user' else '助教'}：{h.get('text', '')[:400]}")
        parts.append("\n".join(lines))
    parts.append(f"【学生现在的问题】{question.strip()[:MAX_QUESTION]}")
    return "\n\n".join(parts)


async def ask_stream(prompt: str) -> AsyncIterator[dict[str, Any]]:
    """跑一次问答，yield {'type': 'delta'|'done'|'error', ...}。

    delta 优先吃 SDK 的 partial message；万一 SDK 没开增量，
    最后一条 AssistantMessage 会兜住，不会一个字都不显示。
    """
    loaded = load_sdk()
    if not loaded["ok"]:
        yield {"type": "error", "message": loaded["reason"]}
        return
    sdk = loaded["sdk"]
    try:
        auth, _mode = auth_options(sdk)
    except AskUnavailable as exc:
        yield {"type": "error", "message": str(exc)}
        return

    options = sdk.QoderAgentOptions(
        auth=auth,
        tools=[],  # 纯问答：不给文件/命令工具
        system_prompt=SYSTEM_PROMPT,
        max_turns=1,
        include_partial_messages=True,
        cwd=tempfile.gettempdir(),
        model=os.environ.get("QODER_MODEL") or None,
    )

    streamed = 0
    fallback = ""
    agen = sdk.query(prompt=prompt, options=options)
    try:
        async with asyncio.timeout(TIMEOUT_S):
            async for msg in agen:
                cls = type(msg).__name__
                if cls == "StreamEvent":
                    text = _delta_text(getattr(msg, "event", None))
                    if text:
                        streamed += len(text)
                        yield {"type": "delta", "text": text}
                elif cls == "AssistantMessage":
                    err = getattr(msg, "error", None)
                    if err:
                        yield {"type": "error", "message": f"模型返回错误：{err}"}
                        return
                    for block in getattr(msg, "content", None) or []:
                        if type(block).__name__ == "TextBlock":
                            fallback += block.text or ""
                            if not streamed:
                                yield {"type": "delta", "text": block.text or ""}
                elif cls == "ResultMessage":
                    if getattr(msg, "is_error", False):
                        errs = getattr(msg, "errors", None) or []
                        yield {"type": "error", "message": "；".join(str(e) for e in errs) or "模型调用失败"}
                        return
                    if not streamed and fallback:
                        yield {"type": "delta", "text": ""}
                    yield {
                        "type": "done",
                        "turns": getattr(msg, "num_turns", 0),
                        "ms": getattr(msg, "duration_ms", 0),
                        "costUsd": getattr(msg, "total_cost_usd", None),
                    }
                    return
        yield {"type": "error", "message": f"{TIMEOUT_S:.0f}s 内没有收到完整回答"}
    except TimeoutError:
        yield {"type": "error", "message": f"提问超时（>{TIMEOUT_S:.0f}s）"}
    except Exception as exc:  # SDK 的异常种类太多，统一转成前端可读的错误
        yield {"type": "error", "message": f"{type(exc).__name__}: {exc}"}
    finally:
        with contextlib.suppress(Exception):  # 客户端断开时关流失败无所谓
            await agen.aclose()


def _delta_text(event: Any) -> str:
    """从 Anthropic 风格的 stream event 里挑出正文增量。"""
    if not isinstance(event, dict):
        return ""
    if event.get("type") == "content_block_delta":
        delta = event.get("delta") or {}
        if delta.get("type") == "text_delta":
            return str(delta.get("text") or "")
    return ""
