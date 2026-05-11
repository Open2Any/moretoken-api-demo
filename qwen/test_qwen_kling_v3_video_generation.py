#!/usr/bin/env python3
"""Test Qwen Kling v3 video generation via the moretoken gateway."""

# ---- hardcoded config ----
API_KEY = "API_KEY"
BASE_URL = "https://napi.moretoken.ai"
MODEL = "kling/kling-v3-video-generation"
PROMPT = "以参考图片中的女生为主体，保持人物身份、脸部特征、发型、白色衬衫、黑色背带和海边背景一致，生成一段真实自拍视频质感短视频；人物自然转身，手臂轻微摆动，头发被海风吹动，镜头轻微手持晃动，动作流畅连贯。"
IMAGE_SOURCE = "http://network.jancsitech.net:9000/video/qwen/reference_real_person_kling.jpg"
SECONDS = 15
SIZE = "720x1280"
ASPECT_RATIO = "9:16"
POLL_INTERVAL_SECONDS = 10
TIMEOUT_SECONDS = 1200
OUTPUT_FILE = "../assets/output/qwen/output_qwen_kling_v3_video_generation.mp4"
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


def resolve_image_input() -> tuple[str, str]:
    source = IMAGE_SOURCE.strip()
    if source.startswith(("http://", "https://")):
        return source, source

    image_path = (SCRIPT_DIR / source).resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"reference image not found: {image_path}")
    encoded = base64.b64encode(image_path.read_bytes()).decode()
    log(f"Loaded reference image: {image_path} ({image_path.stat().st_size} bytes)")
    return encoded, source


def create_video() -> dict:
    url = f"{BASE_URL.rstrip('/')}/v1/videos"
    image_value, image_label = resolve_image_input()

    payload = {
        "model": MODEL,
        "prompt": PROMPT,
        "seconds": str(SECONDS),
        "size": SIZE,
        "aspect_ratio": ASPECT_RATIO,
        "image": image_value,
    }

    log(f"\nPOST {url}")
    log(f"  model={MODEL}  seconds={SECONDS}  size={SIZE}")
    log(f"  prompt={PROMPT!r}")
    log(f"  image={image_label}")

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
    out = (SCRIPT_DIR / OUTPUT_FILE).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

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
    except FileNotFoundError as e:
        log(f"\n{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
