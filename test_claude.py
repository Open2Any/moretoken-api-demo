#!/usr/bin/env python3
"""Test Claude (Anthropic /v1/messages) via the new-api gateway.

Mirrors the style of test_gpt_image_2.py — single-file, stdlib only, hardcoded
config block at the top. Hits the OpenAI-compatible /v1/chat/completions endpoint
that new-api exposes (so the same gateway can route any model). If you need the
native Anthropic /v1/messages shape instead, flip USE_ANTHROPIC_NATIVE = True.
"""

# ---- hardcoded config ----
API_KEY = "API_KEY"
BASE_URL = "http://10.10.101.205:8080"
MODEL = "claude-opus-4-7"
PROMPT = "用一句话介绍你自己。"
MAX_TOKENS = 256
USE_ANTHROPIC_NATIVE = True  # True = POST /v1/messages with x-api-key header
# --------------------------

import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def call_openai_compat() -> dict:
    url = f"{BASE_URL.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": MAX_TOKENS,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    print(f"POST {url}")
    print(f"  model={MODEL}  max_tokens={MAX_TOKENS}")
    print(f"  prompt={PROMPT!r}")

    req = Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urlopen(req, timeout=120) as resp:
        body = resp.read().decode()
        print(f"\nHTTP {resp.status}")
    return json.loads(body)


def call_anthropic_native() -> dict:
    url = f"{BASE_URL.rstrip('/')}/v1/messages"
    payload = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": PROMPT}],
    }
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    if API_KEY:
        headers["x-api-key"] = API_KEY

    print(f"POST {url}")
    print(f"  model={MODEL}  max_tokens={MAX_TOKENS}")
    print(f"  prompt={PROMPT!r}")

    req = Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urlopen(req, timeout=120) as resp:
        body = resp.read().decode()
        print(f"\nHTTP {resp.status}")
    return json.loads(body)


def extract_text(data: dict) -> str:
    # OpenAI-compatible
    if "choices" in data and data["choices"]:
        msg = data["choices"][0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    # Anthropic native
    if "content" in data and isinstance(data["content"], list):
        return "".join(p.get("text", "") for p in data["content"] if p.get("type") == "text")
    return ""


def main() -> int:
    try:
        data = call_anthropic_native() if USE_ANTHROPIC_NATIVE else call_openai_compat()
    except HTTPError as e:
        print(f"\nHTTP {e.code} {e.reason}")
        print(e.read().decode(errors="replace"))
        return 1
    except URLError as e:
        print(f"\nConnection failed: {e.reason}")
        return 1

    text = extract_text(data)
    if not text:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 1

    print("\n--- response ---")
    print(text)

    if "usage" in data:
        print(f"\nusage: {data['usage']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
