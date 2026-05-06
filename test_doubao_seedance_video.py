#!/usr/bin/env python3
"""Test Doubao Seedance video generation via the moretoken gateway."""

# ---- hardcoded config ----
API_KEY = "API_KEY"
BASE_URL = "https://napi.moretoken.ai"
MODEL = "doubao-seedance-2-0-260128"
PROMPT = "一只橘猫坐在复古咖啡馆窗边，镜头缓慢推进，暖金色电影感光影。"
SECONDS = 5
POLL_INTERVAL_SECONDS = 10
TIMEOUT_SECONDS = 900
OUTPUT_FILE = "output.mp4"
DOWNLOAD_RESULT = True
# Optional Doubao-specific passthrough params, for example:
# {"ratio": "16:9", "resolution": "720p", "watermark": False}
METADATA = {}
# --------------------------

import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def build_headers(content_type: bool = True) -> dict:
    headers = {}
    if content_type:
        headers["Content-Type"] = "application/json"
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    return headers


def request_json(method: str, url: str, payload: dict | None = None, timeout: int = 600) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=data, headers=build_headers(), method=method)
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
        print(f"\nHTTP {resp.status}")
    return json.loads(body)


def create_video() -> dict:
    url = f"{BASE_URL.rstrip('/')}/v1/videos"
    payload = {
        "model": MODEL,
        "prompt": PROMPT,
        "seconds": str(SECONDS),
    }
    if METADATA:
        payload["metadata"] = METADATA

    print(f"POST {url}")
    print(f"  model={MODEL}  seconds={SECONDS}")
    print(f"  prompt={PROMPT!r}")
    if METADATA:
        print(f"  metadata={json.dumps(METADATA, ensure_ascii=False)}")

    return request_json("POST", url, payload=payload, timeout=600)


def fetch_video(task_id: str) -> dict:
    url = f"{BASE_URL.rstrip('/')}/v1/videos/{task_id}"
    print(f"\nGET {url}")
    return request_json("GET", url, timeout=120)


def extract_node(data: dict) -> dict:
    if isinstance(data.get("data"), dict):
        return data["data"]
    return data


def extract_task_id(data: dict) -> str:
    node = extract_node(data)
    for key in ("id", "task_id"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def extract_status(data: dict) -> str:
    node = extract_node(data)
    value = node.get("status")
    return value if isinstance(value, str) else ""


def extract_progress(data: dict) -> str:
    node = extract_node(data)
    value = node.get("progress")
    if isinstance(value, int):
        return f"{value}%"
    if isinstance(value, str):
        return value
    return ""


def extract_video_url(data: dict) -> str:
    node = extract_node(data)

    metadata = node.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("url")
        if isinstance(value, str) and value.strip():
            return value

    value = node.get("url")
    if isinstance(value, str) and value.strip():
        return value
    return ""


def extract_error(data: dict) -> str:
    node = extract_node(data)

    error = node.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message

    reason = node.get("reason")
    if isinstance(reason, str) and reason.strip():
        return reason

    return ""


def wait_until_done(task_id: str) -> dict:
    deadline = time.monotonic() + TIMEOUT_SECONDS

    while True:
        data = fetch_video(task_id)
        status = extract_status(data) or "unknown"
        progress = extract_progress(data) or "?"
        video_url = extract_video_url(data)

        print(f"  status={status}  progress={progress}")
        if video_url:
            print(f"  video_url={video_url}")

        if status in {"completed", "succeeded"}:
            return data

        if status in {"failed", "error", "cancelled"}:
            message = extract_error(data) or "video generation failed"
            raise RuntimeError(message)

        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out after {TIMEOUT_SECONDS}s waiting for task {task_id}")

        time.sleep(POLL_INTERVAL_SECONDS)


def download_video(task_id: str) -> Path:
    url = f"{BASE_URL.rstrip('/')}/v1/videos/{task_id}/content"
    out = Path(__file__).resolve().with_name(OUTPUT_FILE)

    print(f"\nGET {url}")
    req = Request(url, headers=build_headers(content_type=False), method="GET")
    with urlopen(req, timeout=1800) as resp:
        data = resp.read()
        print(f"\nHTTP {resp.status}")

    out.write_bytes(data)
    print(f"saved -> {out}  ({out.stat().st_size} bytes)")
    return out


def main() -> int:
    try:
        create_resp = create_video()
        task_id = extract_task_id(create_resp)
        if not task_id:
            print(json.dumps(create_resp, indent=2, ensure_ascii=False))
            return 1

        print("\n--- task created ---")
        print(f"task_id={task_id}")

        final_resp = wait_until_done(task_id)
        print("\n--- final response ---")
        print(json.dumps(final_resp, indent=2, ensure_ascii=False))

        if DOWNLOAD_RESULT:
            download_video(task_id)
        return 0
    except HTTPError as e:
        print(f"\nHTTP {e.code} {e.reason}")
        print(e.read().decode(errors="replace"))
        return 1
    except URLError as e:
        print(f"\nConnection failed: {e.reason}")
        return 1
    except TimeoutError as e:
        print(f"\nTimeout: {e}")
        return 1
    except RuntimeError as e:
        print(f"\nTask failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
