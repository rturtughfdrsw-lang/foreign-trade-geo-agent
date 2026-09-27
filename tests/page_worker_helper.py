"""Test-only subprocess behaviors for PageExtractor lifecycle tests."""

import base64
import json
import os
import sys
import time


def _success(final_url: str, body_text: str) -> dict[str, object]:
    return {
        "kind": "success",
        "page": {
            "final_url": final_url,
            "title": None,
            "description": None,
            "canonical": None,
            "h1": [],
            "h2": [],
            "body_text": body_text,
            "published_date": None,
            "structured_content": [],
            "structured_content_truncated": False,
        },
    }


def main() -> None:
    request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    html = base64.b64decode(request["html_base64"], validate=True)
    if html == b"MODE:SLEEP":
        time.sleep(60)
        return
    if html == b"MODE:CRASH":
        os._exit(23)
    if html == b"MODE:OVERSIZE":
        size = int(request["limits"]["max_worker_output_bytes"]) + 1
        sys.stdout.buffer.write(b"x" * size)
        sys.stdout.buffer.flush()
        return
    if html == b"MODE:ENV":
        if "STAGE_B_TEST_API_KEY" in os.environ:
            os._exit(41)
        response = _success(request["final_url"], "worker environment is clean")
        sys.stdout.buffer.write(json.dumps(response).encode("utf-8"))
        return
    os._exit(24)


if __name__ == "__main__":
    main()
