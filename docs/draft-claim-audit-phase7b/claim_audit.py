"""TEST ONLY bounded English quantity/collection signals. Pure, no rewriting/I/O.

PASS is limited to this detector repertoire, never semantic approval.
Upstream must authenticate admission and verify the returned input binding.
"""
from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import re
import unicodedata


class Status(str, Enum):
    PASS = 'PASS'
    NEEDS_REVIEW = 'NEEDS_REVIEW'
    REJECTED = 'REJECTED'


@dataclass(frozen=True)
class Scope:
    category: str
    subject: str


@dataclass(frozen=True)
class Claim:
    claim_id: str
    claim_text: str
    applicable_scope: Scope
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    code: str
    paragraph_ref: str
    signal: str
    excerpt: str
    candidate_claim_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditResult:
    status: Status
    findings: tuple[Finding, ...]
    article_sha256: str | None
    input_sha256: str | None
    test_only: bool = True
    semantic_approved: bool = False
    production_authorized: bool = False
    live_execution_authorized: bool = False


def normal(text):
    return re.sub(r'\s+', ' ', re.sub(r'[_\u2010-\u2015]', '-',
        unicodedata.normalize('NFKC', text).casefold())).strip()


NUMBER = r'(?:\d+(?:[.,]\d+)*|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|hundred|thousand|million)'
COLLECTION = re.compile(r'\b(?:(?:' + NUMBER + r'|multiple|several|many|both|all|every|each|numerous|various)\s+(?:(?:documented|synthetic|selected)\s+){0,2}(?:configurations?|products?|solutions?|cases?|documents?|records?|items?|models?|applications?)|complete\s+coverage|(?:total|count|sum)s?)\b')
QUANTITY = re.compile(r'\b' + NUMBER + r'(?:-axis)?\b|\b(?:multiple|several|many|both|all|every|complete|numerous|various|pair|dozen)\b')
AMBIGUOUS = re.compile(r'\b(?:not|no|never|without|cannot|can\x27t|unless|if|may|might|could|should)\b|[?"\u201c\u201d]')


def text_ok(value, limit):
    return (type(value) is str and bool(value.strip()) and len(value.encode('utf-8')) <= limit
            and not any(unicodedata.category(c).startswith('C') and c not in '\n\r\t' for c in value))


def audit(admitted_claims, allowed_scope, generated_article):
    """Three inputs only. Never returns a rewritten article or mutates inputs."""
    try:
        valid = (type(admitted_claims) is tuple and 1 <= len(admitted_claims) <= 32
                 and type(allowed_scope) is tuple and 1 <= len(allowed_scope) <= 32
                 and text_ok(generated_article, 65536))
        valid = valid and all(type(s) is Scope and text_ok(s.category, 128)
                             and text_ok(s.subject, 256) for s in allowed_scope)
        valid = valid and len(set(allowed_scope)) == len(allowed_scope)
        valid = valid and all(type(c) is Claim and text_ok(c.claim_id, 64)
            and text_ok(c.claim_text, 4096) and c.applicable_scope in allowed_scope
            and type(c.evidence_refs) is tuple and 1 <= len(c.evidence_refs) <= 16
            and all(text_ok(ref, 128) for ref in c.evidence_refs) for c in admitted_claims)
        valid = valid and len({c.claim_id for c in admitted_claims}) == len(admitted_claims)
        if not valid:
            raise ValueError()
        paragraphs = [p for p in re.split(r'\n\s*\n', generated_article.replace('\r\n', '\n')) if p.strip()]
        if len(paragraphs) > 512:
            raise ValueError()
    except (ValueError, TypeError, AttributeError, UnicodeError):
        return AuditResult(Status.REJECTED, (Finding('INPUT_INVALID', 'DOCUMENT', '', ''),), None, None)
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    article_hash = digest(generated_article.encode('utf-8'))
    binding = digest(json.dumps(dict(claims=[asdict(c) for c in admitted_claims],
        scopes=[asdict(s) for s in allowed_scope], article=generated_article),
        ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    findings = []
    rejected = False
    for index, paragraph in enumerate(paragraphs, 1):
        ref = f'P{index:03}'
        if any(unicodedata.category(ch).startswith('L') and ord(ch) > 127 for ch in normal(paragraph)):
            findings.append(Finding('LANGUAGE_OUTSIDE_REPERTOIRE', ref, '', paragraph[:240]))
            if len(findings) >= 128:
                return AuditResult(Status.REJECTED if rejected else Status.NEEDS_REVIEW,
                    tuple(findings[:127] + [Finding('FINDING_BUDGET', 'DOCUMENT', '', '')]), article_hash, binding)
        for sentence in re.split(r'(?<=[.!?;])\s+|\n', paragraph):
            normalized = normal(sentence).strip(' .!;:#*')
            signals = list(COLLECTION.finditer(normalized))
            signals += [m for m in QUANTITY.finditer(normalized)
                        if not any(a.start() <= m.start() < a.end() for a in signals)]
            for match in signals:
                signal = match.group()
                candidates = tuple(c for c in admitted_claims
                    if re.search(r'(?<!\w)' + re.escape(signal) + r'(?!\w)', normal(c.claim_text)))
                # Only an exact whole claim/sentence gets a collection exception.
                # Matching a substring alone cannot authorize broader scope.
                exact = any(normal(c.claim_text).strip(' .!;:#*') == normalized
                    and re.search(r'(?<!\w)' + re.escape(normal(c.applicable_scope.subject)) + r'(?!\w)', normalized)
                    for c in candidates)
                # Narrow explicit attribute grammar supports the requested five-axis case.
                attribute = any(re.fullmatch(NUMBER + r'-axis', signal)
                    and normal(c.claim_text).strip(' .') == signal + ' machining'
                    and normalized == normal(c.applicable_scope.subject) + ' supports ' + signal + ' machining'
                    for c in candidates)
                if exact or attribute:
                    continue
                uncertain = bool(candidates) or bool(AMBIGUOUS.search(normalized))
                code = 'CLAIM_CONTEXT_REQUIRES_REVIEW' if uncertain else 'UNSUPPORTED_CLAIM'
                rejected |= not uncertain
                findings.append(Finding(code, ref, signal, sentence[:240], tuple(c.claim_id for c in candidates)))
                if len(findings) >= 128:
                    findings = findings[:127] + [Finding('FINDING_BUDGET', 'DOCUMENT', '', '')]
                    return AuditResult(Status.REJECTED if rejected else Status.NEEDS_REVIEW,
                                       tuple(findings), article_hash, binding)
    return AuditResult(Status.REJECTED if rejected else Status.NEEDS_REVIEW if findings else Status.PASS,
                       tuple(findings), article_hash, binding)
