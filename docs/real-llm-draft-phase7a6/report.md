# Phase 7-A.6 Evidence Composition Boundary Prompt Test

**PHASE7A6_EVIDENCE_COMPOSITION_BOUNDARY_COMPLETE**

**OFFLINE_PASS. Real model: NOT_TESTED. Separate live request authorization: PENDING.**

This marker means the isolated prompt addition and requested offline verification are complete. It does not mean DeepSeek has stopped composing quantities or collection/coverage claims. The historical A.5 Layer 3 failure remains unchanged.

The sole generation change appends exactly the requested EVIDENCE COMPOSITION RULE to the full frozen A.5 system prompt. It prohibits calculating, counting, aggregating, summarizing or inferring quantities from evidence items; permits a quantity only when explicitly supported by an admitted claim; and prevents record multiplicity from implying multiple products/configurations, all products, complete coverage or every case. Each supported item should be described individually when needed. The A.3 internal metadata boundary, A.5 JSON escaping requirement and entire saved user message are retained. The user message's historical Phase 7-A.2 experiment label remains unchanged to preserve variables. No production Draft adapter was edited.

The four requested offline cases are saved in offline-cases.json as authored expectations, explicitly not model outputs:

| Case | Input example | Forbidden expectation | Allowed authored example |
|---|---|---|---|
| 1 | ACURA and TILTENTA items | two configurations | ACURA and TILTENTA are described separately |
| 2 | document A, B, C items | three documents show | Describe an individually supported configuration claim without a document count |
| 3 | product A and B items | all products | Describe the documented product individually |
| 4 | Admitted ACURA five-axis claim | Removing or inventing quantities | Retain the admitted five-axis claim unchanged |

These cases assert that the candidate contains the explicit composition constraints and quantity exception, and that their hand-authored expected examples have the specified form. They do not run a model, establish semantic inference automatically, or install an output classifier/filter. In particular, the tests do not prove that the real model will avoid the forbidden examples. The supported-number case verifies that the original admitted five-axis claim remains in the frozen user input and is retained in the authored example. No Evidence or Admission fixture is modified.

Verification command actually run:

```powershell
.\.venv\Scripts\python.exe -B docs/real-llm-draft-phase7a6/verify_offline.py
```

| Suite | Tests | Result |
|---|---:|---|
| A.6 cases and prompt preservation | 8 | PASS |
| A.5 JSON contract regression | 7 | PASS |
| A.3 boundary regression | 7 | PASS |
| Existing one-shot experiment regression | 10 | PASS |
| A.1 admission regression | 26 | PASS |
| Phase6 regression | 27 | PASS |
| Phase3 regression | 26 | PASS |
| Total | 111 | 0 failures, 0 errors, 0 skipped |

A.5/A.3 original assertions, including their historical exact-delta checks, run unchanged against the preserved A.5 candidate. A.6's new tests separately verify the exact A.5-to-A.6 append, full A.3/A.5 boundary preservation and unchanged user input/model settings. No original assertion was removed or weakened. The original A.4 malformed JSON and A.2 internal language leak remain negative regression controls, not new request inputs. OfflineGuard and explicit guards prohibit sockets/DNS, real HTTP, credential reads, production Writer, WordPress and historical live senders. Observed network attempts, forbidden calls and real API calls are zero. No full repository suite was run. Regression editorial PASS is fixture behavior, not generated-article approval.

The persisted Phase7A1 READY admission envelope and result are loaded, their artifact/implementation hashes verified, and require_ready(input,result) recomputed successfully. Current repository and original Phase6 workspace file inventories and Git HEAD remain identical to the before baseline. A.2 through A.5 artifacts are preserved; the complete A.5 live manifest was checked. The historical Phase7A request remains excluded from content reads under the original inventory policy, with stat metadata preserved. No credentials were read.

All additions are under docs/real-llm-draft-phase7a6/: prompt.py/json/diff, test_composition_prompt.py, verify_offline.py, offline case expectations/test log/results, frozen input snapshots, reviewable request.json, live-request-proposal.json, admission revalidation, preservation baseline, this report and verification/manifests. The Python files support the isolated candidate and offline tests only; no live sender is added. Evidence, Admission, Gate, validators, parser, Editorial Review, retry logic and output filtering remain unchanged.

The proposed unsent request uses model=deepseek-flash, temperature=0, thinking={type:disabled}, response_format={type:json_object}, max_tokens=3000. A separately authorized real experiment would allow exactly one HTTP request, no retry, fallback or repair, and stop at the first failed Layer 1–4. Frozen hashes and require_ready must pass again before sending. This phase performs no real request and cannot consume or reuse A.5's already-spent live authorization. User authorization is requested only after this concrete prompt/request and offline result are reviewable, as explicitly required by the A.6 user instruction.

semantic_approved=false, production_authorized=false and the saved envelope's live_execution_authorized=false remain unchanged. The main limitation is unverified real-model behavior; offline assertions cannot establish live evidence-composition compliance or customer-publication quality.

```yaml
real_api_calls: 0
production_writer_calls: 0
wordpress_calls: 0
deployment: false
git_commit: false
git_push: false
```
