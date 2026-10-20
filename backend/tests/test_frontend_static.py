"""빌드된 화면 정적 서빙 — SPA 폴백이 /api·/health를 가리지 않는지가 핵심이다."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.frontend import add_frontend
from app.api.routes import router
from app.core.config import Settings, get_settings

SECRET_TEXT = "outside-dist-secret"


@pytest.fixture
def client(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<!doctype html><div id="root"></div>', encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text(SECRET_TEXT, encoding="utf-8")

    app = FastAPI()
    app.include_router(router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    add_frontend(app, dist)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, jwt_secret="x" * 32)
    return TestClient(app)


def test_root_serves_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert 'id="root"' in r.text
    assert "no-cache" in r.headers["cache-control"]


def test_client_route_falls_back_to_index(client):
    r = client.get("/history/3")
    assert r.status_code == 200
    assert 'id="root"' in r.text


def test_asset_served(client):
    r = client.get("/assets/app.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert "console.log('app')" in r.text


def test_root_file_served(client):
    r = client.get("/favicon.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg")


def test_unknown_api_path_is_json_404(client):
    r = client.get("/api/asks")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {"detail": "Not Found"}


def test_api_and_health_not_shadowed(client):
    r = client.post("/api/ask", json={"question": "q"})
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/json")
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/..%2f..%2fsecret.txt", "/../secret.txt", "/assets/..%2f..%2f..%2fsecret.txt"])
def test_path_traversal_does_not_escape_dist(client, path):
    r = client.get(path)
    assert SECRET_TEXT not in r.text


def test_openapi_has_no_frontend_routes(client):
    paths = client.app.openapi()["paths"]
    assert all(p.startswith(("/api/", "/health")) for p in paths)


def test_default_dist_dir_is_repo_frontend_regardless_of_cwd():
    # uvicorn은 backend/에서, pytest는 저장소 루트에서 돈다 — 상대 경로면 한쪽에서 화면이 조용히 빠진다
    repo = Path(__file__).resolve().parents[2]
    assert Settings(_env_file=None).frontend_dist_dir == repo / "frontend" / "dist"
