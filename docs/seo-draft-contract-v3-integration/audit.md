# Phase 0 — read-only source audit

2026-10-12 (Asia/Shanghai). Completed before any source/test changes. Existing
tracked edits and untracked files are preserved; baseline-sha256.json records
every existing non-ignored file before this directory was created.

## 1. Current v2 offline entry points

- `workflows/draft_contract_v2.py::build_offline_writer_material`: validates the
  Selection Contract and projects selected-only facts plus unchanged native P/S
  context, budgets, limitations and verification actions. It never calls a Writer.
- `workflows/draft_contract_v2.py::inspect_offline_candidate`: native parsing,
  candidate inspection, routing/reservations and v2 explanation validation.
- `scripts/prepare_seo_draft_v2_flash_preflight.py::parse_experiment_response`:
  strict `{candidate, explanations}` experimental envelope and v2 sidecar binding.
  `load_inputs` and `build_request` prepare the existing preflight; none needs edits.
- Existing tests: `test_draft_contract_v2`, `test_seo_draft_v2_flash_preflight`.

## 2. Calling v3

`core/draft_explanation_contract_v3.py` exposes `decode_sidecar_v3`,
`encode_sidecar_v3`, and `inspect_explanations_v3(sidecar, selection, raw,
specification, value, current_snapshot_sha256=...)`. Version is
`seo-draft-explanation-v3-offline`. The strict codec rejects unknown fields,
including approval fields. The inspector binds candidate/context/text hashes,
selected facts, source quotes, controlled visible decision/boundary/verification
realization, native checks and section reservations. PASS is structural only;
its successful state is PENDING_SEMANTIC_REVIEW and both authority flags are false.

Important ordering dependency: the full inspector requires a native parsed
specification and itself calls `inspect_specification`. Therefore the integration
must perform v3 codec/hash prechecks before native parsing, then full v3 checking
after parsing, then record an independent final native validator check. It cannot
honestly claim to run the full existing v3 inspector before parsing. No production
contract changes are needed to accommodate this dependency.

## 3. Native schema

No change required. The isolated envelope contains `candidate: {draft: ...}` and
an independent `v3_sidecar`. Only canonical native candidate JSON reaches
`workflows/content_draft.py::_parse_specification`; experimental decision fields
must never enter candidate claims or the draft object. Keep existing proposal
metadata required by the native review path.

## 4. Compatibility boundaries and insertion point

Add only `workflows/draft_contract_v3_experiment.py`, new tests, and local artifacts.
Reuse v2 writer projection without mutating its returned semantics or implementation;
add v3 instructions in a separate material object. Accept already decoded Selection
Artifact at the workflow boundary; the local artifact driver uses the unchanged
storage codec. Capture each step as an immutable JSON snapshot for local persistence.

Native parser: `_parse_specification` in `workflows/content_draft.py`.
Native validator for unapproved proposals: `core/draft_candidate_review.py::
inspect_specification`, which delegates to existing evidence and article-quality
checks in `core/content_draft.py`. Do not call the admitted DraftItem finalizer:
that path requires human decisions. Parser compatibility and deterministic review
validation do not establish semantic approval or delivery eligibility.

Must preserve: v2 selection/sidecar codecs and behavior, Writer, parser/Validator,
Gate, runtime/CLI registration, storage schema, draft JSON, frozen-v1 output and
original v2 model envelope/rejection. No network transports, credentials, runtime
registration, WordPress, approval transitions or live-request builder in the new
workflow. Workflow states are OFFLINE_ONLY (including rejected attempts) and
PENDING_SEMANTIC_REVIEW only; explicit errors distinguish failed offline attempts.

Synthetic positive input can reuse `tests/draft_explanation_v3_fixtures.py::fixture_v3`
(6 sections / 12 chains). Historical bytes are replayed unchanged, never repaired.
No production-file edit is necessary; stop if implementation reveals otherwise.
