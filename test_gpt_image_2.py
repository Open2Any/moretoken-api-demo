'''
Description: 
Author: Devin
Date: 2026-04-30 05:15:48
'''
#!/usr/bin/env python3
"""Test gpt-image-2 via the new-api gateway."""

# ---- hardcoded config ----
API_KEY = "API_KEY"
BASE_URL = "https://napi.moretoken.ai"
MODEL = "gpt-image-2"
PROMPT = "给我一张复古图片"
SIZE = "1024x1024"
OUTPUT_FILE = "assets/output/output_gpt_image_2.png"
RESPONSE_JSON_FILE = "assets/output/output_gpt_image_2_response.json"
REQUEST_TIMEOUT_SECONDS = 1200
DOWNLOAD_TIMEOUT_SECONDS = 900
# --------------------------

import base64
import json
import sys
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass

SCRIPT_DIR = Path(__file__).resolve().parent


def elapsed(started: float) -> str:
    return f"{time.monotonic() - started:.2f}s"


def log(message: str) -> None:
    print(message, flush=True)


def start_heartbeat(label: str, started: float, interval: int = 15) -> threading.Event:
    stop = threading.Event()

    def run() -> None:
        while not stop.wait(interval):
            log(f"... still waiting for {label} after {elapsed(started)}")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return stop


def main() -> int:
    url = f"{BASE_URL.rstrip('/')}/v1/images/generations"
    payload = {
        "model": MODEL,
        "prompt": PROMPT,
        "n": 1,
        "size": SIZE,
    }
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    log(f"POST {url}")
    log(f"  model={MODEL}  size={SIZE}")
    log(f"  prompt={PROMPT!r}")
    log(f"  request_timeout={REQUEST_TIMEOUT_SECONDS}s")

    req = Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    started = time.monotonic()
    heartbeat = start_heartbeat("generation response", started)
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            log(f"\nresponse headers received after {elapsed(started)}")
            body = resp.read().decode()
            status = resp.status
    except HTTPError as e:
        heartbeat.set()
        log(f"\nHTTP {e.code} {e.reason} after {elapsed(started)}")
        log(e.read().decode(errors="replace"))
        return 1
    except URLError as e:
        heartbeat.set()
        log(f"\nConnection failed after {elapsed(started)}: {e.reason}")
        return 1
    except TimeoutError as e:
        heartbeat.set()
        log(f"\nGeneration request timed out after {elapsed(started)}: {e}")
        return 1
    finally:
        heartbeat.set()

    log(f"\nHTTP {status} after {elapsed(started)}")
    response_json = SCRIPT_DIR / RESPONSE_JSON_FILE
    response_json.parent.mkdir(parents=True, exist_ok=True)
    response_json.write_text(body, encoding="utf-8")
    log(f"response json -> {response_json}")

    data = json.loads(body)

    if "data" not in data or not data["data"]:
        log(json.dumps(data, indent=2, ensure_ascii=False))
        return 1

    item = data["data"][0]
    out = SCRIPT_DIR / OUTPUT_FILE
    out.parent.mkdir(parents=True, exist_ok=True)

    if "b64_json" in item:
        out.write_bytes(base64.b64decode(item["b64_json"]))
        log(f"saved -> {out.resolve()}  ({out.stat().st_size} bytes)")
    elif "url" in item:
        log(f"image url: {item['url']}")
        log(f"  download_timeout={DOWNLOAD_TIMEOUT_SECONDS}s")
        download_started = time.monotonic()
        heartbeat = start_heartbeat("image download", download_started)
        try:
            with urlopen(item["url"], timeout=DOWNLOAD_TIMEOUT_SECONDS) as r:
                out.write_bytes(r.read())
        except HTTPError as e:
            heartbeat.set()
            log(f"\nDownload failed: HTTP {e.code} {e.reason} after {elapsed(download_started)}")
            log(f"generation response is saved at {response_json}")
            return 1
        except URLError as e:
            heartbeat.set()
            log(f"\nDownload failed after {elapsed(download_started)}: {e.reason}")
            log(f"generation response is saved at {response_json}")
            return 1
        except TimeoutError as e:
            heartbeat.set()
            log(f"\nDownload timed out after {elapsed(download_started)}: {e}")
            log(f"generation response is saved at {response_json}")
            return 1
        finally:
            heartbeat.set()
        log(f"saved -> {out.resolve()}  ({out.stat().st_size} bytes)")
    else:
        log(json.dumps(data, indent=2, ensure_ascii=False))
        return 1

    if "usage" in data:
        log(f"usage: {data['usage']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
