from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.main import create_app


async def test_health(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_security_headers(client):
    response = await client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in response.headers["content-security-policy"]


async def test_system_info(client):
    response = await client.get("/api/system")
    assert response.status_code == 200
    body = response.json()
    assert "ytdlp" in body
    assert body["dirs"]["library"]


async def test_rejects_non_http_url(client):
    response = await client.post("/api/jobs", json={"url": "file:///etc/passwd"})
    assert response.status_code == 400


async def test_job_lifecycle(client):
    created = await client.post("/api/jobs", json={"url": "https://example.com/watch?v=1"})
    assert created.status_code == 201
    job = created.json()
    assert job["status"] == "queued"

    listing = await client.get("/api/jobs")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["id"] == job["id"]

    canceled = await client.post(f"/api/jobs/{job['id']}/cancel")
    assert canceled.status_code == 200

    deleted = await client.delete(f"/api/jobs/{job['id']}")
    assert deleted.status_code == 200
    assert (await client.get(f"/api/jobs/{job['id']}")).status_code == 404


async def test_library_scan_is_empty(client):
    response = await client.post("/api/library/scan")
    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_library_search(client):
    response = await client.get("/api/library", params={"q": "nothing"})
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_rename_preview_rejects_bad_template(client):
    response = await client.post(
        "/api/library/rename/preview",
        json={"ids": ["nope"], "template": "{bogus}"},
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.fixture
def token_app(tmp_path):
    cfg = Settings(
        data_dir=tmp_path,
        download_dir=tmp_path / "downloads",
        library_dir=tmp_path / "library",
        config_dir=tmp_path / "config",
        static_dir=tmp_path / "static",
        app_password="s3cret",
    ).normalize()
    cfg.ensure_dirs()
    return create_app(cfg)


async def test_auth_flow(token_app):
    transport = httpx.ASGITransport(app=token_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Requested-With": "ytdlweb"}
    ) as client:
        assert (await client.get("/api/jobs")).status_code == 401
        assert (await client.get("/api/health")).status_code == 200

        bad = await client.post("/api/auth/login", json={"password": "wrong"})
        assert bad.status_code == 401

        good = await client.post("/api/auth/login", json={"password": "s3cret"})
        assert good.status_code == 200
        assert client.cookies.get("ytdlweb_session") == "s3cret"

        assert (await client.get("/api/jobs")).status_code == 200

        # CSRF guard: state-changing call without the custom header is refused.
        raw = await client.post(
            "/api/jobs",
            json={"url": "https://example.com/x"},
            headers={"X-Requested-With": ""},
        )
        assert raw.status_code == 403


async def test_write_guard(tmp_path):
    cfg = Settings(
        data_dir=tmp_path,
        download_dir=tmp_path / "downloads",
        library_dir=tmp_path / "library",
        config_dir=tmp_path / "config",
        static_dir=tmp_path / "static",
        allow_write=False,
    ).normalize()
    cfg.ensure_dirs()
    app = create_app(cfg)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Requested-With": "ytdlweb"}
    ) as client:
        response = await client.post(
            "/api/library/rename/apply", json={"ids": ["x"], "template": "{title}"}
        )
        assert response.status_code == 403


async def test_duplicate_url_requires_force(client, app):
    created = await client.post("/api/jobs", json={"url": "https://example.com/v/dup"})
    job = created.json()
    app.state.db.update_job(job["id"], status="done", outpath="/downloads/x.mp3", title="X")

    again = await client.post("/api/jobs", json={"url": "https://example.com/v/dup"})
    assert again.status_code == 409
    detail = again.json()["detail"]
    assert detail["existing"]["id"] == job["id"]
    assert "force" in detail["message"]

    forced = await client.post(
        "/api/jobs", json={"url": "https://example.com/v/dup", "preset": {"force": True}}
    )
    assert forced.status_code == 201


async def test_retry_sets_force(client, app):
    created = await client.post("/api/jobs", json={"url": "https://example.com/v/retry"})
    job = created.json()
    app.state.db.update_job(job["id"], status="done")

    retried = await client.post(f"/api/jobs/{job['id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["preset"]["force"] is True


async def test_prefs_roundtrip(client):
    initial = await client.get("/api/prefs")
    assert initial.status_code == 200
    assert initial.json()["default_preset"]["mode"] == "video"

    saved = await client.put(
        "/api/prefs",
        json={
            "default_preset": {"mode": "audio", "audio_format": "opus", "quality": "720"},
            "default_template": "{artist}/{title}",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["default_preset"]["mode"] == "audio"
    assert saved.json()["default_preset"]["audio_format"] == "opus"

    reread = await client.get("/api/prefs")
    assert reread.json()["default_preset"]["audio_format"] == "opus"
    assert reread.json()["default_template"] == "{artist}/{title}"


async def test_prefs_rejects_bad_template(client):
    response = await client.put(
        "/api/prefs", json={"default_preset": {}, "default_template": "{nope}"}
    )
    assert response.status_code == 400
