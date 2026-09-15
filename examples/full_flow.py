"""Manual ON/capture/OFF example followed by HTTP artifact downloads."""
import argparse
import json
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18081/api/v1")
    parser.add_argument("--operate-hardware", action="store_true")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / 'downloads')
    args = parser.parse_args()
    if not args.operate_hardware:
        parser.error("真实高压/采集操作需要 --operate-hardware")

    with httpx.Client(timeout=60, trust_env=False) as client:
        def call(path, body):
            started = time.monotonic()
            print(f"{path} 开始", flush=True)
            response = client.post(args.base_url.rstrip("/") + path, json=body)
            print(f"{path} HTTP {response.status_code} ({time.monotonic()-started:.3f}s) 响应:", flush=True)
            try:
                payload = response.json()
                print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
            except ValueError:
                print(response.text, flush=True)
                raise
            response.raise_for_status()
            if payload.get("success") is not True:
                raise RuntimeError(payload)
            return payload

        try:
            call("/xray/high-voltage", {"enabled": True})
            capture = call("/capture", {"framePeriodSeconds": 1.0, "integrationCount": 10,
                              "generateMockDefect": args.mock, "overwriteExisting": False})
        finally:
            call("/xray/high-voltage", {"enabled": False})
        args.output.mkdir(parents=True, exist_ok=True)
        for kind, item in capture.get('downloads', {}).items():
            if item is None:
                print(f'{kind}: 无可下载文件', flush=True)
                continue
            target = args.output / Path(item['filename']).name
            print(f'{kind}: 下载开始', flush=True)
            with client.stream('GET', urljoin(args.base_url, item['url'])) as response:
                response.raise_for_status()
                with target.open('wb') as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
            print(f'{kind}: HTTP {response.status_code}，已保存 {target} ({target.stat().st_size} bytes)', flush=True)


if __name__ == "__main__":
    main()
