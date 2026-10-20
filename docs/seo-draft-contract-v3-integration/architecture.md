# Isolated v3 experiment architecture

No runtime/CLI registration, provider object, Writer invocation, transport,
delivery, publication or approval transition exists in this path.

```text
Persisted Selection Artifact (unchanged v2 codec, driver boundary)
  -> validate typed Selection Contract + snapshot/Plan/evidence bindings
  -> unchanged v2 selected-only Writer Projection
  -> separate Prompt-v3 material (no provider request)
  -> stored Synthetic LLM envelope
  -> strict v3 sidecar codec + sidecar/candidate/context hash prechecks
  -> unchanged Native Parser, candidate JSON only
  -> full v3 Explanation Contract (requires parsed spec; includes native checks)
  -> independent unchanged Native Validator review inspection
  -> PENDING_SEMANTIC_REVIEW, human review required
```

The full existing v3 inspector requires parsed specification input. The v3 stage
is therefore split into a pre-parser format/binding check and a post-parser
relation/body inspection. Both are required. The native validator runs inside
that inspector and once more explicitly for a separate native compatibility
artifact. The admitted DraftItem finalizer and production Gate are never called.
`inspect_specification` uses the existing proposal-only review validation, evidence
checks and article-quality rules. Compatibility here means native parsing and
deterministic candidate review, not eligibility for WordPress or production.

## Workflow and persistence boundary

`run_offline_v3_experiment` accepts validated domain input, an already decoded
Selection Contract and stored synthetic envelope text. It has no concrete storage
or adapter dependencies. Every completed step is captured as a frozen JSON string;
failure captures the failed stage and a sanitized local diagnostic. The local
`build_artifacts.py` driver reads historical synthetic fixtures, uses the unchanged
Selection Artifact codec, invokes the workflow, and writes create-only files.
Existing identical files may be verified on replay; changed files cause rejection.

The package stores both the complete synthetic input (validation side) and the
selected-only writer projection/prompt (writing side). Selection audit reasons and
unselected facts never enter prompt material. Stage index hashes bind the on-disk
intermediate files. Reproduce with:

```powershell
.\.venv\Scripts\python.exe docs/seo-draft-contract-v3-integration/build_artifacts.py --output-dir <new-local-directory>
```

This driver imports test fixtures deliberately: it is a local offline reproducibility
tool, not an installed runtime entry point. No live/integration scripts are run.

## Experimental envelope, unchanged native candidate

```json
{
  "contract_version": "seo-draft-explanation-v3-offline",
  "candidate": {"draft": "existing native object"},
  "v3_sidecar": "independent strict v3 sidecar object",
  "sidecar_hash": "SHA256 of canonical complete sidecar UTF-8 JSON",
  "semantic_approved": false,
  "production_authorized": false
}
```

The example abbreviates nested objects. Actual schemas are in synthetic-output.json
and prompt-v3-material.json. Envelope keys are exact; duplicate keys, nonfinite
numbers, invalid version, unknown fields, invalid sizes or authority flags fail
closed. Candidate is canonically serialized, bounded by native output limits and
sent alone to native parsing. Native draft/section/claim/proposal fields stay exact.
No decision_object, boundary_type, verification_owner or verification_artifact
is inserted into candidate. Those remain only in the v3 sidecar.

## Bindings and authority

- Candidate hash binds canonical native JSON bytes, excluding envelope/sidecar.
- Sidecar hash binds canonical complete sidecar bytes; no auto-repair or rehash at
  validation. The synthetic producer computes these hashes before replay.
- Selection/snapshot/Plan hashes are checked against current domain inputs.
- Claim and section IDs, selected facts, evidence quotes and exact visible claim
  text bind the proposed relations to their native article locations.
- PASS means structure is complete. Causal truth, evidence relevance and useful
  procurement reasoning still require a person. Both approval flags must be the
  boolean false. True at the envelope boundary or extra approval fields in the
  sidecar are rejected. Hashes provide consistency, never approval provenance.

Workflow and stage states are only OFFLINE_ONLY and PENDING_SEMANTIC_REVIEW.
Rejected attempts are OFFLINE_ONLY with nonempty errors and accepted=false.
The package's final completion status is OFFLINE_V3_INTEGRATION_READY only after
successful regression; this is distinct from the candidate's review state.

## Limits

The controlled realization contract does not prove arbitrary natural-language
semantics. The positive example has 6 sections, 12 chains, 38 claims and 20 blocks;
it demonstrates compatibility and body binding using synthetic relations. Real
model adherence, generation stability and semantic quality remain unverified.
The old v2 envelope and frozen-v1 bytes remain unchanged and rejected. No migration,
repair, promotion or automatic approval is supported.
