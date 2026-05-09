#!/usr/bin/env python3
"""Test Seedance 2.0 text-to-video generation via the moretoken gateway."""

# ---- config ----
API_KEY = "API_KEY"
BASE_URL = "https://napi.moretoken.ai"
MODEL = "doubao-seedance-2-0-260128"
PROMPT = "一只橘猫坐在复古咖啡馆窗边，镜头缓慢推进，暖金色电影感光影，猫咪慵懒地眨眼。"
SECONDS = 5
POLL_INTERVAL = 10
TIMEOUT = 900
OUTPUT_FILE = "assets/output_t2v.mp4"
DOWNLOAD = True
# -----------------

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


def log(msg: str) -> None:
    print(msg, flush=True)


def headers(content_type: bool = True) -> dict:
    h = {}
    if content_type:
        h["Content-Type"] = "application/json"
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h


def api(method: str, url: str, payload: dict | None = None, timeout: int = 600) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=data, headers=headers(), method=method)
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
        log(f"HTTP {resp.status}")
    return json.loads(body)


def node(data: dict) -> dict:
    return data["data"] if isinstance(data.get("data"), dict) else data


def create_video() -> dict:
    url = f"{BASE_URL.rstrip('/')}/v1/videos"
    payload = {
        "model": MODEL,
        "prompt": PROMPT,
        "seconds": str(SECONDS),
    }
    log(f"\nPOST {url}")
    log(f"  model={MODEL}  seconds={SECONDS}")
    log(f"  prompt={PROMPT!r}")
    return api("POST", url, payload=payload)


def poll(task_id: str) -> dict:
    deadline = time.monotonic() + TIMEOUT
    started = time.monotonic()
    while True:
        url = f"{BASE_URL.rstrip('/')}/v1/videos/{task_id}"
        log(f"\nGET {url}")
        data = api("GET", url, timeout=120)
        n = node(data)
        status = n.get("status", "unknown")
        progress = n.get("progress", "?")
        elapsed = time.monotonic() - started
        log(f"  status={status}  progress={progress}  elapsed={elapsed:.0f}s")

        video_url = (n.get("metadata") or {}).get("url") or n.get("url")
        if video_url:
            log(f"  video_url={video_url}")

        if status in {"completed", "succeeded"}:
            return data
        if status in {"failed", "error", "cancelled"}:
            err = (n.get("error") or {}).get("message") or n.get("reason") or "failed"
            raise RuntimeError(err)
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out after {TIMEOUT}s")
        time.sleep(POLL_INTERVAL)


def download(task_id: str) -> Path:
    url = f"{BASE_URL.rstrip('/')}/v1/videos/{task_id}/content"
    out = SCRIPT_DIR / OUTPUT_FILE
    log(f"\nGET {url}")
    req = Request(url, headers=headers(content_type=False), method="GET")
    with urlopen(req, timeout=1800) as resp:
        out.write_bytes(resp.read())
        log(f"HTTP {resp.status}")
    log(f"saved -> {out}  ({out.stat().st_size} bytes)")
    return out


def main() -> int:
    try:
        resp = create_video()
        n = node(resp)
        task_id = n.get("id") or n.get("task_id") or ""
        if not task_id:
            log("\n--- no task_id ---")
            log(json.dumps(resp, indent=2, ensure_ascii=False))
            return 1

        log(f"\n--- task created ---")
        log(f"task_id={task_id}")

        final = poll(task_id)
        log("\n--- final response ---")
        log(json.dumps(final, indent=2, ensure_ascii=False))

        if DOWNLOAD:
            download(task_id)
        return 0
    except HTTPError as e:
        log(f"\nHTTP {e.code} {e.reason}")
        log(e.read().decode(errors="replace"))
        return 1
    except URLError as e:
        log(f"\nConnection failed: {e.reason}")
        return 1
    except (TimeoutError, RuntimeError) as e:
        log(f"\n{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
