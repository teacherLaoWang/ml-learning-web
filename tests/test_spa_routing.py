"""单端口托管行为回归：hash 路由 + 相对资源路径的组合曾经把深链打成白屏。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import DIST, app

client = TestClient(app)
pytestmark = pytest.mark.skipif(not DIST.is_dir(), reason="还没 npm run build，跳过静态托管检查")


def test_root_serves_index() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'id="app"' in r.text
    # index.html 不能被缓存，否则重新构建后浏览器会去要旧哈希的分片
    assert "no-store" in r.headers.get("cache-control", "")


def test_built_index_references_relative_assets_only() -> None:
    html = (DIST / "index.html").read_text(encoding="utf-8")
    assert 'src="/' not in html, "index.html 里出现根绝对路径，换端口/子目录会挂"
    assert "cdn." not in html and "unpkg" not in html and "jsdelivr" not in html, "不允许外链 CDN"


@pytest.mark.parametrize("deep", ["/algo/mlp", "/catalog", "/glossary", "/nope"])
def test_deep_links_redirect_to_root(deep: str) -> None:
    r = client.get(deep, follow_redirects=False)
    assert r.status_code == 307, f"{deep} 应该回根路径（前端用 hash 路由）"
    assert r.headers["location"] == "/"


def test_missing_asset_is_json_404_not_html() -> None:
    r = client.get("/assets/definitely-missing.js")
    assert r.status_code == 404
    assert "json" in r.headers["content-type"], "静态资源缺失若返回 HTML，浏览器会报 MIME 错误"


def test_real_bundle_is_served() -> None:
    bundles = sorted((DIST / "assets").glob("index-*.js"))
    assert bundles, "dist/assets 里没有 index-*.js，先 npm run build"
    r = client.get(f"/assets/{bundles[0].name}")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
