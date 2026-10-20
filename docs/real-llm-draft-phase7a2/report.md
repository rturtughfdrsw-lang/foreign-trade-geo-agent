# Phase 7-A.2 real LLM Draft experiment — TEST ONLY

**PHASE7A2_REAL_LLM_DRAFT_TEST_COMPLETE**

**TEST FAIL — first failed layer: 4 (Editorial Review).** Failure code: `P7A2_EDITORIAL_INTERNAL_LANGUAGE_LEAK`.

The unchanged Phase 3 `review_article` returned `NEED_REVISION`: paragraph P002 contains the internal phrases “test-only” and “production authorization”, severity MEDIUM. These phrases are forbidden in reader-facing prose by the existing engine, including scenario notices. The failing original paragraph is preserved in `article.md` and `evidence-audit.json`; the exact native finding is in `editorial-review.json`. Stop on this failure. No prompt/code/article edit, automatic repair, retry or fallback followed the real request. The remaining supplemental editorial rubric was not run after the native failure.

| Layer | Result | Evidence |
|---|---|---|
| 1 — JSON contract | PASS | Strict parsing; sole top-level field `article`; no extra fields |
| 2 — Draft contract | PASS | Article-only string, 2754 UTF-8 bytes, 384 words, 14 paragraphs; H1/H2/prose structure |
| 3 — Evidence boundary | PASS (recorded Codex agent audit) | All six admitted claims retain fictional/configuration scopes; no unauthorized claim, unsupported numeric or scope expansion found |
| 4 — Phase 3 Editorial Review | FAIL / NEED_REVISION | INTERNAL_LANGUAGE_LEAK at P002; later rubric stopped |

## Request and provenance

The persisted Phase 7-A.1 READY envelope and saved result were deserialized and `require_ready(input, result)` recomputed successfully, including again before the request and final verification. The snapshot's `semantic_approved=false`, `production_authorized=false` and saved `live_execution_authorized=false` were verified and retained. Separate user authorization covered only this single TEST ONLY model request. Existing Evidence-001–004, Decision Record, versions/scopes/hashes and frozen manifests were not edited.

A new request was built from admitted claims, evidence-bound scopes and original record, not from the historical Phase 7-A request. Input evidence is **synthetic**; the real component here is the LLM API request, not customer evidence or factual verification of HEDELIUS. The Phase 3 engine was loaded from the unchanged, hash-verified Phase 5 baseline. No legacy sentence schema or record identity was fabricated. The Phase 6 exact-paragraph fixture checker remains unchanged; requested natural-prose evaluation uses Phase 3 plus the separately recorded evidence audit specified before execution.

Provider `deepseek`; model requested/reported `deepseek-flash`; temperature `0`; thinking `disabled`; JSON-only response format; `max_tokens=3000`. HTTP 200, finish_reason `stop`, latency **4.922 seconds**. Input tokens **3217**, output tokens **488**, total **3705**. No monetary estimate was made. Prompt SHA256: `27bdf8100db09875a258d2ee0fb77966f1c22eebce1c1002ffab5fbf3cd21742`. Article SHA256: `ac721cca5ae5de3c80a76db7c8897b3d5d698430db6b3b123d5795367a002e6e`. Full request/content/raw-response hashes are in `verification.json`.

The durable exclusive-create attempt marker and one-shot transport cap the experiment at one POST. Retries, redirects, automatic repair and fallback were disabled. Raw non-secret provider response, unchanged model content, article, usage, latency, metadata and validation are preserved. Credential values and authorization headers were not printed or persisted.

## Verification actually run

Final guarded offline suite: **89 tests, 0 failures, 0 errors, 0 skipped**: experiment harness 10, Phase 7-A.1 admission 26, Phase 6 regression 27, Phase 3 review 26. Earlier intermediate runs passed 88 tests and 10 focused tests. No offline test made a real API call. The full repository suite was not run. `offline-final-tests.log` records the final suite. Frozen-file hashes, unchanged existing files in both workspaces and unchanged Git HEADs were verified after the request. Only the new `docs/real-llm-draft-phase7a2/` directory was added; no production code path was modified.

## Safety result

```yaml
real_api_calls: 1
production_writer_calls: 0
wordpress_calls: 0
deployment: false
git_commit: false
git_push: false
semantic_approved: false
production_authorized: false
live_execution_authorized: false
```

## Disclosed deviation and limits

The first offline preservation inventory hashed historical docs as opaque bytes, including the old Phase 7-A request. It did not display, deserialize or use that request to generate the experiment. This was a deviation from the strict no-read instruction. Before freezing or making the API call, the final inventory excluded its content and retained only size/mtime; a focused test verifies the exclusion. No historical request was used as input.

Evidence-layer PASS is an agent test assessment, not human approval or a general semantic proof. The native Phase 3 engine detects limited patterns and cannot independently establish all claims/applicability. Here its blocking finding stopped editorial acceptance; this is **not TEST PASS**, production readiness or permission for any later API request. No real customer crawl, WordPress, deployment, production Writer, commit or push occurred. All original authorization flags remain false.

Artifacts: `frozen-input/`, `request.json`, `prompt.json`, `frozen-manifest.json`, `request-metadata.json`, `attempt-consumed.json`, `response.raw.json`, `model-response.txt`, `article.md`, `response-metadata.json`, `usage.json`, `validation-initial.json`, `evidence-audit.json`, `editorial-review.json`, `validation-result.json`, `failure-logs.json`, `verification.json`, `artifact-manifest.json`, offline test logs, protocol and isolated experiment/test scripts. No further execution is authorized by these artifacts.
