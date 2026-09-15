"""Contract tests use mock ADR; no physical device is contacted."""
import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from adr_gateway.app import create_app
from adr_gateway.config import Settings


def reply(**fields):
    return dict(success=True, requestId=str(uuid4()), stage="completed", message="完成", **fields)


def setup(tmp_path, handler):
    settings = Settings(storage_root=tmp_path / "results")
    app = create_app(settings, transport=httpx.MockTransport(handler))
    return app, settings


def test_existing_weldos_flow(tmp_path):
    calls = []
    responses = []
    def adr(request):
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        if request.url.path.endswith("/capture"):
            path = Path(body["savePath"])
            assert path.parent.is_dir()
            path.write_bytes(b"tiff fixture")
            path.with_suffix(".xml").write_text("<annotation/>")
            path.with_name(path.stem + "_ai.xml").write_text("<annotation/>")
            payload = reply(saved=True, savedFilePath=str(path))
        else:
            payload = reply(enabled=body["enabled"])
        responses.append(payload)
        return httpx.Response(200, json=payload)
    app, settings = setup(tmp_path, adr)
    name = "RT-existing-weldos-run.tif"
    with TestClient(app) as client:
        assert client.post("/api/v1/xray/high-voltage", json={"enabled": True}).json() == responses[-1]
        body = dict(framePeriodSeconds=1.0, integrationCount=10,
                    savePath=str(settings.storage_root / name),
                    overwriteExisting=False, generateMockDefect=True)
        result = client.post("/api/v1/capture", json=body)
        assert {k: v for k, v in result.json().items() if k != 'downloads'} == responses[-1]
        for kind, content in [('film', b'tiff fixture'), ('ai', b'<annotation/>'), ('humanReview', b'<annotation/>')]:
            item = result.json()['downloads'][kind]
            downloaded = client.get(item['url'])
            assert downloaded.status_code == 200
            assert downloaded.content == content
            assert item['sizeBytes'] == len(content)
            assert 'attachment' in downloaded.headers['content-disposition']
        assert result.json()["savedFilePath"] == body["savePath"]
        assert calls[-1][1] == body
        assert client.post("/api/v1/xray/high-voltage", json={"enabled": False}).json() == responses[-1]
    assert len(list(settings.storage_root.iterdir())) == 3
    assert [p for p, _ in calls] == ["/api/v1/xray/high-voltage", "/api/v1/capture", "/api/v1/xray/high-voltage"]


def test_fixed_directory_and_generated_names(tmp_path):
    saved = []
    def adr(request):
        body = json.loads(request.content)
        saved.append(body["savePath"])
        return httpx.Response(200, json=reply(saved=bool(body['savePath']), savedFilePath=body["savePath"]))
    app, settings = setup(tmp_path, adr)
    with TestClient(app) as client:
        for extra in ({"savePath": "D:/untrusted/elsewhere/name.tif"}, {}, {}):
            assert client.post("/api/v1/capture", json=dict(framePeriodSeconds=1, integrationCount=1, **extra)).status_code == 200
        assert all(Path(p).parent == settings.storage_root for p in saved)
        assert Path(saved[0]).name == "name.tif"
        assert len(set(saved)) == 3
        client.post("/api/v1/capture", json={"savePath": ""})
        assert saved[-1] == ""


@pytest.mark.parametrize("status,code", [(400, "MISSING_PARAMETER"), (409, "CAPTURE_BUSY"), (503, "AI_SERVICE_UNAVAILABLE")])
def test_upstream_errors_unchanged(tmp_path, status, code):
    payload = dict(success=False, requestId=str(uuid4()), stage="precheck",
                   errorCode=code, message="失败", saved=False, savedFilePath="")
    app, _ = setup(tmp_path, lambda request: httpx.Response(status, json=payload))
    with TestClient(app) as client:
        response = client.post("/api/v1/capture", json={})
    assert response.status_code == status
    assert response.json() == payload


def test_only_documented_routes_and_bad_input(tmp_path):
    def unexpected(request):
        pytest.fail("Invalid local request must not reach ADR")
    app, _ = setup(tmp_path, unexpected)
    assert set(app.openapi()["paths"]) == {"/api/v1/capture", "/api/v1/xray/high-voltage", "/api/v1/files/{filename}"}
    with TestClient(app) as client:
        for path in ("/api/v1/health", "/api/v1/tasks", "/docs", "/openapi.json"):
            assert client.get(path).status_code == 404
        for body in ({"savePath": None}, {"savePath": "name.exe"}, {"savePath": "C:/x/NUL.tif"}):
            assert client.post("/api/v1/capture", json=body).status_code == 400
        assert client.post("/api/v1/capture", content="{").status_code == 400


@pytest.mark.parametrize("kind,status", [("timeout", 504), ("connection", 502), ("invalid", 502)])
def test_gateway_errors(tmp_path, kind, status):
    def adr(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if kind == "connection":
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, text="not json")
    app, _ = setup(tmp_path, adr)
    with TestClient(app) as client:
        response = client.post("/api/v1/capture", json={})
    assert response.status_code == status
    payload = response.json()
    assert payload["success"] is False and payload["saved"] is False
    assert payload["requestId"] and payload["stage"] == "gateway"


