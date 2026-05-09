#!/usr/bin/env python3
"""Test Kling OmniVideo image-to-video via the moretoken gateway.

Reference:
  submit via moretoken OpenAI-compatible route: POST /v1/videos
  fetch via moretoken OpenAI-compatible route:  GET /v1/videos/{task_id}
"""

# ---- hardcoded config ----
API_KEY = "API_KEY"
BASE_URL = "https://www.moretoken.ai"
MODEL_NAME = "kling-v3-omni"
MODE = "pro"
PROMPT = "基于参考图生成一段短视频：人物轻轻转头看向窗外，室内暖光流动，镜头缓慢推进，真实电影感。"
IMAGE_FILE = "../assets/reference_real_person.jpg"
DURATION = "5"
SIZE = "1280x720"
POLL_INTERVAL_SECONDS = 10
TIMEOUT_SECONDS = 1200
OUTPUT_FILE = "../assets/kling/output_kling_v3_omni_video_generation.mp4"
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
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
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


def create_video() -> dict:
    url = f"{BASE_URL.rstrip('/')}/v1/videos"
    image_path = (SCRIPT_DIR / IMAGE_FILE).resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"reference image not found: {image_path}")
    encoded = base64.b64encode(image_path.read_bytes()).decode()
    log(f"Loaded reference image: {image_path} ({image_path.stat().st_size} bytes)")

    payload = {
        "model": MODEL_NAME,
        "mode": MODE,
        "duration": DURATION,
        "size": SIZE,
        "prompt": PROMPT,
        "image": encoded,
    }

    log(f"\nPOST {url}")
    log(f"  model={MODEL_NAME}  mode={MODE}  duration={DURATION}  size={SIZE}")
    log(f"  prompt={PROMPT!r}")
    log(f"  image={IMAGE_FILE}")

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
    for key in ("task_id", "id"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def extract_status(data: dict) -> str:
    node = extract_node(data)
    for key in ("task_status", "status"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def extract_video_url(data: dict) -> str:
    node = extract_node(data)
    metadata = node.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("url")
        if isinstance(value, str) and value.strip():
            return value
    task_result = node.get("task_result")
    if isinstance(task_result, dict):
        videos = task_result.get("videos")
        if isinstance(videos, list) and videos:
            url = videos[0].get("url")
            if isinstance(url, str) and url.strip():
                return url
    value = node.get("url")
    if isinstance(value, str) and value.strip():
        return value
    return ""


def extract_error(data: dict) -> str:
    node = extract_node(data)
    for key in ("task_status_msg", "message", "msg"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value
    error = node.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message
    return ""


def wait_until_done(task_id: str) -> tuple[dict, str]:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    started = time.monotonic()

    while True:
        data = fetch_video(task_id)
        status = extract_status(data) or "unknown"
        video_url = extract_video_url(data)
        elapsed = time.monotonic() - started

        log(f"  status={status}  elapsed={elapsed:.0f}s")
        if video_url:
            log(f"  video_url={video_url}")

        if status in {"succeed", "succeeded", "completed"}:
            return data, video_url

        if status in {"failed", "error", "cancelled"}:
            message = extract_error(data) or "video generation failed"
            raise RuntimeError(message)

        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out after {TIMEOUT_SECONDS}s waiting for task {task_id}")

        time.sleep(POLL_INTERVAL_SECONDS)


def download_from_url(video_url: str) -> Path:
    out = (SCRIPT_DIR / OUTPUT_FILE).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    log(f"\nGET {video_url}")
    req = Request(video_url, headers={"User-Agent": build_headers(content_type=False)["User-Agent"]}, method="GET")
    with urlopen(req, timeout=1800) as resp:
        data = resp.read()
        log(f"HTTP {resp.status}")

    out.write_bytes(data)
    log(f"saved -> {out}  ({out.stat().st_size} bytes)")
    return out


def main() -> int:
    try:
        create_resp = create_video()
        log("\n--- create response ---")
        log(json.dumps(create_resp, indent=2, ensure_ascii=False))

        task_id = extract_task_id(create_resp)
        if not task_id:
            log("\n--- no task_id in response ---")
            return 1

        log(f"\n--- task created ---\ntask_id={task_id}")

        final_resp, video_url = wait_until_done(task_id)
        log("\n--- final response ---")
        log(json.dumps(final_resp, indent=2, ensure_ascii=False))

        if DOWNLOAD_RESULT:
            if not video_url:
                log("\n--- no video_url in final response ---")
                return 1
            download_from_url(video_url)
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
    except FileNotFoundError as e:
        log(f"\n{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
