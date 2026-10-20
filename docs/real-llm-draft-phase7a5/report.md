# Phase 7-A.5 JSON Contract Stabilization — TEST ONLY

**PHASE7A5_JSON_CONTRACT_STABILIZATION_COMPLETE**

Outcome: **OFFLINE_PASS**. Real-model JSON compliance: **NOT_TESTED**. Separate live-request authorization: **PENDING**. This completion marker covers prompt stabilization and offline verification only; it is not evidence that DeepSeek reliably returns valid JSON.

The sole generation change appends the user-specified JSON STRING ESCAPING REQUIREMENT to the complete saved Phase7A3 system prompt. The newline instruction contains the two literal characters backslash and n. The saved A.3 user message remains identical, including its historical Phase 7-A.2 experiment metadata label. Every A.3 internal metadata boundary instruction remains intact. Model settings remain deepseek-flash, temperature=0, thinking={type:disabled}, response_format={type:json_object}, max_tokens=3000. No production Draft adapter was changed.

New files exist only under docs/real-llm-draft-phase7a5/: candidate prompt.py/prompt.json, prompt.diff, test_json_prompt_contract.py, verify_offline.py, frozen-input snapshots, candidate request.json, live-request-proposal.json, admission-revalidation.json, offline test log/result, preservation baseline, this report, verification and manifests. The Python files provide the isolated candidate prompt and offline tests; they do not add a live sender or alter runtime behavior. No existing code, admission, evidence, gate, validator, output parser, retry implementation or editorial engine was edited. A.2, A.3 and A.4 historical artifacts and original Phase6 workspace files remain unchanged.

Verification actually executed:

```powershell
.\.venv\Scripts\python.exe -B docs/real-llm-draft-phase7a5/verify_offline.py
```

| Suite | Tests | Result |
|---|---:|---|
| A.5 prompt contract and strict JSON controls | 7 | PASS |
| Unchanged A.3 regression assertions against A.5 candidate | 7 | PASS |
| Existing single-request experiment regression | 10 | PASS |
| A.1 admission regression | 26 | PASS |
| Phase6 regression | 27 | PASS |
| Phase3 editorial regression | 26 | PASS |
| Total | 103 | 0 failures, 0 errors, 0 skipped |

OfflineGuard and explicit guards blocked real HTTP, credential access, production Writer, WordPress and historical live senders. Observed network attempts and forbidden calls: 0. The test suites use local fixtures and mock transports. The escaped JSON control is hand-authored, not model output. The original A.4 malformed response still fails strict parsing at position 87. Unescaped quotes, extra fields, duplicate keys and code fences still fail Layer 1. No JSON repair, regex extraction, fallback parser or relaxed validation was introduced. A.3's leaked historical article is read only by its negative regression control, never as a new model input. Editorial fixture PASS is a regression result, not this experiment's generated-content approval. Full repository suite was not run.

The persisted A.1 READY input/result were deserialized and require_ready(input, result) recomputed successfully. Frozen input bytes, request and prompt hashes are retained. Existing file inventories and Git HEAD in the current repository and original Phase6 workspace match the preservation baseline; user changes are preserved. The historical Phase7A request remains excluded from content reads under the original inventory policy; its stat metadata is preserved. No credentials were read.

No live request is authorized by this offline phase or executed. The concrete request.json is prepared for review, and live-request-proposal.json specifies exactly one HTTP POST, zero retry, no fallback and no repair. Separate user authorization is required by the current user instruction. If authorized later, validate the unchanged READY envelope and all frozen hashes before the sole request. Run strict Layer 1 first: failure stops the experiment immediately; PASS permits Layer 2–4 in order, stopping at the first failure. Save raw response, model content, usage, latency, hashes and each reached layer result. These later checks do not broaden the A.5 objective to SEO quality, evidence quality or editorial approval.

A single successful future response can establish only that this particular request returned valid JSON; it cannot establish a statistical stability rate. The A.4 failure remains unchanged. No SEO/evidence/editorial quality result or live-model PASS is claimed here. semantic_approved=false, production_authorized=false and the saved live_execution_authorized=false remain unchanged.

```yaml
real_api_calls: 0
production_writer_calls: 0
wordpress_calls: 0
deployment: false
git_commit: false
git_push: false
```
