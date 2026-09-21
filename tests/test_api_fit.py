"""HTTP 契约测试：用 TestClient 打真实端点，确认前后端契约（docs/API-CONTRACT.md §1）不掉链子。

注意：教案文字（app/content/lessons/*.py）由另一位作者并行编写，所以这里只断言
「结构字段」齐全，不断言故事/术语等内容字段非空（loader 会用 missingText 报缺哪些）。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.content import catalog
from app.main import app

client = TestClient(app)


def get(path: str) -> Any:
    r = client.get(path)
    assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"
    return r.json()


def test_env():
    env = get("/api/env")
    assert env["python"].startswith("3.1")
    assert isinstance(env["numpy"], str) and env["numpy"][0].isdigit()
    assert set(env["torch"]) == {"available", "version", "device"}
    assert env["torch"]["available"] is True or env["hint"]


def test_catalog_shape():
    cat = get("/api/catalog")
    assert len(cat["families"]) == 6
    assert cat["readyCount"] == len(catalog.READY_KEYS)
    keys = [it["key"] for f in cat["families"] for it in f["items"]]
    assert len(keys) == cat["totalCount"] == len(set(keys))
    lin = next(it for f in cat["families"] for it in f["items"] if it["key"] == "linreg")
    assert lin["status"] == "ready" and lin["difficulty"] == 1


@pytest.mark.parametrize("key", catalog.READY_KEYS)
def test_algorithm_detail(key: str):
    body = get(f"/api/algorithms/{key}")
    assert body["key"] == key and body["status"] == "ready" and body["hasSim"] is True
    assert [p["id"] for p in body["params"]] == [p["id"] for p in catalog.PARAM_SPECS[key]]
    assert [(v["id"], v["kind"]) for v in body["visuals"]] == \
        [(v["id"], v["kind"]) for v in catalog.VISUAL_SPEC[key]]
    assert [m["id"] for m in body["metrics"]] == [m["id"] for m in catalog.METRIC_SPEC[key]]


def test_algorithm_detail_unknown_key_is_404():
    assert client.get("/api/algorithms/不存在的算法").status_code == 404
    assert client.get("/api/algorithms/gmm").status_code == 200  # outline 也有目录卡片
    assert client.get("/api/algorithms/gmm").json()["hasSim"] is False


@pytest.mark.parametrize("key", catalog.READY_KEYS)
def test_fit_returns_all_visuals(key: str):
    r = client.post(f"/api/algorithms/{key}/fit", json={"params": {}, "seed": 7, "steps": 80})
    body = r.json()
    assert r.status_code == 200, body
    assert body["missingVisuals"] == []
    assert body["declaredVisuals"] == [v["id"] for v in catalog.VISUAL_SPEC[key]]
    assert body["key"] == key and body["seed"] == 7 and body["steps"] == 80
    assert body["backend"] in ("numpy", "torch")
    assert body["elapsedMs"] >= 0
    assert set(body["params"]) == {p["id"] for p in catalog.PARAM_SPECS[key]}
    kinds = {v["id"]: v["kind"] for v in catalog.VISUAL_SPEC[key]}
    assert [(v["id"], v["kind"]) for v in body["visuals"]] == list(kinds.items())


def test_fit_uses_param_defaults_and_clamps():
    r = client.post("/api/algorithms/linreg/fit",
                    json={"params": {"lr": 99, "noise": -5}, "seed": 1, "steps": 10})
    body = r.json()
    spec = {p["id"]: p for p in catalog.PARAM_SPECS["linreg"]}
    assert body["params"]["lr"] == spec["lr"]["max"]
    assert body["params"]["noise"] == spec["noise"]["min"]
    assert body["missingVisuals"] == []
    # steps 上限 400
    r2 = client.post("/api/algorithms/linreg/fit", json={"params": {}, "steps": 99999})
    assert r2.json()["steps"] == 400


def test_fit_illegal_params_is_400():
    for bad in ({"lr": "abc"}, {"lr": None}, {"spread": {}}):
        r = client.post("/api/algorithms/linreg/fit", json={"params": bad, "seed": 7})
        assert r.status_code == 400, r.text[:200]
        assert "参数" in r.json()["detail"]


def test_fit_non_finite_param_is_400():
    raw = '{"params": {"lr": NaN}, "seed": 7}'
    r = client.post("/api/algorithms/linreg/fit", content=raw,
                    headers={"content-type": "application/json"})
    assert r.status_code == 400, r.text[:200]


def test_fit_unknown_key_is_404_or_501():
    r = client.post("/api/algorithms/nope/fit", json={"params": {}})
    assert r.status_code in (404, 501), r.status_code
    r2 = client.post("/api/algorithms/gmm/fit", json={"params": {}})  # outline：没仿真
    assert r2.status_code in (404, 501), r2.status_code


def test_step_endpoint_resumes():
    r = client.post("/api/algorithms/kmeans/step", json={"params": {"k": 3}, "seed": 5, "steps": 12})
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["resumed"] is True
    assert body["missingVisuals"] == []
    assert body["steps"] == 12


def test_fit_is_deterministic_over_http():
    a = client.post("/api/algorithms/pca/fit", json={"params": {"tilt": 45}, "seed": 3}).json()
    b = client.post("/api/algorithms/pca/fit", json={"params": {"tilt": 45}, "seed": 3}).json()
    assert a["metrics"] == b["metrics"]
    assert a["visuals"] == b["visuals"]


def test_summary_reports_missing_lesson_text_only_as_data():
    body = get("/api/summary")
    assert body["ready"] == len(catalog.READY_KEYS)
    assert isinstance(body["incompleteLessons"], list)
