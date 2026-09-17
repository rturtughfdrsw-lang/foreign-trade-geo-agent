"""One-off runtime PoC for geo-optimizer-skill; not a production adapter."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import fields, is_dataclass
from typing import Any

from geo_optimizer import __version__, audit


PUBLIC_URLS = ("https://example.com", "https://www.python.org")
LOCALHOST_URL = "http://127.0.0.1"


def _summary(url: str) -> dict[str, Any]:
    """Run one audit and return only a compact, observed result summary."""
    started = time.perf_counter()
    try:
        result = audit(url)
    except Exception as exc:  # The PoC must report an unexpected library exception.
        return {
            "url": url,
            "success": False,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        }

    top_level_fields = [item.name for item in fields(result)] if is_dataclass(result) else []
    recommendations = getattr(result, "recommendations", [])
    citability = getattr(result, "citability", None)
    return {
        "url": url,
        "success": getattr(result, "error", None) is None,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "result_type": f"{type(result).__module__}.{type(result).__qualname__}",
        "top_level_fields": top_level_fields,
        "score": getattr(result, "score", None),
        "band": getattr(result, "band", None),
        "http_status": getattr(result, "http_status", None),
        "error": getattr(result, "error", None),
        "score_breakdown": getattr(result, "score_breakdown", None),
        "recommendation_count": len(recommendations),
        "recommendation_sample": recommendations[:3],
        "citability_score": getattr(citability, "total_score", None),
        "citability_grade": getattr(citability, "grade", None),
    }


def main() -> int:
    results = {
        "python_version": sys.version,
        "geo_optimizer_version": __version__,
        "public_audits": [_summary(url) for url in PUBLIC_URLS],
        "localhost_audit": _summary(LOCALHOST_URL),
    }
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
