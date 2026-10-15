"""Bounded one-shot DeepSeek response retention, shared by isolated runners.

No credentials or authorization are loaded here. Callers supply the transport,
exact request bytes and native validator; raw files are never HTTP resources.
"""
import hashlib
import inspect
import json
import os
import re
import subprocess
from datetime import UTC, datetime

import httpx
from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter
from foreign_trade_geo_agent.core import content_draft as cd

ENDPOINT = "https://api.deepseek.com/chat/completions"
MAX_REQUEST_BYTES = 16_000
# JSON escaping and the provider envelope need space beyond native model text.
MAX_RESPONSE_BYTES = 256 * 1024


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class OneShotTransport(httpx.AsyncBaseTransport):
    """Exact bytes, one attempt (including errors), no alternate endpoint."""
    def __init__(self, inner, expected, *, expires_at=None, request_limit=MAX_REQUEST_BYTES):
        require(type(request_limit) is int and 0 < request_limit <= cd.MAX_INPUT_ENVELOPE_BYTES,
                'SINGLE_REQUEST_GUARD')
        self.inner, self.expected, self.calls = inner, expected, 0
        self.expires_at = expires_at
        self.request_limit = request_limit

    async def handle_async_request(self, request):
        require(self.expires_at is None or datetime.now(UTC) < self.expires_at,
                "LIVE_AUTHORIZATION_EXPIRED_OR_MISSING")
        require(self.calls == 0 and request.method == "POST" and str(request.url) == ENDPOINT
                and request.content == self.expected and len(request.content) <= self.request_limit,
                "SINGLE_REQUEST_GUARD")
        self.calls += 1
        return await self.inner.handle_async_request(request)

    async def aclose(self):
        await self.inner.aclose()


def restrict_directory(directory):
    """Fail closed before HTTP: only the current local account can read results."""
    if os.name == "nt":
        import csv
        identity = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True, check=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        sid = next(csv.reader(identity.stdout.splitlines()))[1]
        require(re.fullmatch(r"S-1-[0-9-]+", sid) is not None, "LOCAL_ACCESS_RESTRICTION_FAILED")
        subprocess.run(["icacls", str(directory), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"],
            capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        directory.chmod(0o700)


def save_bytes(path, raw):
    # Exclusive creation also protects against accidental reuse within an attempt.
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def contains_secret(raw, key):
    # Scan escaped ASCII too, without invoking a parser before raw retention.
    decoded = raw.decode("utf-8", errors="replace")
    decoded = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), decoded)
    decoded = decoded.replace('\\"', '"').replace("\\/", "/")
    return key in decoded or re.search(
        r"(?i)bearer\s|(?:api[_ -]?key|password|authorization|cookie|set-cookie)[\s\"']*[:=]|\bsk-[A-Za-z0-9_-]{8,}",
        decoded) is not None


def retain_response(output, metadata, raw, key, *, complete):
    metadata.update(response_state="COMPLETE_RESPONSE" if complete else "PARTIAL_RESPONSE",
                    response_bytes=len(raw), response_complete=complete)
    if metadata.get("content_encoded"):
        metadata.update(response_state="WITHHELD_UNINSPECTABLE", response_saved=False,
                        failure_stage="response_safety")
        raise ValueError("ENCODED_RESPONSE_REFUSED")
    if contains_secret(raw, key):
        # Never redact/rewrite the envelope and call it original. Explicit refusal.
        metadata.update(response_state="WITHHELD_SECRET", response_saved=False, failure_stage="response_safety")
        raise ValueError("SECRET_OUTPUT_REFUSED")
    save_bytes(output / "response-body.bin", raw)
    metadata.update(response_saved=True, response_sha256=sha(raw))

