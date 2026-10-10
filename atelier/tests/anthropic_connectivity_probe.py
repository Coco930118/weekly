"""Minimal Anthropic connectivity probe.

Purpose only: confirm the API key / org / scope work at all. This does NOT
use any Coco Atelier canon or employee instruction text, and is not part of
the normal test suite (its filename does not match unittest discover's
default `test*.py` pattern). Run manually via the `anthropic-connectivity-
probe` GitHub Actions workflow (workflow_dispatch), where ANTHROPIC_API_KEY
is injected from repository secrets.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


def require_live_env():
    if os.environ.get("ATELIER_ANTHROPIC_LIVE") != "1":
        raise SystemExit("ATELIER_ANTHROPIC_LIVE=1 is required")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is missing")


def probe():
    model = os.environ.get("ANTHROPIC_PROBE_MODEL", "claude-sonnet-5-5")
    max_tokens = 16
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": "Reply with exactly one word: ok"}],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read())
            result = {
                "status": "ok",
                "http_status": response.status,
                "model": payload.get("model"),
                "stop_reason": payload.get("stop_reason"),
                "usage": payload.get("usage"),
                "max_output_tokens": max_tokens,
            }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        result = {
            "status": "error",
            "http_status": exc.code,
            "error_body": detail[:2000],
        }
    except urllib.error.URLError as exc:
        result = {"status": "error", "error_body": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    require_live_env()
    outcome = probe()
    sys.exit(0 if outcome.get("status") == "ok" else 1)
