"""ADR-compatible operations and downloads of their saved artifacts."""
import json
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from .files import capture_downloads, capture_path, download_file, upstream_path

router = APIRouter(prefix="/api/v1")


def failure(path, status, code, message):
    payload = dict(success=False, requestId=str(uuid4()), stage="parameter_validation",
                   errorCode=code, message=message)
    if path == "/capture":
        payload.update(saved=False, savedFilePath="")
    else:
        payload.update(stage="xray_control", enabled=False)
    if status >= 500:
        payload["stage"] = "gateway"
    return JSONResponse(payload, status_code=status)


async def forward(request: Request, path: str):
    local_path = None
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError):
        return failure(path, 400, "INVALID_JSON", "请求体不是合法 JSON")
    if not isinstance(body, dict):
        return failure(path, 400, "INVALID_JSON", "请求体必须是 JSON 对象")
    if path == "/capture":
        supplied = body.get("savePath")
        if "savePath" in body and not isinstance(supplied, str):
            return failure(path, 400, "INVALID_PARAMETER", "savePath 字段必须是 string")
        # Explicit empty string retains ADR's documented 'do not save' behavior.
        if supplied != "":
            try:
                settings = request.app.state.settings
                local_path = capture_path(settings.storage_root, supplied)
                body["savePath"] = upstream_path(local_path, settings.adr_save_root)
            except ValueError as exc:
                return failure(path, 400, "INVALID_SAVE_PATH", str(exc))
            except OSError:
                return failure(path, 500, "SAVE_FAILED", "无法创建或访问配置的保存目录")
    try:
        upstream = await request.app.state.adr.call(path, body)
    except httpx.TimeoutException:
        return failure(path, 504, "ADR_TIMEOUT", "等待 ADR 响应超时，执行结果未确认")
    except httpx.RequestError:
        return failure(path, 502, "ADR_UNAVAILABLE", "无法连接 ADR，执行结果未确认")
    # Preserve upstream success/error JSON and HTTP status, including 400/409/503.
    try:
        payload = upstream.json()
        if not isinstance(payload, dict):
            raise ValueError("Expected object")
        json.dumps(payload, allow_nan=False)
    except (ValueError, UnicodeDecodeError):
        return failure(path, 502, "ADR_INVALID_RESPONSE", "ADR 返回了无效的 JSON 对象")
    if path == '/capture' and upstream.status_code == 200 and payload.get('success') is True:
        payload['downloads'] = {'film': None, 'ai': None, 'humanReview': None}
        if payload.get('saved') is True:
            expected = body.get('savePath')
            if not expected or str(payload.get('savedFilePath', '')).replace('\\', '/') != expected.replace('\\', '/'):
                return failure(path, 502, 'ADR_INVALID_RESPONSE', 'ADR 返回的保存路径与请求不一致')
            payload['downloads'] = capture_downloads(request.app.state.settings.storage_root, local_path)
        return JSONResponse(payload, status_code=upstream.status_code)
    return Response(upstream.content, status_code=upstream.status_code, media_type="application/json")


@router.post("/xray/high-voltage")
async def high_voltage(request: Request):
    return await forward(request, "/xray/high-voltage")


@router.post("/capture")
async def capture(request: Request):
    return await forward(request, "/capture")


@router.get('/files/{filename}')
def download(request: Request, filename: str):
    try:
        target = download_file(request.app.state.settings.storage_root, filename)
    except OSError:
        return JSONResponse({'success': False, 'errorCode': 'FILE_NOT_FOUND',
                             'message': '文件不存在或不可下载'}, status_code=404)
    media = {'.tif': 'image/tiff', '.tiff': 'image/tiff', '.dcm': 'application/dicom',
             '.xml': 'application/xml'}[target.suffix.lower()]
    return FileResponse(target, media_type=media, filename=target.name,
                        headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
