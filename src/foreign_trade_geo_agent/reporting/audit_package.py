"""Exclusive, hash-bound JSON export independent of History artifact schemas."""

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


UNVERIFIED = (
    "Whole-site coverage or absence of uncrawled pages",
    "Search engine indexing, rankings, SERP intent, traffic, conversions or revenue",
    "JavaScript-rendered content, authenticated pages, PDFs and external resources",
    "Schema, Open Graph, noindex, noai, llms.txt, sitemap and performance metrics",
    "Product facts, customer claims, source authenticity, legal authority and content quality",
)


def _json_default(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Enum):
        return value.value
    raise TypeError("Unsupported audit export value.")


def json_bytes(value):
    return (json.dumps(value, default=_json_default, ensure_ascii=False,
                       sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def safe_url(value):
    """Do not disclose credentials, query strings or fragments in diagnostics."""
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        authority = host + (f":{parts.port}" if parts.port else "")
        return urlunsplit((parts.scheme, authority, parts.path, "", ""))
    except ValueError:
        return "[invalid URL]"


def _digest(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


class PackageExporter:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self._write("INCOMPLETE.json", json_bytes({
            "package_complete": False,
            "status": "incomplete_do_not_accept",
            "reason": "No committed, verified manifest; execution or export may have stopped.",
        }))

    def _write(self, name, data):
        with (self.directory / name).open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

    def finish(self, *, crawl, packet, audit, requests, fetches, inputs, outcome, started_at,
               duration_seconds):
        # Core contracts are exported as plain data; History's schema is untouched.
        crawl_data = asdict(crawl)
        for failure in crawl_data["failures"]:
            failure["error"] = "Controlled crawl failure; inspect typed categories."
            failure["requested_url"] = safe_url(failure["requested_url"])
            if failure["final_url"]:
                failure["final_url"] = safe_url(failure["final_url"])
        payloads = {
            "input.json": json_bytes(inputs), "crawl.json": json_bytes(crawl_data),
            "packet.json": (packet.to_json() + "\n").encode("utf-8"),
            "audit.json": json_bytes(audit), "requests.json": json_bytes(requests),
            "fetches.json": json_bytes(fetches),
        }
        truncation = {
            "packet_truncated": packet.truncated,
            "crawl_structured_truncated_urls": [p.final_url for p in crawl.pages
                                                if p.structured_content_truncated],
            "packet_content_truncated_ids": [p.evidence_id for p in packet.pages if p.content_truncated],
            "packet_structured_truncated_ids": [p.evidence_id for p in packet.pages
                                               if p.structured_content_truncated],
            "text_policy": "Extractor rejects over-limit body/metadata; Packet selects bounded text. See extraction failures and packet flags.",
        }
        summary = (
            f"# Bounded read-only SEO audit\n\nOutcome: {outcome}\n\n"
            f"Observation: {inputs['provenance']['kind']}\n\n"
            f"Seed: {safe_url(crawl.seed_url)}\n\n"
            f"Crawled pages: {len(crawl.pages)}; failures: {len(crawl.failures)}; "
            f"Packet pages: {len(packet.pages)}; audit: {audit.status.value}; score: {audit.score}.\n\n"
            f"Robots: {crawl.robots_status.value}; stop: {crawl.stop_reason.value}; "
            f"budget exhausted: {crawl.budget_exhausted}; packet truncated: {packet.truncated}.\n\n"
            "This is a bounded static-page sample, never a whole-site audit. Unfetched pages are unknown. "
            "A heuristic score or successful export is not SEO acceptance or permission.\n\n"
            "Observed checks:\n\n" + "\n".join(f"- {e.check_key}: {e.outcome.value} ({e.observed_value})" for e in audit.evidence)
            + "\n\nUnverified:\n\n" + "\n".join(f"- {item}" for item in UNVERIFIED) + "\n"
        )
        payloads["summary.md"] = summary.encode("utf-8")
        for name, data in payloads.items():
            self._write(name, data)
        manifest = {
            "schema": "readonly-seo-audit-package-v1", "package_complete": True,
            "outcome": outcome, "sample_complete": outcome == "sample_complete",
            "full_site_audit": False, "seed_url": crawl.seed_url,
            "exact_origin": asdict(crawl.exact_origin) if crawl.exact_origin else None,
            "provenance": inputs["provenance"],
            "started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration_seconds, 6),
            "budgets": inputs["crawl_budgets"], "resources": asdict(crawl.resources),
            "robots_status": crawl.robots_status.value, "crawl_delay": crawl.crawl_delay,
            "robots_evidence": "crawl.json typed status; requests.json response status. Unknown is never permission; confirmed 404 follows native NOT_FOUND policy.",
            "robots_fetch": next((f for f in fetches if f["kind"] == "fetch_text"), None),
            "resource_accounting": "Native counters sum returned fetch results. In-flight cancelled operations may have no native counters; requests.json preserves started HTTP attempts.",
            "stop_reason": crawl.stop_reason.value, "budget_exhausted": crawl.budget_exhausted,
            "http_attempt_urls": [r["url"] for r in requests],
            "response_received_urls": [r["url"] for r in requests if r["response_received"]],
            "visited_pages": [{"requested_url": p.requested_url, "final_url": p.final_url,
                               "extraction_status": p.extraction_status.value} for p in crawl.pages],
            "failures": crawl_data["failures"], "truncation": truncation,
            "input_summary": {"packet_limits": inputs["packet_limits"],
                              "sha256": _digest(payloads["input.json"])["sha256"]},
            "output_summary": {"crawl_pages": len(crawl.pages), "packet_pages": len(packet.pages),
                               "audit_status": audit.status.value, "score": audit.score},
            "audit_coverage": [e.check_key for e in audit.evidence],
            "audit_input": "crawl.json successful extractions; packet.json is separately bounded observed evidence",
            "unverified": UNVERIFIED,
            "side_effects": "Only safe GET crawling and local export; no model/search/planning/Draft/WordPress dependencies constructed.",
            "files": {name: _digest(data) for name, data in payloads.items()},
        }
        self._write("manifest.json", json_bytes(manifest))
        # Read all files back before committing the completion marker removal.
        verify_package(self.directory, allow_incomplete=True)
        (self.directory / "INCOMPLETE.json").unlink()


def verify_package(directory, *, allow_incomplete=False):
    root = Path(directory)
    if not allow_incomplete and (root / "INCOMPLETE.json").exists():
        raise ValueError("Incomplete audit package.")
    manifest = json.loads((root / "manifest.json").read_bytes())
    required = {"input.json", "crawl.json", "packet.json", "audit.json", "requests.json", "fetches.json", "summary.md"}
    if (manifest.get("schema") != "readonly-seo-audit-package-v1"
            or manifest.get("package_complete") is not True or set(manifest["files"]) != required):
        raise ValueError("Invalid audit manifest.")
    parsed = {}
    for name, digest in manifest["files"].items():
        data = (root / name).read_bytes()
        if _digest(data) != digest:
            raise ValueError("Audit package checksum mismatch.")
        if name.endswith(".json"):
            parsed[name] = json.loads(data)
        else:
            data.decode("utf-8")
    crawl, packet, audit, inputs = (parsed[name] for name in
                                    ("crawl.json", "packet.json", "audit.json", "input.json"))
    expected_summary = {"crawl_pages": len(crawl["pages"]), "packet_pages": len(packet["pages"]),
                        "audit_status": audit["status"], "score": audit["score"]}
    if (manifest["output_summary"] != expected_summary
            or manifest["input_summary"]["sha256"] != manifest["files"]["input.json"]["sha256"]
            or manifest["budgets"] != inputs["crawl_budgets"]
            or manifest["exact_origin"] != crawl["exact_origin"]
            or manifest["seed_url"] != crawl["seed_url"]
            or manifest["resources"] != crawl["resources"]
            or manifest["robots_status"] != crawl["robots_status"]
            or manifest["stop_reason"] != crawl["stop_reason"]
            or manifest["budget_exhausted"] != crawl["budget_exhausted"]
            or manifest["truncation"]["packet_truncated"] != packet["truncated"]
            or manifest["failures"] != crawl["failures"]
            or manifest["audit_coverage"] != [e["check_key"] for e in audit["evidence"]]
            or manifest["http_attempt_urls"] != [r["url"] for r in parsed["requests.json"]]):
        raise ValueError("Audit manifest does not match exported results.")
    return manifest
