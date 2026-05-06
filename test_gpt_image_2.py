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
OUTPUT_FILE = "output.png"
# --------------------------

import base64
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


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

    print(f"POST {url}")
    print(f"  model={MODEL}  size={SIZE}")
    print(f"  prompt={PROMPT!r}")

    req = Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urlopen(req, timeout=600) as resp:
            body = resp.read().decode()
            status = resp.status
    except HTTPError as e:
        print(f"\nHTTP {e.code} {e.reason}")
        print(e.read().decode(errors="replace"))
        return 1
    except URLError as e:
        print(f"\nConnection failed: {e.reason}")
        return 1

    print(f"\nHTTP {status}")
    data = json.loads(body)

    if "data" not in data or not data["data"]:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 1

    item = data["data"][0]
    out = Path(OUTPUT_FILE)

    if "b64_json" in item:
        out.write_bytes(base64.b64decode(item["b64_json"]))
        print(f"saved -> {out.resolve()}  ({out.stat().st_size} bytes)")
    elif "url" in item:
        print(f"image url: {item['url']}")
        with urlopen(item["url"], timeout=300) as r:
            out.write_bytes(r.read())
        print(f"saved -> {out.resolve()}  ({out.stat().st_size} bytes)")
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 1

    if "usage" in data:
        print(f"usage: {data['usage']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
