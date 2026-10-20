# Phase 7-B Draft Claim Audit — TEST ONLY design

The executable prototype is `claim_audit.py`, isolated in this experiment directory. It is a pure offline function, with no provider, storage, parser, prompt, rewrite or production-workflow dependency. Existing admission, evidence, prompts, JSON parsing and Editorial Review remain unchanged.

## Placement and authority

Proposed flow: Evidence Admission → LLM Draft → existing strict JSON/Draft contract checks → Draft Claim Audit → Editorial Review. No runtime wiring is installed in this phase.

The caller must recompute the existing READY receipt and supply the corresponding immutable admitted claims and scopes. Audit does not authenticate a caller's claim list or grant admission. Trust cannot be created by passing invented claims to this function. Before consuming a stored result, recompute its binding from the same claims, scopes and exact article; changed inputs invalidate the result.

Only audit PASS permits the proposed offline handoff to Editorial Review. NEEDS_REVIEW holds for explicit human evidence/scope review; REJECTED stops. Neither state triggers automatic deletion, rewrite, retry or fallback. No status changes semantic_approved, production_authorized or live_execution_authorized. Even Editorial PASS is not publication authorization.

## Input and output contract

`audit(admitted_claims, allowed_scope, generated_article) -> AuditResult`

- `admitted_claims`: tuple of immutable Claim values: claim_id, claim_text, applicable_scope, evidence_refs. Existing evidence-bound claims are projected into these local types for testing; no persisted source object is modified. Confidence/provenance verification remains with upstream Admission; this audit does not replace it.
- `allowed_scope`: tuple of Scope(category, subject), matching each claim's scope exactly.
- `generated_article`: the unchanged string supplied after strict JSON parsing. This function accepts no raw JSON and implements no JSON extraction.
- Result: status, immutable findings, exact article SHA256, canonical input SHA256 and fixed false approval/authorization flags. Findings contain code, paragraph_ref, normalized matched signal, original excerpt, candidate_claim_ids. IDs identify claims considered for support, not new support assertions. Evidence references remain available through those immutable input claims. There is no rewritten article field.

| Status | Meaning in this prototype | Next step |
|---|---|---|
| PASS | No unresolved or unsupported signal in the implemented repertoire | Existing Editorial Review, still TEST ONLY |
| NEEDS_REVIEW | A candidate quantity exists but context/scope is not safely established, a sentence is negated/conditional/quoted/a question, language is outside the English repertoire, or the finding budget is exhausted without a definite rejection | Hold for human review |
| REJECTED | Detected affirmative quantity/collection claim has no corresponding explicit admitted quantity, or input is invalid | Stop |

REJECTED dominates NEEDS_REVIEW. Findings are ordered by paragraph, with collection matches preceding remaining quantity tokens. Input-invalid errors are bounded and sanitized; their bindings are null. Valid inputs always produce article and full input bindings, including on rejection.

## First-stage detection and support rules

Normalize NFKC, case, whitespace and common dash forms only for comparison. Never normalize the returned article: no article is returned or rewritten. Paragraph references index nonempty blank-line blocks. Excerpts retain original sentence text up to 240 characters; the matched signal is normalized. The function does not promise byte offsets after Unicode normalization.

The bounded English repertoire recognizes digit quantities, number words zero through twenty plus hundred/thousand/million, axis quantities, and common aggregation terms. Collection expressions pair quantifiers such as two, three, multiple, all and every with products, configurations, solutions, cases, documents, records and related nouns. Complete coverage, totals, counts and sums are also signals. This includes all six requested prohibited examples. Separate supported items never become a synthesized count.

An explicit collection exception requires both a whole normalized sentence equal to one admitted claim and that claim's scope subject explicitly present in the sentence. A matching substring is insufficient: same quantity with another subject, lost qualifier, or unresolved scope returns NEEDS_REVIEW. This is intentionally conservative; it does not prove arbitrary entailment.

The requested numeric-attribute positive control has a narrow grammar: an admitted `five-axis machining` phrase with scope subject ACURA supports `ACURA supports five-axis machining.` The same rule applies to the recognized number-axis form with the exact admitted phrase and subject. It does not authorize another subject, a different unit, new capability, inferred count, or an unrelated numeric claim. An exact whole scoped admitted numeric claim also passes.

Unmatched affirmative signals return UNSUPPORTED_CLAIM. If a matching admitted signal exists but the exact scope/wording rule cannot prove correspondence, return CLAIM_CONTEXT_REQUIRES_REVIEW. Negation, quotes, questions and modal/conditional markers similarly require review, preventing a negative caveat such as “not all products” from being treated as an asserted universal capability. This lexical ambiguity rule can conservatively hold benign prose.

## Bounds and safety

Inputs: 1–32 claims, 1–32 scopes, 1–16 evidence references per claim, 4096 UTF-8 bytes per claim text, 65536 article bytes, 512 paragraphs; IDs and scope fields have smaller explicit bounds. Empty values, duplicate claim IDs/scopes, invalid types, disallowed control characters and out-of-scope claims reject. Findings cap at 128 with an explicit budget marker. Dataclasses and tuples are immutable. No credential reads, external I/O or model calls exist in the audit module.

## Validation

The four required examples run through the actual audit function:

1. ACURA + TILTENTA with “Two configurations are described.” → REJECTED.
2. Scoped claim “Five-axis machining” with “ACURA supports five-axis machining.” → PASS.
3. “selected configurations” with “All configurations support automation.” → REJECTED.
4. “ACURA and TILTENTA are described separately.” → PASS for this quantity/collection-only audit.

Additional tests cover all requested terms, explicit supported exceptions, subject mismatch, lost qualifiers, absent scope anchor, negation/questions/quotes, formatting variants, no cross-claim aggregation, malformed/bounded inputs, foreign-language hold, deterministic bindings, non-mutation and finding limits. Frozen A.5/A.6 actual articles are replayed offline; both must reject their historical configuration-count spans. Existing A.6/A.5/A.3, admission, Phase6 and Phase3 regressions run unchanged.

## Limits and future decision

This is an executable design prototype, not a production semantic firewall. PASS is restricted to the detector vocabulary and grammars. Unrecognized idioms (for example “a duo”), indirect/pronominal scope, complex tables, multilingual paraphrases, and novel collection expressions can escape detection. Unrelated false claims without a quantity signal also pass this narrow stage. No evidence-quality, SEO-quality, numerical performance, universal language or whole-article fidelity certification is claimed.

Exact-string support deliberately sends many legitimate paraphrases to review. Lexical modality detection can also send an unsupported claim to review rather than rejection; both outcomes block automatic progression. The present caller-owned claims are trusted only after the upstream gate. Production integration, broader grammar coverage, calibrated false-positive/false-negative evaluation and human disposition persistence require a later explicit task. No additional prompt rules or live experiment are proposed in this phase.
