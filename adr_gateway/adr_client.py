"""Forward ADR calls without retries or changing its response contract."""
import logging
import math
import time

import httpx

log = logging.getLogger(__name__)


class AdrClient:
    def __init__(self, settings, *, transport=None):
        self.settings = settings
        self.transport = transport

    async def call(self, path: str, body: dict) -> httpx.Response:
        timeout = 10.0
        if path == "/capture":
            timeout = 60.0
            period, count = body.get("framePeriodSeconds"), body.get("integrationCount")
            if type(period) in (int, float) and type(count) is int:
                try:
                    estimate = period * count * 2 + 30
                    if math.isfinite(estimate) and estimate > 0:
                        timeout = max(timeout, estimate)
                except OverflowError:
                    pass  # ADR validates invalid parameter ranges.
        started = time.monotonic()
        log.info("%s 开始 请求: %s", path, body)
        try:
            async with httpx.AsyncClient(transport=self.transport, trust_env=False, follow_redirects=False) as client:
                response = await client.post(self.settings.adr_base_url + path, json=body, timeout=timeout)
            log.info("%s HTTP %s (%.3fs) 响应: %s", path, response.status_code,
                     time.monotonic() - started, response.text)
            return response
        except httpx.RequestError:
            log.exception("%s 请求失败 (%.3fs)", path, time.monotonic() - started)
            raise
