# Phase 7-A.3 — offline result

**PHASE7A3_PROMPT_BOUNDARY_COMPLETE**

Offline prompt-contract/fixture verification: **PASS**. Real DeepSeek behavior: **NOT TESTED**. The Phase7-A.2 real-model outcome remains **TEST FAIL**; its original article and consumed attempt are unchanged.

The candidate adds an explicit internal-metadata/reader-facing boundary to the preserved A.2 Draft system prompt. It forbids the nine requested internal terms, status values and workflow discussion, including in disclaimers or translated/paraphrased forms. It retains evidence-supported product content, scope limits, the fictional scenario notice, unresolved buyer questions and prospective technical-documentation requests. The saved user message and model settings remain identical. No output filtering, validator change or Editorial Review relaxation was used.

All changes are additions under `docs/real-llm-draft-phase7a3/`: `prompt.py`, candidate `prompt.json`, `prompt.diff`, `design.md`, `test_prompt_boundary.py`, `verify_offline.py`, red/final test JSON and logs, `verification.json` and this report. No existing source, test, evidence, Decision Record, admission contract, gate or review-engine file was edited. Preservation inventories across the current repository, original Phase6 worktree and A.2 artifacts match before/after; existing user changes were preserved.

Verification command actually run:

```powershell
.\.venv\Scripts\python.exe -B docs/real-llm-draft-phase7a3/verify_offline.py offline-final-tests
```

| Suite | Tests | Result |
|---|---:|---|
| A.3 prompt boundary, four cases and controls | 7 | PASS |
| A.2 experiment regression | 10 | PASS |
| A.1 admission regression | 26 | PASS |
| Phase6 regression | 27 | PASS |
| Phase3 editorial regression | 26 | PASS |
| Total | 96 | 0 failures, 0 errors, 0 skipped |

The A.1/6/3 modules are loaded from the original `C:/Users/31969/.codex/worktrees/phase6-e2e/foreign-trade-geo-agent` workspace by the preserved A.2 harness. Full repository suite was not run. The negative control confirms the original leaked A.2 article still receives native `NEED_REVISION` / `INTERNAL_LANGUAGE_LEAK`. The clean authored Phase6 fixture receives native PASS.

Earlier verification: the first exploratory discovery reported four missing-boundary failures plus three test-authoring errors (incorrect helper name and missing empty boundary constant); those test errors were corrected. The recorded guarded red suite then reported 96 tests, four expected boundary failures, zero errors and 89 original regression passes. After the prompt addition, the same guarded suite passed all 96 tests. Logs are retained; no tests or valid assertions were removed.

Artifact export initially resolved the A.2 `verify_offline` module instead of A.3 because the historical harness changes the import search path. Its guarded offline runner executed, then exclusive-create protection rejected the existing A.2 log with `FileExistsError`; no historical artifact was overwritten. Export was corrected to load A.3 by explicit absolute module path, and the final existing-file inventory was checked again. This was a tooling error, not a model retry or API request.

The four cases inspect prompt instructions and hand-authored fixture expectations. They do **not** generate an article from their metadata inputs and do **not** demonstrate that DeepSeek now suppresses those terms. No fake model output is presented as model evidence. The hypothesis needs one separately authorized real-model experiment, with the unchanged gates and editorial engine. This phase stops here; no live request, retry or live execution entry point was added.

Observed offline counters: real API calls 0; network attempts 0; forbidden guarded calls 0; production Writer 0; WordPress 0. No deployment, commit or push. Semantic approval, production authorization and live execution authorization remain false. Customer-publication quality is a prompt requirement, not publication approval or proof that synthetic evidence is suitable for a real customer.
