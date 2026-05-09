#!/usr/bin/env python3
"""Test Seedance 2.0 image-to-video generation via the moretoken gateway."""

# ---- hardcoded config ----
API_KEY = "API_KEY"
BASE_URL = "https://napi.moretoken.ai"
MODEL = "doubao-seedance-2-0-260128"
PROMPT = "镜头缓慢推进，画面中的人物微微转头望向窗外，暖金色光影流动，电影感氛围。"
IMAGE_FILE = "assets/image.png"    # 参考图片路径（相对于脚本目录）
SECONDS = 5
POLL_INTERVAL_SECONDS = 10
TIMEOUT_SECONDS = 900
OUTPUT_FILE = "assets/output_i2v.mp4"
DOWNLOAD_RESULT = True
# --------------------------

import base64
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass

SCRIPT_DIR = Path(__file__).resolve().parent


def log(message: str) -> None:
    print(message, flush=True)


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
        log(f"HTTP {resp.status}")
    return json.loads(body)


def load_image_base64(path: Path) -> str:
    raw = path.read_bytes()
    return base64.b64encode(raw).decode()


def create_video() -> dict:
    url = f"{BASE_URL.rstrip('/')}/v1/videos"

    image_path = SCRIPT_DIR / IMAGE_FILE
    if not image_path.exists():
        raise FileNotFoundError(f"Reference image not found: {image_path}")

    img_b64 = load_image_base64(image_path)
    log(f"Loaded reference image: {image_path} ({image_path.stat().st_size} bytes)")

    # Gateway TaskSubmitReq parses `image` / `images` / `input_reference`,
    # not `image_url` — wrong field name was silently dropped, falling back to t2v.
    data_uri = f"data:image/png;base64,{img_b64}"

    payload = {
        "model": MODEL,
        "prompt": PROMPT,
        "seconds": str(SECONDS),
        "image": data_uri,
    }

    log(f"\nPOST {url}")
    log(f"  model={MODEL}  seconds={SECONDS}")
    log(f"  prompt={PROMPT!r}")
    log(f"  image={IMAGE_FILE} (base64, {len(img_b64)} chars)")

    return request_json("POST", url, payload=payload, timeout=600)


def fetch_video(task_id: str) -> dict:
    url = f"{BASE_URL.rstrip('/')}/v1/videos/{task_id}"
    log(f"\nGET {url}")
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
    started = time.monotonic()

    while True:
        data = fetch_video(task_id)
        status = extract_status(data) or "unknown"
        progress = extract_progress(data) or "?"
        video_url = extract_video_url(data)
        elapsed = time.monotonic() - started

        log(f"  status={status}  progress={progress}  elapsed={elapsed:.0f}s")
        if video_url:
            log(f"  video_url={video_url}")

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
    out = SCRIPT_DIR / OUTPUT_FILE

    log(f"\nGET {url}")
    req = Request(url, headers=build_headers(content_type=False), method="GET")
    with urlopen(req, timeout=1800) as resp:
        data = resp.read()
        log(f"HTTP {resp.status}")

    out.write_bytes(data)
    log(f"saved -> {out}  ({out.stat().st_size} bytes)")
    return out


def main() -> int:
    try:
        create_resp = create_video()
        task_id = extract_task_id(create_resp)
        if not task_id:
            log("\n--- no task_id in response ---")
            log(json.dumps(create_resp, indent=2, ensure_ascii=False))
            return 1

        log("\n--- task created ---")
        log(f"task_id={task_id}")

        final_resp = wait_until_done(task_id)
        log("\n--- final response ---")
        log(json.dumps(final_resp, indent=2, ensure_ascii=False))

        if DOWNLOAD_RESULT:
            download_video(task_id)
        return 0
    except HTTPError as e:
        log(f"\nHTTP {e.code} {e.reason}")
        log(e.read().decode(errors="replace"))
        return 1
    except URLError as e:
        log(f"\nConnection failed: {e.reason}")
        return 1
    except TimeoutError as e:
        log(f"\nTimeout: {e}")
        return 1
    except RuntimeError as e:
        log(f"\nTask failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