async def receive_candidate(value, raw_request, transport, key, *, output, metadata, validator,
                            detail, timeout=60.0, response_limit=MAX_RESPONSE_BYTES):
    require(type(response_limit) is int and 0 < response_limit <= MAX_RESPONSE_BYTES, 'RESPONSE_BUDGET_INVALID')
    chunks, size, complete, received = [], 0, False, False
    metadata["failure_stage"] = "http_receive"
    try:
        async with httpx.AsyncClient(transport=transport, timeout=timeout,
                trust_env=False, follow_redirects=False, headers={"Authorization": "Bearer " + key,
                                                              "Accept-Encoding": "identity"}) as client:
            async with client.stream("POST", ENDPOINT, content=raw_request,
                                     headers={"Content-Type": "application/json"}) as response:
                received = True
                metadata["http_status"] = response.status_code
                # aiter_raw preserves entity bytes (including any content encoding).
                # MockTransport may return an already-read Response.
                metadata["content_encoded"] = response.headers.get("content-encoding", "identity") != "identity"
                if response.is_stream_consumed:
                    chunk = response.content
                    chunks.append(chunk[:response_limit])
                    size = len(chunk)
                    require(size <= response_limit, "RESPONSE_BUDGET_EXCEEDED")
                else:
                    async for chunk in response.aiter_raw():
                        remaining = response_limit - size
                        chunks.append(chunk[:max(0, remaining)])
                        size += len(chunk)
                        require(size <= response_limit, "RESPONSE_BUDGET_EXCEEDED")
                complete = True
    finally:
        if received:
            metadata["response_budget_exceeded"] = size > response_limit
            metadata["failure_stage"] = "response_persistence"
            retain_response(output, metadata, b"".join(chunks), key, complete=complete)
            metadata["failure_stage"] = "http_receive"
    raw = b"".join(chunks)
    metadata["failure_stage"] = "provider_json"
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, json.JSONDecodeError):
            metadata["json_error"] = {"line": exc.lineno, "column": exc.colno, "offset": exc.pos}
        require(metadata["http_status"] == 200, "PROVIDER_HTTP_FAILURE")
        raise ValueError("PROVIDER_JSON_FORMAT") from None
    usage = body.get("usage") if type(body) is dict else None
    metadata["usage"] = {k: v for k, v in usage.items() if k in {
        "prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"}
        and type(v) is int and 0 <= v <= 1_000_000} if type(usage) is dict else None
    choices = body.get("choices") if type(body) is dict else None
    finish = choices[0].get("finish_reason") if type(choices) is list and choices and type(choices[0]) is dict else None
    metadata["finish_reason"] = finish if type(finish) is str and finish in {
        "stop", "length", "tool_calls", "content_filter", "insufficient_system_resource"} else None
    extracted = DeepSeekContentDraftWriter._extract_text(body)
    if extracted is not None:
        metadata["failure_stage"] = "model_text_persistence"
        save_bytes(output / "model-output.txt", extracted[0].encode("utf-8"))
        metadata["model_text_sha256"] = sha(extracted[0].encode("utf-8"))
    metadata["failure_stage"] = "provider_envelope"
    require(metadata["http_status"] == 200, "PROVIDER_HTTP_FAILURE")
    require(type(body) is dict and body.get("model") == "deepseek-flash"
            and type(body.get("choices")) is list and len(body["choices"]) == 1,
            "PROVIDER_ENVELOPE_INVALID")
    require(extracted is not None and extracted[1] == "stop", "OUTPUT_INCOMPLETE")
    metadata["failure_stage"] = "native_validation"
    try:
        report = validator(value, extracted[0])
        if inspect.isawaitable(report):
            report = await report
    except Exception as exc:
        # Exact candidate, including whitespace/newlines; no repair or retry.
        metadata["failure_stage"] = "rejected_candidate_persistence"
        save_bytes(output / "rejected-candidate.txt", extracted[0].encode("utf-8"))
        metadata["failure_stage"] = "native_validation"
        category = str(exc) if type(exc) is ValueError and str(exc) in {
            c.value for c in cd.ContentDraftValidationCategory} else "NATIVE_VALIDATION_FAILED"
        metadata["validation_detail"] = detail(value, extracted[0], category)
        raise
    return report, extracted[0], metadata["usage"]

