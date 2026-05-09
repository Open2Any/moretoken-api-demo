#!/usr/bin/env python3
"""Smoke test the newly added Volcengine model IDs."""

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_KEY = os.getenv("API_KEY", os.getenv("MORETOKEN_API_KEY", ""))
BASE_URL = os.getenv("BASE_URL", "https://napi.moretoken.ai")
TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", "180"))
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "1920x1920")

MODELS = [
    "doubao-seedream-3-0-t2i-250415",
    "doubao-seedream-4-5-251128",
    "doubao-seedream-5-0-260128",
    "doubao-seedream-5-0-lite-260128",
    "doubao-seed-2-0-lite-260428",
    "doubao-seed-2-0-mini-260215",
    "doubao-seed-2-0-mini-260428",
    "doubao-seed-2-0-pro-260215",
    "doubao-seed-character-251128",
]


def post_json(path: str, payload: dict) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    req = Request(
        f"{BASE_URL.rstrip('/')}{path}",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return resp.status, json.loads(resp.read().decode())


def test_image_model(model: str) -> tuple[int, dict]:
    return post_json(
        "/v1/images/generations",
        {
            "model": model,
            "prompt": "一只白色马克杯放在木桌上，简洁产品摄影风格。",
            "n": 1,
            "size": IMAGE_SIZE,
        },
    )


def test_chat_model(model: str) -> tuple[int, dict]:
    return post_json(
        "/v1/chat/completions",
        {
            "model": model,
            "messages": [{"role": "user", "content": "用一句话回复：模型连通测试成功。"}],
            "max_tokens": 64,
            "stream": False,
        },
    )


def extract_summary(data: dict) -> str:
    if data.get("data"):
        item = data["data"][0]
        if "url" in item:
            return f"image url={item['url'][:80]}"
        if "b64_json" in item:
            return "image b64_json returned"
    if data.get("choices"):
        msg = data["choices"][0].get("message") or {}
        content = msg.get("content", "")
        if isinstance(content, str):
            return content.replace("\n", " ")[:120]
    if data.get("usage"):
        return f"usage={data['usage']}"
    return json.dumps(data, ensure_ascii=False)[:200]


def main() -> int:
    if not API_KEY:
        print("Missing API_KEY or MORETOKEN_API_KEY environment variable.")
        return 2

    failures = 0
    for model in MODELS:
        is_image = model.startswith("doubao-seedream-")
        endpoint = "/v1/images/generations" if is_image else "/v1/chat/completions"
        print(f"\n==> {model}")
        print(f"POST {BASE_URL.rstrip('/')}{endpoint}")

        try:
            status, data = test_image_model(model) if is_image else test_chat_model(model)
            print(f"OK HTTP {status}: {extract_summary(data)}")
        except HTTPError as e:
            failures += 1
            print(f"FAIL HTTP {e.code} {e.reason}")
            print(e.read().decode(errors="replace")[:1000])
        except (URLError, TimeoutError) as e:
            failures += 1
            print(f"FAIL connection: {e}")

    print(f"\nDone. total={len(MODELS)} failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
