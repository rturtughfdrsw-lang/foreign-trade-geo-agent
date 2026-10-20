# Phase 7-A.6 — Single real DeepSeek request

**PHASE7A6_BLOCKED — TEST FAIL**

Layer 1 JSON contract: **PASS**. message.content passes the unchanged strict JSON parser, its only top-level key is article, and article is a string. No JSON extraction, relaxed parser or repair was used.

Layer 2 Draft contract: **PASS**. The article contains one H1, H2 sections and prose, with 2959 UTF-8 bytes, 10 blank-line paragraphs and 408 whitespace-delimited words, within the existing 65536-byte/512-paragraph limits. article.md is the unchanged article value obtained by strict JSON parsing.

**First failure: Layer 3. Code: P7A6_EVIDENCE_UNSUPPORTED_NUMERIC.**

P004 contains this assertion:

> Within the synthetic documentation, two configurations are described.

ACURA and TILTENTA are separately supported admitted claims; no admitted claim explicitly supports a configuration count of two. The model inferred a document/configuration count from the supplied items, violating the exact EVIDENCE COMPOSITION RULE added in A.6. This single live observation demonstrates that this prompt did not prevent the targeted unauthorized count in this run. It does not establish failure rates across models or requests. The failure concerns an inferred quantity, not an invented accuracy specification.

Layer 3 stopped at that first finding. Remaining evidence/collection/coverage assertions were not accepted or comprehensively audited after the stop. Layer 4 Phase3 Editorial Review was **NOT RUN**; no internal-language or reader-facing-quality PASS is claimed. editorial-result.json explicitly records the unexecuted result. The evidence audit is an agent-recorded evaluation using the same strict evidence boundary as prior experiments, not a new automatic validator or actual human approval.

Before execution, require_ready(input,result) recomputed the saved Phase7A1 envelope/result as READY. All frozen hashes passed. Prompt SHA256=`5ebeb45dc758aff6a7a879018db8e6e33aa3e09968a9bff78bb1fcbdeb9dc80c`; request SHA256=`3d3df9afe7149fc2f57f79e3a8b8c9659d8a17f7378c92ef9f433081f811d4ba`. Evidence-001–004 original bytes, artifact hashes, document hashes, v1 versions and applicable scopes were explicitly verified against the saved envelope and original Phase6 inputs. live-preflight-verification.json retains each evidence identity/version/scope/hash. Final verification confirmed them again.

The directly authorized request used exactly the saved Phase7A6 request.json/prompt and Phase7A1 READY envelope. Parameters: deepseek-flash, temperature=0, thinking={type:disabled}, response_format={type:json_object}, max_tokens=3000. HTTP 200; reported model=deepseek-flash; finish_reason=stop; no reasoning content. The unchanged existing executor was invoked from stdin with the A.6 output directory. The durable consumed marker and one-shot transport enforce this attempt's one-request boundary. No prompt/code modification, retry, fallback, repair, output filtering or alternative parsing was performed.

Latency: **4.360 seconds**. Usage: prompt_tokens=3740, completion_tokens=494, total_tokens=4234; prompt cache hit=640, miss=3100. Original provider response is response.raw.json; unchanged model content is model-response.txt; article is article.md. response-metadata.json, usage.json, latency.json, evidence-audit.json, editorial-result.json, validation-result.json, failure-logs.json and live-verification.json record the request, reached layers and stop. live-artifact-manifest.json records their SHA256 hashes.

Current repository and original Phase6 workspace code/tests/docs inventories and Git HEAD match the saved preservation baseline. All A.2–A.5 history and A.6 offline artifact hashes remain unchanged; only new A.6 live records were appended. Original report.md / verification.json remain the offline snapshot; live-report.md / live-verification.json contain this live result. No code, Evidence, Admission, Gate, validator, parser, retry logic or editorial engine was edited. The 111 offline tests recorded in the prior stage remain PASS; no tests or full repository suite were rerun or claimed in this live stage.

semantic_approved=false, production_authorized=false, live_execution_authorized=false remain unchanged in saved artifacts/envelope. The separate user authorization covered only this TEST ONLY request and is now consumed. No production permission is inferred. Stop here.

```yaml
real_api_calls: 1
production_writer_calls: 0
wordpress_calls: 0
deployment: false
git_commit: false
git_push: false
```
