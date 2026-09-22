"""离线 fixture 与后端真实输出的结构一致性。

fixture 由 `uv run python -m tools.make_fixtures` 从后端当前实现生成。
谁改了 app/ml/* 的返回结构却没重新生成 fixture，这里就会红。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from app.content import catalog
from app.ml import registry

FIX = Path(__file__).resolve().parent.parent / "frontend" / "src" / "fixtures"
D = {k: {p["id"]: p["default"] for p in catalog.PARAM_SPECS[k]} for k in catalog.READY_KEYS}


def _fixture(key: str) -> dict[str, Any]:
    path = FIX / f"{key}.json"
    assert path.is_file(), f"缺少 {path}，跑一次 uv run python -m tools.make_fixtures"
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(obj: Any, path: str = "$", bad: list[str] | None = None) -> list[str]:
    bad = bad if bad is not None else []
    if isinstance(obj, dict):
        for k, v in obj.items():
            _finite(v, f"{path}.{k}", bad)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _finite(v, f"{path}[{i}]", bad)
    elif isinstance(obj, float) and not math.isfinite(obj):
        bad.append(path)
    return bad


@pytest.mark.parametrize("key", catalog.READY_KEYS)
def test_fixture_matches_live_shape(key: str) -> None:
    fx = _fixture(key)
    live = registry.run(key, D[key], seed=7, steps=150)

    assert fx["mock"] is True, "fixture 必须标记 mock，前端要据此显示离线徽章"
    assert fx["key"] == key
    assert [(v["id"], v["kind"]) for v in fx["visuals"]] == [(v["id"], v["kind"]) for v in live["visuals"]], \
        f"{key} 的 visual id/kind 与后端不一致，请重新生成 fixture"
    assert sorted(fx["metrics"]) == sorted(live["metrics"]), f"{key} metrics 键漂移"
    assert sorted(s["id"] for s in fx["series"]) == sorted(s["id"] for s in live["series"]), f"{key} series 漂移"
    assert sorted(t["id"] for t in fx["table"]) == sorted(t["id"] for t in live["table"]), f"{key} table 漂移"

    fvid = {v["id"]: v.get("data") or {} for v in fx["visuals"]}
    lvid = {v["id"]: v.get("data") or {} for v in live["visuals"]}
    for vid, data in fvid.items():
        assert set(data) == set(lvid[vid]), f"{key}/{vid} 字段漂移：fixture {sorted(set(data) ^ set(lvid[vid]))}"
        grid = data.get("grid") or (data.get("boundary") or {}).get("grid")
        if isinstance(grid, dict):
            assert len(grid["z"]) == len(grid["y"]), f"{key}/{vid} grid.z 行数应等于 len(y)"
            assert all(len(row) == len(grid["x"]) for row in grid["z"]), f"{key}/{vid} grid.z 列数应等于 len(x)"
    assert not _finite(fx), f"{key} fixture 里有非有限数值"


def test_meta_files_shape() -> None:
    meta = FIX / "_meta"
    catalog_json = json.loads((meta / "catalog.json").read_text(encoding="utf-8"))
    specs = json.loads((meta / "specs.json").read_text(encoding="utf-8"))
    lessons = json.loads((meta / "lessons.json").read_text(encoding="utf-8"))
    concepts = json.loads((meta / "concepts.json").read_text(encoding="utf-8"))

    assert set(catalog_json) == {"env", "families"}
    assert set(specs) == {"paramSpecs", "visualSpecs", "metricSpecs"}
    assert sorted(specs["paramSpecs"]) == catalog.READY_KEYS
    assert sorted(lessons) == catalog.READY_KEYS
    for key, lesson in lessons.items():
        assert lesson.get("terms"), f"{key} 教案没有术语"
        assert lesson.get("derivation"), f"{key} 教案没有推导"
    assert catalog_json["env"]["torch"]["available"] is False or "hint" in catalog_json["env"]

    # 离线模式下的概念卡片：每个 outline 条目都要有内容可渲染
    outline_keys = {it["key"] for f in catalog.FAMILIES for it in f["items"] if it["status"] == "outline"}
    assert set(concepts) == outline_keys, "concepts.json 必须正好覆盖所有 outline 条目"
    for key in outline_keys:
        c = concepts[key]
        assert c.get("story"), f"{key} 概念卡片没有正文"
        assert c.get("terms"), f"{key} 概念卡片没有术语"
        assert c.get("intuition"), f"{key} 概念卡片没有直觉段落"
    for f in catalog_json["families"]:
        for it in f["items"]:
            assert "concept" not in it, "概念文字应留在 concepts.json，别把 /api/catalog 撑大"


def test_fixture_size_budget() -> None:
    """fixture 是懒加载的，但仍然不该无限膨胀。"""
    total = sum((FIX / f"{k}.json").stat().st_size for k in catalog.READY_KEYS)
    assert total < 900_000, f"fixture 合计 {total/1024:.0f}KB，重新生成时记得降采样"
