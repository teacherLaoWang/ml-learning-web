"""内容一致性测试：目录、教案字段、参数 id、交叉引用都不能飘。"""

from __future__ import annotations

import pytest

from app.content import catalog, loader

ALL_KEYS = [it["key"] for fam in catalog.FAMILIES for it in fam["items"]]


def test_no_duplicate_keys() -> None:
    assert len(ALL_KEYS) == len(set(ALL_KEYS)), "目录里有重复的算法 key"


def test_ready_keys_have_all_specs() -> None:
    ready = [it["key"] for fam in catalog.FAMILIES for it in fam["items"] if it["status"] == "ready"]
    assert sorted(ready) == catalog.READY_KEYS
    for key in ready:
        assert key in catalog.VISUAL_SPEC, f"{key} 缺 VISUAL_SPEC"
        assert key in catalog.METRIC_SPEC, f"{key} 缺 METRIC_SPEC"
        assert catalog.VISUAL_SPEC[key], f"{key} 至少要有一个可视化"


def test_every_catalog_key_resolves() -> None:
    for key in ALL_KEYS:
        p = loader.payload(key)
        assert p["name"], key
        assert p["tagline"], f"{key} 缺 tagline"
        assert p["story"], f"{key} 缺 story"
        assert p["intuition"], f"{key} 缺 intuition"
        assert p["terms"], f"{key} 缺 terms"


def test_ready_lessons_are_complete() -> None:
    for key in catalog.READY_KEYS:
        p = loader.payload(key)
        assert not p.get("contentError"), f"{key}: {p.get('contentError')}"
        assert not p.get("missingText"), f"{key} 缺内容字段 {p['missingText']}"
        assert len(p["derivation"]) >= 4, f"{key} 推导步骤太少"
        assert len(p["terms"]) >= 7, f"{key} 术语太少"
        assert len(p["pitfalls"]) >= 4, f"{key} 常见坑太少"
        assert p["formula"]["text"], f"{key} 缺公式"
        assert p["formula"]["vars"], f"{key} 公式没有变量释义"
        assert p["quiz"] and 0 <= p["quiz"]["answer"] < len(p["quiz"]["options"]), key
        assert len(p["presets"]) >= 2, f"{key} 预设太少"


def test_param_ids_are_unique_and_well_formed() -> None:
    for key, specs in catalog.PARAM_SPECS.items():
        ids = [p["id"] for p in specs]
        assert len(ids) == len(set(ids)), f"{key} 参数 id 重复"
        for p in specs:
            assert p["min"] < p["max"], f"{key}.{p['id']} 范围反了"
            assert p["min"] <= p["default"] <= p["max"], f"{key}.{p['id']} 默认值越界"
            assert p.get("label"), f"{key}.{p['id']} 缺中文标签"


def test_presets_only_use_known_params() -> None:
    for key in catalog.READY_KEYS:
        valid = {p["id"] for p in catalog.PARAM_SPECS[key]}
        for preset in loader.payload(key)["presets"]:
            for pid in preset["params"]:
                assert pid in valid, f"{key} 预设 {preset['id']} 用了不存在的参数 {pid}"


def test_cross_references_point_to_real_keys() -> None:
    valid = set(ALL_KEYS)
    for key in ALL_KEYS:
        for ref in loader.payload(key)["seeAlso"]:
            assert ref in valid, f"{key} 的 seeAlso 指向不存在的 {ref}"
            assert ref != key, f"{key} 引用了自己"


def test_visual_ids_unique_per_algorithm() -> None:
    for key, specs in catalog.VISUAL_SPEC.items():
        ids = [s["id"] for s in specs]
        assert len(ids) == len(set(ids)), f"{key} visual id 重复"
        assert all(s["kind"] in {"surface3d", "cloud3d", "vector3d", "line2d", "bars", "matrix", "tree2d"}
                   for s in specs), f"{key} 有未知 kind"
        assert all(s.get("title") for s in specs), f"{key} visual 缺标题"


def test_catalog_payload_shape() -> None:
    cat = catalog.catalog_payload()
    assert cat["readyCount"] == 10
    assert cat["totalCount"] == len(ALL_KEYS) >= 30
    assert len(cat["families"]) == 6
    for fam in cat["families"]:
        assert fam["items"], fam["key"]
        for it in fam["items"]:
            assert it["status"] in {"ready", "outline"}


@pytest.mark.parametrize("key", catalog.READY_KEYS)
def test_glossary_covers_key(key: str) -> None:
    rows = loader.glossary()
    assert any(key in r["keys"] for r in rows), f"{key} 的术语没进速查表"


def test_mlp_worked_example_numbers_are_reproducible() -> None:
    """MLP 教案里的 2-2-1 手算例子必须能真算出来，防止文字与算术飘走。"""
    from math import exp

    sig = lambda t: 1 / (1 + exp(-t))
    x1, x2, y = 1.0, 0.5, 1.0
    w11, w21, b1 = 0.8, 0.6, 0.3
    w12, w22, b2 = 0.4, 0.9, -0.2
    v1, v2, b3 = 0.7, 0.5, 0.1
    z1 = w11 * x1 + w21 * x2 + b1
    h1 = sig(z1)
    z2 = w12 * x1 + w22 * x2 + b2
    h2 = sig(z2)
    z = v1 * h1 + v2 * h2 + b3
    o = sig(z)
    loss = (o - y) ** 2
    d3 = 2 * (o - y) * o * (1 - o)
    d1 = d3 * v1 * h1 * (1 - h1)

    text = "\n".join(str(v) for v in loader.payload("mlp").values())
    for shown in ["1.40", "0.802", "0.657", "0.990", "0.729", "0.0734", "−0.107", "−0.0119"]:
        assert shown in text, f"MLP 教案里应当出现的算例数字 {shown} 不见了"
    assert round(z1, 2) == 1.40 and round(h1, 3) == 0.802
    assert round(h2, 3) == 0.657 and round(o, 3) == 0.729
    assert round(loss, 4) == 0.0734
    assert round(d3, 3) == -0.107 and round(d1, 4) == -0.0119
