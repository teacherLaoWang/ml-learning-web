"""教案装载：app/content/lessons/{key}.py 各自暴露一个 LESSON 字典。

结构约定见 docs/API-CONTRACT.md §1「GET /api/algorithms/{key}」。
机读部分（参数范围、visual 列表）来自 catalog.py，文字部分来自 lessons/。
"""

from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache
from typing import Any

from app.content import catalog
from app.content.tex import TexError, to_latex_display

_PKG = "app.content.lessons"

REQUIRED_TEXT = ("name", "tagline", "story", "intuition", "derivation", "terms")


@lru_cache(maxsize=512)
def _tex(text: str) -> str:
    """教案原文是 Unicode，转录成 LaTeX；转不动就返回空串让前端回退。"""
    try:
        return to_latex_display(text) if text and text.strip() else ""
    except TexError:
        return ""

def _latexify(obj: dict[str, Any]) -> dict[str, Any]:
    """给公式卡补 latex：作者手写的优先，程序转录的兜底。"""
    out = dict(obj)
    text = str(out.get("text") or "")
    out["latex"] = str(out.get("latex") or "") or _tex(text)
    out["vars"] = [
        {**v, "latex": str(v.get("latex") or "") or _tex(str(v.get("sym") or ""))}
        for v in out.get("vars") or []
    ]
    return out


def _latexify_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for step in steps:
        d = dict(step)
        if d.get("formula"):
            d["latex"] = str(d.get("latex") or "") or _tex(str(d["formula"]))
        out.append(d)
    return out


@lru_cache(maxsize=1)
def _lessons() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    try:
        pkg = importlib.import_module(_PKG)
    except ModuleNotFoundError:
        return out
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name not in catalog.PARAM_SPECS:  # 只认识目录里 ready 的 key
            continue
        try:
            lesson = getattr(importlib.import_module(f"{_PKG}.{mod.name}"), "LESSON", None)
        except Exception as exc:  # 单篇写坏不应该拖垮整站
            lesson = {"_loadError": f"{type(exc).__name__}: {exc}"}
        if isinstance(lesson, dict):
            out[mod.name] = lesson
    return out


def lesson_keys() -> list[str]:
    return sorted(_lessons())


def _outline() -> dict[str, dict[str, Any]]:
    try:
        from app.content.outline import OUTLINE  # 概念卡片（无仿真）
    except Exception:
        return {}
    return OUTLINE if isinstance(OUTLINE, dict) else {}


def payload(key: str) -> dict[str, Any]:
    """把目录规格 + 文字内容合成一份完整教案（ready 走 lessons/，outline 走 outline.py）。"""
    item = catalog.find_item(key)
    if item is None:
        raise KeyError(key)
    ready = key in catalog.PARAM_SPECS
    lesson = _lessons().get(key, {}) if ready else _outline().get(key, {})
    visuals = catalog.VISUAL_SPEC.get(key, [])
    data = {
        "key": key,
        "name": lesson.get("name", item["name"]),
        "family": item["family"],
        "familyName": item["familyName"],
        "color": item["color"],
        "status": item["status"],
        "difficulty": item["difficulty"],
        "tags": item["tags"],
        "tagline": lesson.get("tagline", ""),
        "story": lesson.get("story", ""),
        "formula": _latexify(lesson.get("formula", {"text": "", "vars": []})),
        "intuition": lesson.get("intuition", []),
        "derivation": _latexify_steps(lesson.get("derivation", [])),
        "terms": lesson.get("terms", []),
        "pitfalls": lesson.get("pitfalls", []),
        "seeAlso": lesson.get("seeAlso", []),
        "quiz": lesson.get("quiz"),
        "simHint": lesson.get("simHint", ""),
        "params": catalog.PARAM_SPECS.get(key, []),
        "presets": lesson.get("presets", []),
        "metrics": catalog.METRIC_SPEC.get(key, []),
        "visuals": visuals,
        "hasSim": ready,
    }
    if "_loadError" in lesson:
        data["contentError"] = lesson["_loadError"]
    needed = list(REQUIRED_TEXT) if ready else [t for t in REQUIRED_TEXT if t != "derivation"]
    missing = [t for t in needed if not data[t]]
    if missing:
        data["missingText"] = missing
    return data


def all_payloads() -> list[dict[str, Any]]:
    return [payload(k) for k in sorted(catalog.PARAM_SPECS)]


def glossary() -> list[dict[str, Any]]:
    """把各篇术语汇总成一张速查表（含概念卡片）。"""
    rows: dict[str, dict[str, Any]] = {}
    keys = sorted(catalog.PARAM_SPECS) + sorted(_outline())
    for key in keys:
        p = payload(key)
        for t in p["terms"]:
            term = t.get("term", "")
            if not term:
                continue
            rows.setdefault(term, {**t, "keys": []})
            if key not in rows[term]["keys"]:
                rows[term]["keys"].append(key)
    return sorted(rows.values(), key=lambda r: r["term"].lower())