def test_capture_does_not_block_shutdown_or_mask_busy(tmp_path):
    async def scenario():
        entered, finish = asyncio.Event(), asyncio.Event()
        async def adr(request):
            if request.url.path.endswith("/capture"):
                if entered.is_set():
                    return httpx.Response(409, json={"success": False, "errorCode": "CAPTURE_BUSY"})
                entered.set()
                await finish.wait()
                return httpx.Response(200, json=reply(saved=False, savedFilePath=""))
            assert json.loads(request.content) == {"enabled": False}
            return httpx.Response(200, json=reply(enabled=False))
        app, _ = setup(tmp_path, adr)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            pending = asyncio.create_task(client.post("/api/v1/capture", json={}))
            try:
                await asyncio.wait_for(entered.wait(), 2)
                busy = await client.post("/api/v1/capture", json={})
                assert busy.status_code == 409
                off = await asyncio.wait_for(client.post("/api/v1/xray/high-voltage", json={"enabled": False}), 2)
                assert off.json()["enabled"] is False
                assert not pending.done()
            finally:
                finish.set()
                await pending
    asyncio.run(scenario())


def test_film_only_and_no_save_downloads(tmp_path):
    def adr(request):
        body = json.loads(request.content)
        if body['savePath']:
            Path(body['savePath']).write_bytes(b'film only')
        return httpx.Response(200, json=reply(saved=bool(body['savePath']), savedFilePath=body['savePath']))
    app, _ = setup(tmp_path, adr)
    with TestClient(app) as client:
        response = client.post('/api/v1/capture', json={'savePath': '中文 底片.tif'})
        downloads = response.json()['downloads']
        assert downloads['ai'] is None and downloads['humanReview'] is None
        assert client.get(downloads['film']['url']).content == b'film only'
        response = client.post('/api/v1/capture', json={'savePath': ''})
        assert response.json()['downloads'] == dict(film=None, ai=None, humanReview=None)


def test_download_rejects_outside_paths_and_non_artifacts(tmp_path, monkeypatch):
    app, settings = setup(tmp_path, lambda request: pytest.fail('Download must not call ADR'))
    settings.storage_root.mkdir()
    (tmp_path / 'outside.xml').write_text('secret')
    (settings.storage_root / 'config.env').write_text('secret')
    with TestClient(app) as client:
        for name in ('missing.tif', 'config.env', '..%5Coutside.xml', '..%2Foutside.xml',
                     'C%3Aoutside.xml', 'film.tif%3Asecret.xml'):
            assert client.get('/api/v1/files/' + name).status_code == 404
        # A link is rejected even if its visible filename has an allowed extension.
        (settings.storage_root / 'link.xml').write_text('secret')
        monkeypatch.setattr(Path, 'is_symlink', lambda self: self.name == 'link.xml')
        assert client.get('/api/v1/files/link.xml').status_code == 404


def test_download_returns_current_review_without_changing_ai(tmp_path):
    app, settings = setup(tmp_path, lambda request: pytest.fail('Download must not call ADR'))
    settings.storage_root.mkdir()
    review = settings.storage_root / 'film.xml'
    review.write_bytes(b'original')
    (settings.storage_root / 'film_ai.xml').write_bytes(b'ai')
    with TestClient(app) as client:
        assert client.get('/api/v1/files/film.xml').content == b'original'
        review.write_bytes(b'reviewed')
        assert client.get('/api/v1/files/film.xml').content == b'reviewed'
        assert client.get('/api/v1/files/film_ai.xml').content == b'ai'


def test_container_to_windows_path_mapping(tmp_path):
    settings = Settings(storage_root=tmp_path, adr_save_root='D:/ADR_Data')
    def adr(request):
        body = json.loads(request.content)
        assert body['savePath'].replace('\\', '/') == 'D:/ADR_Data/film.tif'
        (tmp_path/'film.tif').write_bytes(b'film')
        return httpx.Response(200, json=reply(saved=True, savedFilePath=body['savePath']))
    with TestClient(create_app(settings, transport=httpx.MockTransport(adr))) as client:
        response = client.post('/api/v1/capture', json={'savePath': 'film.tif'})
        assert response.status_code == 200
        assert client.get(response.json()['downloads']['film']['url']).content == b'film'


def test_environment_overrides_toml(tmp_path, monkeypatch):
    from adr_gateway.config import load_settings
    config = tmp_path/'settings.toml'
    config.write_text('port = 1234')
    monkeypatch.setenv('RT_GATEWAY_CONFIG', str(config))
    monkeypatch.setenv('RT_GATEWAY_PORT', '18081')
    monkeypatch.setenv('RT_GATEWAY_ADR_SAVE_ROOT', 'D:/ADR_Data')
    settings = load_settings()
    assert settings.port == 18081 and settings.adr_save_root == 'D:/ADR_Data'
