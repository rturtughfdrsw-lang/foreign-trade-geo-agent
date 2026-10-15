# SEO Draft Contract v2 offline implementation

Spec: ../seo-draft-contract-v2-design/report.md; user confirmation and six phases override design-only restrictions.

Goal: OFFLINE_SELECTION_CONTRACT_READY. No live requests, production wiring, prompt changes, Gate changes, SQLite migration, V1 payload changes, WordPress, deployment or Git mutations.

Approved sequence and expected new files:
- [x] Phases 1–2: core/draft_selection_contract.py; tests/test_draft_selection_contract.py. Immutable bounded domain types, binding and routing, hard budgets 48/24; soft diagnostics only.
- [x] Phase 3: workflows/draft_contract_v2.py; storage/draft_selection_contract.py; tests/test_draft_contract_v2.py. Explicit offline material builder and separate strict JSON artifact; selected-only projection.
- [x] Phase 4: core/draft_explanation_contract.py; tests/test_draft_explanation_contract.py. Body/claim/section/premise/candidate binding, structure only.
- [x] Phases 5–6: local fixture loader tests/draft_v2_fixtures.py, frozen replay and bounded failures, related tests and full regression.
- [x] Final report: file preservation, test counts/exit codes, network evidence, limitations.

Ruling: Work in the authorized current checkout and add files only. Required design/native inputs are uncommitted here; a clean worktree would omit them. No branch/history mutation.
Ruling: Keep this plan and progress record in the user-specified report directory, rather than skill scratch directories. No commits or cleanup of user files.
Ruling: Use independent V2 domain types and sidecar; production V1 JSON/parser/validator remain unchanged.
Review focus: full E quotes leaking unselected facts; hashes bound to actual current input rather than caller assertions; soft targets becoming rejection conditions; required-direct duplicate feasibility; annotations detached from visible claim text.

Interfaces: DraftSelectionContract + SectionEvidenceBudget consume ContentDraftInput only at explicit validation; storage serializes V2 only. Offline writer builder consumes artifact plus validated native input and projects a copy. ExplanationContract validates native specification claims. Offline replay uses existing Parser/Validator and returns rejection or PENDING_SEMANTIC_REVIEW, never an admitted DraftItem.

Progress:
- Baseline manifest: 2,445 pre-existing files; branch feat/live-site-analysis; HEAD e78cebd50363a9b3a515d8195fbe54fb346edc06. Baseline-related: 29 tests, exit 0.
- Initial whole-suite baseline: 1,901 tests, exit 1, seven EXPERIMENT_CODE_CHANGED errors. This run overlapped additions to src; source-freeze tests correctly detected edits. Do not describe these as pre-existing defects or a passing baseline. Run stable verification before completion.
- RED: new modules/entry points/codecs absent, import failures recorded. Implementation iteration: incorrect imported output-limit constant repaired; one boundary test partition initially violated per-part word minimum, corrected without changing domain depth limits.
- Review: malformed native containers could escape as TypeError, and impossible required claims/block capacity was not prechecked. Added reproducing tests, then bounded offline exception handling and minimum capacity validation. Native parser and Gate unchanged.
- New tests after review: 54 tests, exit 0 (new-tests-final.json). All external-network attempt counters zero.
- Ruling: Follow user instruction against new Agents; perform author review, no subagent/model review. Remaining limitation: no independent review.
- Ruling: English explanation profile retains design 20/12/20 minimum words and 60–160 overall, max 1,200 characters; these are structural diagnostics, not semantic proof.
- Final verification: 54 new tests, 162 related tests, 1,955 full regression tests; all exit 0, no failures/errors/skips. Initial 7 source-freeze errors did not recur with stable source. Real API/WordPress calls 0; blocked external network attempts 0. Frozen-v1 rejected; V2 mock 38 claims/20 blocks, PENDING_SEMANTIC_REVIEW. Final status OFFLINE_SELECTION_CONTRACT_READY; REAL_REQUEST not authorized.
