'''
Description: 
Author: Devin
Date: 2026-05-06 07:52:10
'''
#!/usr/bin/env python3
"""Test Codex gpt-5.4 via the new-api gateway."""

# ---- hardcoded config ----
API_KEY = "API_KEY"
BASE_URL = "https://napi.moretoken.ai"
MODEL = "gpt-5.4"
INSTRUCTIONS = "You are Codex. Answer briefly and directly."
PROMPT = "用一句话介绍你自己。"
TIMEOUT_SECONDS = 600
# --------------------------

import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def call_responses() -> dict:
    url = f"{BASE_URL.rstrip('/')}/v1/responses"
    payload = {
        "model": MODEL,
        "instructions": INSTRUCTIONS,
        "input": [{"role": "user", "content": PROMPT}],
        "stream": False,
        "store": False,
    }
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    print(f"POST {url}")
    print(f"  model={MODEL}")
    print(f"  prompt={PROMPT!r}")

    req = Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        body = resp.read().decode()
        print(f"\nHTTP {resp.status}")
    return json.loads(body)


def extract_text(data: dict) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    parts = []
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            elif isinstance(content, str):
                parts.append(content)

    return "".join(parts)


def main() -> int:
    try:
        data = call_responses()
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
