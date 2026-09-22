"""/api/ask 的契约测试 —— 不调真实模型，SDK 用假的替身。

这一组测试盯的是三件事：
1. 没配凭证时必须明确报「未启用」，不能给出看似正常的空答案；
2. 喂给模型的上下文只从服务端教案里取，前端伪造不了；
3. SSE 帧格式稳定，前端才能流式显示。
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import ai
from app.api import ask as ask_mod
from app.main import app

HAS_SDK = importlib.util.find_spec("qoder_agent_sdk") is not None
needs_sdk = pytest.mark.skipif(
    not HAS_SDK, reason="qoder-agent-sdk 是可选 extra（uv sync --extra ai），CI 主环境不装"
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认让「未配置」成为初值，个别用例再自己打开开关。"""
    monkeypatch.delenv("QODER_PERSONAL_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(ai, "_CLI_STATE", {"tick": 1e9, "ok": False, "why": "本机 qodercli 未登录"})


# ------------------------------------------------------------------ 状态 ----


@needs_sdk
def test_status_reports_missing_token(client: TestClient) -> None:
    body = client.get("/api/ask/status").json()
    assert body["ready"] is False
    assert "QODER_PERSONAL_ACCESS_TOKEN" in body["reason"]
    assert "qodercli login" in body["reason"]


@needs_sdk
def test_status_ready_with_pat(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QODER_PERSONAL_ACCESS_TOKEN", "pat-not-a-real-one")
    body = client.get("/api/ask/status").json()
    assert body["ready"] is True
    assert body["mode"] == "pat"
    assert "以正文为准" in body["note"]


@needs_sdk
def test_status_reuses_local_cli_login(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai, "_CLI_STATE", {"tick": 1e9, "ok": True, "why": "teacherLaoWang"})
    body = client.get("/api/ask/status").json()
    assert body["ready"] is True and body["mode"] == "qodercli"


# ------------------------------------------------------------------ 取上下文 ----


def test_lookup_covers_every_section_kind() -> None:
    from app.content import loader

    payload = loader.payload("linreg")
    cases: list[tuple[dict[str, Any], str]] = [
        ({"kind": "story"}, "故事"),
        ({"kind": "formula"}, "公式"),
        ({"kind": "page"}, "整页概览"),
    ]
    for section, label in cases:
        title, text = ask_mod._lookup(payload, section)
        assert title.startswith(label)
        assert text.strip()
    title, text = ask_mod._lookup(payload, {"kind": "intuition", "index": 0})
    assert "第 1 段" in title and text == payload["intuition"][0]
    title, text = ask_mod._lookup(payload, {"kind": "derivation", "index": 0})
    assert payload["derivation"][0]["title"] in title
    assert payload["derivation"][0]["body"] in text
    term = payload["terms"][0]["term"]
    title, text = ask_mod._lookup(payload, {"kind": "term", "term": term})
    assert term in title and term in text
    _title, text = ask_mod._lookup(payload, {"kind": "pitfall", "index": 1})
    assert text == payload["pitfalls"][1]
    _title, text = ask_mod._lookup(payload, {"kind": "visual", "id": payload["visuals"][0]["id"]})
    assert text.strip()
    _title, text = ask_mod._lookup(payload, {"kind": "param", "id": payload["params"][0]["id"]})
    assert "范围" in text


@pytest.mark.parametrize(
    ("section", "code"),
    [
        ({"kind": "nonsense"}, 400),
        ({"kind": "intuition"}, 400),  # 缺 index
        ({"kind": "intuition", "index": 999}, 404),
        ({"kind": "term", "term": "不存在的术语"}, 404),
        ({"kind": "visual", "id": "nope"}, 404),
        ({"kind": "param", "id": "nope"}, 404),
    ],
)
def test_lookup_rejects_bad_sections(section: dict[str, Any], code: int) -> None:
    from fastapi import HTTPException

    from app.content import loader

    with pytest.raises(HTTPException) as exc:
        ask_mod._lookup(loader.payload("linreg"), section)
    assert exc.value.status_code == code


def test_prompt_carries_context_and_history() -> None:
    prompt = ai.build_prompt(
        question="为什么要除以 n-1？",
        context="方差估计……",
        section_label="直觉 · 第 2 段",
        algo_name="线性回归",
        history=[
            {"role": "user", "text": "第一问"},
            {"role": "assistant", "text": "第一答"},
            {"role": "user", "text": "追问"},
        ],
    )
    assert "线性回归" in prompt and "直觉 · 第 2 段" in prompt
    assert "方差估计" in prompt and "为什么要除以 n-1？" in prompt
    assert "学生：第一问" in prompt and "助教：第一答" in prompt
    assert "追问" in prompt.split("前面的问答")[1]


def test_current_slider_values_join_the_context(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    async def fake_stream(prompt: str) -> AsyncIterator[dict[str, Any]]:
        seen["prompt"] = prompt
        yield {"type": "delta", "text": "好"}
        yield {"type": "done", "turns": 1, "ms": 12, "costUsd": 0.001}

    monkeypatch.setattr(ai, "ask_stream", fake_stream)
    monkeypatch.setattr(ai, "ask_status", lambda: {"ready": True, "mode": "pat"})
    client = TestClient(app)
    client.post(
        "/api/ask",
        json={
            "key": "linreg",
            "section": {"kind": "intuition", "index": 0},
            "question": "把学习率调到 1 会怎样？",
            "params": {"lr": 999, "n": 40},
        },
    )
    prompt = seen["prompt"]
    assert "学生当前把参数设成" in prompt
    # 越界的 lr 会被钳到参数规格的上限，而不是原样喂进去
    assert "999" not in prompt


def test_history_is_capped() -> None:
    long_hist = [{"role": "user", "text": f"q{i}"} for i in range(30)]
    prompt = ai.build_prompt("现在的问题", "上下文", "公式", "KNN", long_hist)
    tail = prompt.split("前面的问答")[1]
    assert "q29" in tail and "q24" not in tail


# ------------------------------------------------------------------ 路由 ----


@needs_sdk
def test_ask_is_503_when_not_configured(client: TestClient) -> None:
    r = client.post(
        "/api/ask",
        json={"key": "linreg", "section": {"kind": "story"}, "question": "这跟最小二乘有什么关系？"},
    )
    assert r.status_code == 503
    assert "QODER_PERSONAL_ACCESS_TOKEN" in r.json()["detail"]


def test_ask_rejects_unknown_key_and_empty_question(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai, "ask_status", lambda: {"ready": True, "mode": "pat"})
    ok = client.post(
        "/api/ask", json={"key": "nope", "section": {"kind": "story"}, "question": "x"}
    )
    assert ok.status_code == 404
    empty = client.post(
        "/api/ask", json={"key": "linreg", "section": {"kind": "story"}, "question": "   "}
    )
    assert empty.status_code == 422


def test_ask_streams_sse_frames(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_stream(prompt: str) -> AsyncIterator[dict[str, Any]]:
        assert "线性回归" in prompt
        yield {"type": "delta", "text": "想象一条"}
        yield {"type": "delta", "text": "拟合线"}
        yield {"type": "done", "turns": 1, "ms": 900, "costUsd": 0.002}

    monkeypatch.setattr(ai, "ask_stream", fake_stream)
    monkeypatch.setattr(ai, "ask_status", lambda: {"ready": True, "mode": "pat"})
    r = client.post(
        "/api/ask",
        json={"key": "linreg", "section": {"kind": "formula"}, "question": "这个式子怎么读？"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    frames = [line[5:] for line in r.text.splitlines() if line.startswith("data: ")]
    events = [json.loads(f) for f in frames]
    assert [e["type"] for e in events] == ["delta", "delta", "done"]
    assert events[0]["text"] + events[1]["text"] == "想象一条拟合线"
    assert events[2]["costUsd"] == 0.002


def test_ask_error_event_survives_as_a_frame(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(prompt: str) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "error", "message": "模型返回错误：rate_limit"}

    monkeypatch.setattr(ai, "ask_stream", broken)
    monkeypatch.setattr(ai, "ask_status", lambda: {"ready": True, "mode": "pat"})
    r = client.post(
        "/api/ask",
        json={"key": "knn", "section": {"kind": "story"}, "question": "K 怎么选？"},
    )
    assert json.loads(r.text.splitlines()[0][5:])["message"] == "模型返回错误：rate_limit"


# ------------------------------------------------------------- SDK 适配层 ----


def test_delta_text_only_accepts_text_deltas() -> None:
    assert ai._delta_text({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "a"}}) == "a"
    assert ai._delta_text({"type": "content_block_delta", "delta": {"type": "thinking_delta", "text": "a"}}) == ""
    assert ai._delta_text({"type": "message_start"}) == ""
    assert ai._delta_text(None) == ""


def test_cli_probe_reads_both_output_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    monkeypatch.setattr(ai, "_qodercli_path", lambda: "/bin/echo")

    class Out:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def fake_run_json(cmd: list[str], **kw: Any) -> Out:
        assert kw["check"] is False  # 探测失败要走自己的分支，不能让 ruff 的 check 语义混进来
        return Out('{"version": "1.1.38", "account": "teacherLaoWang"}')

    monkeypatch.setattr(subprocess, "run", fake_run_json)
    assert ai._probe_cli_login() == {"ok": True, "why": "teacherLaoWang"}

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: Out("Version: 1.1.38\nAccount: Not logged in\n"))
    assert ai._probe_cli_login() == {"ok": False, "why": "本机 qodercli 未登录"}

    def boom(cmd: list[str], **kw: Any) -> Out:
        raise OSError("没有权限")

    monkeypatch.setattr(subprocess, "run", boom)
    assert ai._probe_cli_login()["ok"] is False

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: Out("Version: 1.1.38\nAccount: Not logged in\n"))
    assert ai._probe_cli_login() == {"ok": False, "why": "本机 qodercli 未登录"}

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: Out("完全看不懂的东西"))
    assert ai._probe_cli_login()["ok"] is False
