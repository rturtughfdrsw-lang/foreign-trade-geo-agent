# Explanation Contract v3 — isolated offline design

## Scope and states

New core module only; no production imports, Gate/Validator edits, transport or v2 replacement. The existing selection, native parser, native evidence rules, routing and budgets remain prerequisites in the offline harness. PASS means **structural procurement chain complete**, followed only by PENDING_SEMANTIC_REVIEW. FAIL means REJECTED. There is no approval capability.

## Decision chain

1. Evidence references bind every interpretation premise to the section's selected facts, exact full source quotes, snapshot, Plan and selection digest. A visible evidence basis states which observation is being used; it is linked to those references, not a claim of entailment.
2. Buyer implication identifies a typed decision object, a proposed change to that decision, and a causal rationale. A controlled reader-visible realization binds those slots in order. A label or keyword bag alone cannot satisfy the relationship model.
3. non_applicability retains the native required limitation, adds a condition and explicit epistemic status. `unknown` is unresolved, never observed failure. `condition_change` is conditional, not proof of failure. This prototype deliberately cannot represent observed failure: that needs separately reviewed failure evidence and is deferred. Common failure-language contradictions produce rejection diagnostics; absence of a detected phrase never proves semantics.
4. Verification names a responsible actor, action, concrete artifact, recipient, next decision object and intended use. These relations must be visible in verification_action. The fixed native procurement action remains present.

## Sidecar

The versioned sidecar retains claim_id, section_id, selected_fact_refs, candidate_hash and text_sha256 (visible interpretation body). It also binds selection_sha256, evidence_snapshot_sha256 and plan_sha256. Fields decision_object, boundary_type, verification_owner and verification_artifact are top-level annotation fields. Nested evidence_reference, decision and verification records carry the relationship slots. Local code computes hashes, never the writer. Candidate hash is over the exact supplied UTF-8 native candidate string, not a reserialized envelope; replay retains the original envelope hash separately.

Every interpretation has exactly one annotation. IDs, section order/headings, exact premise sets and full joined visible text must match. Missing, duplicate, additional, unselected or stale annotations fail closed. Input collections/text/JSON sizes are bounded; strict codec rejects unknown fields, duplicate keys, NaN, unsupported versions and approval fields. Diagnostics contain fixed tokens, never provider text.

## Deterministic limits

This offline prototype uses a controlled realization of explicit relations rather than natural-language keyword scoring or minimum word counts. Free-text slots remain unverified: a maliciously complete AST or a wrong causal rationale can still look structurally complete. Humans must check every premise's relevance, causal entailment, conditions, unknown/false distinction and proposed next step, including the historic S4 coupon error. PASS is not a purchasing-quality verdict. This is a testable design, not an assertion that arbitrary English semantics have been solved.

Examples and generated artifacts are SYNTHETIC / TEST ONLY and never projected into production material. No new production writer projection is implemented.
