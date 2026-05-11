#!/usr/bin/env python3
"""Test Qwen HappyHorse 1.0 video-edit with local video/image files via the moretoken gateway."""

# ---- hardcoded config ----
API_KEY = "API_KEY"
BASE_URL = "https://napi.moretoken.ai"
MODEL = "happyhorse-1.0-video-edit"
PROMPT = "以输入视频的动作节奏和镜头运动为基础，参考图片中的女生形象，尽量保持人物身份、脸部特征、发型、白色衬衫和黑色背带一致，输出真实自拍视频质感的舞蹈短视频，人物稳定清晰，动作自然连贯。"
VIDEO_SOURCE = "./blueprint-supreme-dance-tiktok_10s_540x720_15fps.mp4"
REFERENCE_IMAGE_SOURCE = "./reference_real_person.jpg"
SIZE = "720p"
SECONDS = 15
WATERMARK = True
SEED = None
POLL_INTERVAL_SECONDS = 10
TIMEOUT_SECONDS = 1200
OUTPUT_FILE = "../assets/output/qwen/output_qwen_happyhorse_1_0_video_edit_reference_video_generation_15s.mp4"
DOWNLOAD_RESULT = True
# --------------------------

import base64
import json
import mimetypes
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
    req = Request(url, data=data, headers=build_headers(content_type=payload is not None), method=method)
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
        log(f"HTTP {resp.status}")
    return json.loads(body)


def guess_mime_type(path: Path, fallback: str) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or fallback


def resolve_media_input(source: str, fallback_mime: str, label: str) -> tuple[str, str]:
    source = source.strip()
    media_path = (SCRIPT_DIR / source).resolve()
    if not media_path.exists():
        raise FileNotFoundError(f"{label} not found: {media_path}")

    encoded = base64.b64encode(media_path.read_bytes()).decode()
    mime_type = guess_mime_type(media_path, fallback_mime)
    data_uri = f"data:{mime_type};base64,{encoded}"
    log(f"Loaded {label}: {media_path} ({media_path.stat().st_size} bytes, {mime_type})")
    return data_uri, source


def create_video() -> dict:
    url = f"{BASE_URL.rstrip('/')}/v1/videos"
    video_value, video_label = resolve_media_input(VIDEO_SOURCE, "video/mp4", "source video")
    image_value, image_label = resolve_media_input(REFERENCE_IMAGE_SOURCE, "image/jpeg", "reference image")

    metadata = {
        "input": {
            "img_url": "",
            "media": [
                {
                    "type": "video",
                    "url": video_value,
                },
                {
                    "type": "reference_image",
                    "url": image_value,
                },
            ],
        },
        "parameters": {
            "watermark": WATERMARK,
        },
    }
    if SEED is not None:
        metadata["parameters"]["seed"] = SEED

    payload = {
        "model": MODEL,
        "prompt": PROMPT,
        "seconds": str(SECONDS),
        "size": SIZE,
        "image": image_value,
        "metadata": metadata,
    }

    log(f"\nPOST {url}")
    log(f"  model={MODEL}  seconds={SECONDS}  size={SIZE}")
    log(f"  prompt={PROMPT!r}")
    log(f"  source_video={video_label}")
    log(f"  reference_image={image_label}")

    return request_json("POST", url, payload=payload, timeout=600)


def fetch_video(task_id: str) -> dict:
    url = f"{BASE_URL.rstrip('/')}/v1/videos/{task_id}"
    log(f"\nGET {url}")
    return request_json("GET", url, timeout=120)


def extract_node(data: dict) -> dict:
    if isinstance(data.get("data"), dict):
        return data["data"]
    if isinstance(data.get("output"), dict):
        return data["output"]
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
    for key in ("status", "task_status"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


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

    for key in ("url", "video_url", "remote_url"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value

    task_result = node.get("task_result")
    if isinstance(task_result, dict):
        videos = task_result.get("videos")
        if isinstance(videos, list) and videos:
            url = videos[0].get("url")
            if isinstance(url, str) and url.strip():
                return url

    return ""


def extract_error(data: dict) -> str:
    node = extract_node(data)
    for key in ("reason", "message", "task_status_msg", "msg"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            code = node.get("code")
            return f"{code}: {value}" if isinstance(code, str) and code.strip() else value

    error = node.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message

    message = data.get("message")
    if isinstance(message, str) and message.strip():
        code = data.get("code")
        return f"{code}: {message}" if isinstance(code, str) and code.strip() else message

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

        if status in {"completed", "succeeded"} or status.upper() in {"SUCCEEDED", "SUCCESS"}:
            return data

        if status in {"failed", "error", "cancelled"} or status.upper() in {"FAILED", "ERROR", "CANCELED", "CANCELLED"}:
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
        log("\n--- create response ---")
        log(json.dumps(create_resp, indent=2, ensure_ascii=False))

        task_id = extract_task_id(create_resp)
        if not task_id:
            log("\n--- no task_id in response ---")
            return 1

        log(f"\n--- task created ---\ntask_id={task_id}")

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
