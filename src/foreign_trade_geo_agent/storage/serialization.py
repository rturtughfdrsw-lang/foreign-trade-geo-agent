"""Explicit, versioned JSON codecs for persisted domain artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
import json
import math
import types
from typing import Any, Union, get_args, get_origin, get_type_hints

from foreign_trade_geo_agent.core.content_draft_review import LocalDraftRevision
from foreign_trade_geo_agent.core.audit import SiteAuditResult
from foreign_trade_geo_agent.core.change_plan import ChangeOperation, ChangePlanReport, NewResourceSpec
from foreign_trade_geo_agent.core.content_draft import ContentDraftInput, ContentDraftReport, DraftItem, DraftClaim, ArticleWritingBrief
from foreign_trade_geo_agent.core.draft_customer_evidence import DraftCustomerSource, DraftCustomerEvidence, DraftCustomerFact, DraftInterpretation
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunity,
    ContentOpportunityReport,
)
from foreign_trade_geo_agent.core.history import (
    ArtifactType,
    MalformedHistoryDataError,
    UnsupportedHistoryVersionError,
)
from foreign_trade_geo_agent.core.optimization import SiteOptimizationReport
from foreign_trade_geo_agent.core.research import ResearchReport
from foreign_trade_geo_agent.core.site_content import SiteContentPacket
from foreign_trade_geo_agent.core.visibility import VisibilityReport
from foreign_trade_geo_agent.core.evidence_intake import SemanticAssessment, EvidenceTask, ReviewedInterpretation


_ROOT_TYPES: dict[tuple[ArtifactType, int], type[object]] = {
    (ArtifactType.SITE_CONTENT, 1): SiteContentPacket,
    (ArtifactType.SITE_AUDIT, 1): SiteAuditResult,
    (ArtifactType.VISIBILITY, 1): VisibilityReport,
    (ArtifactType.SITE_OPTIMIZATION, 1): SiteOptimizationReport,
    (ArtifactType.INDUSTRY_RESEARCH, 1): ResearchReport,
    (ArtifactType.CONTENT_OPPORTUNITY, 1): ContentOpportunityReport,
    (ArtifactType.CHANGE_PLAN, 1): ChangePlanReport,
    (ArtifactType.CONTENT_DRAFT, 1): ContentDraftReport,
}
_V1_DEFAULTED_COMPAT_FIELDS: dict[type[object], frozenset[str]] = {
    LocalDraftRevision: frozenset({"candidate_decisions"}),
    ReviewedInterpretation: frozenset({"proposal"}),
    DraftInterpretation: frozenset({"proposal"}),
    SemanticAssessment: frozenset({"scope_coverage", "interpretations"}),
    EvidenceTask: frozenset({'article_type', 'search_intent', 'reader_problem', 'section_briefs'}),
    ArticleWritingBrief: frozenset({'article_type', 'reader_problem'}),
    NewResourceSpec: frozenset({'section_briefs'}),
    DraftCustomerSource: frozenset({'facts'}),
    DraftCustomerEvidence: frozenset({'interpretations'}),
    DraftCustomerFact: frozenset({'requirement_ids'}),
    ContentDraftInput: frozenset({"customer_evidence", "writing_brief", "propose_interpretations"}),
    DraftItem: frozenset({"section_block_counts", "customer_evidence"}),
    DraftClaim: frozenset({"customer_refs", "proposal"}),
    ContentOpportunity: frozenset({"audit_refs"}),
    ContentOpportunityReport: frozenset(
        {"audit_evidence", "final_validation_category", "writer_attempt_count"}
    ),
    ChangeOperation: frozenset({"audit_refs"}),
    ChangePlanReport: frozenset(
        {"final_validation_category", "writer_attempt_count"}
    ),
}


def encode_artifact(
    artifact_type: ArtifactType,
    value: object,
    *,
    payload_version: int = 1,
) -> str:
    root_type = _root_type(artifact_type, payload_version)
    if type(value) is not root_type:
        raise TypeError("Artifact value does not match its allowlisted root type.")
    return json.dumps(
        _encode(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def decode_artifact(
    artifact_type: ArtifactType,
    payload_version: int,
    payload_json: str,
) -> object:
    root_type = _root_type(artifact_type, payload_version)
    if type(payload_json) is not str:
        raise MalformedHistoryDataError("Artifact payload must be JSON text.")
    try:
        raw = json.loads(
            payload_json,
            object_pairs_hook=_unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"Unsupported JSON constant: {value}")
            ),
        )
        if type(raw) is not dict:
            raise ValueError("root is not an object")
        return _decode(raw, root_type)
    except MalformedHistoryDataError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise MalformedHistoryDataError("Artifact payload is malformed.") from exc


def _root_type(artifact_type: ArtifactType, payload_version: int) -> type[object]:
    if not isinstance(artifact_type, ArtifactType) or type(payload_version) is not int:
        raise UnsupportedHistoryVersionError("Artifact codec is unsupported.")
    try:
        return _ROOT_TYPES[(artifact_type, payload_version)]
    except KeyError as exc:
        raise UnsupportedHistoryVersionError("Artifact codec is unsupported.") from exc


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key.")
        result[key] = value
    return result


def _encode(value: object) -> object:
    if value is None or type(value) in {str, int, bool}:
        return value
    if type(value) is float:
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime must be timezone-aware.")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise TypeError("Artifact mapping keys must be strings.")
        return {key: _encode(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)
                if not (field.name == "proposal" and getattr(value, field.name) is None)
                and not (type(value) is ContentDraftInput and field.name == "propose_interpretations" and value.propose_interpretations is False)
                and not (type(value) in {ContentDraftInput, DraftItem} and field.name == "customer_evidence"
                        and getattr(value, field.name) is None)
                and not (type(value) is ContentDraftInput and field.name == 'writing_brief' and value.writing_brief is None)
                and not (type(value) is DraftClaim and field.name == "customer_refs" and not value.customer_refs)
                and not (field.name in _V1_DEFAULTED_COMPAT_FIELDS.get(type(value), ())
                         and field.name in {'article_type', 'reader_problem', 'search_intent', 'section_briefs', 'facts', 'interpretations', 'candidate_decisions'}
                         and getattr(value, field.name) in (None, ()))}
    raise TypeError("Artifact contains an unsupported value.")


def _decode(value: object, expected_type: object) -> object:
    if expected_type is Any:
        raise TypeError("Unbounded artifact values are not supported.")
    origin = get_origin(expected_type)
    args = get_args(expected_type)

    if origin in {Union, types.UnionType}:
        matches: list[object] = []
        for candidate in args:
            try:
                matches.append(_decode(value, candidate))
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                continue
        if len(matches) != 1:
            raise ValueError("Union value is ambiguous or invalid.")
        return matches[0]

    if origin is tuple:
        if type(value) is not list:
            raise TypeError("Tuple field must be a JSON array.")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(item, args[0]) for item in value)
        if len(args) != len(value):
            raise ValueError("Fixed tuple length is invalid.")
        return tuple(_decode(item, item_type) for item, item_type in zip(value, args, strict=True))

    if origin in {dict, Mapping} or origin is not None and issubclass(origin, Mapping):
        if type(value) is not dict or len(args) != 2 or args[0] is not str:
            raise TypeError("Mapping field must be a JSON object with string keys.")
        return {key: _decode(item, args[1]) for key, item in value.items() if type(key) is str}

    if expected_type is type(None):
        if value is not None:
            raise TypeError("Expected null.")
        return None
    if expected_type in {str, int, float, bool}:
        if expected_type is float and type(value) is float and math.isfinite(value):
            return value
        if type(value) is not expected_type:
            raise TypeError("Primitive field has an invalid type.")
        return value
    if expected_type is datetime:
        if type(value) is not str or not value.endswith("Z"):
            raise TypeError("Datetime field must use UTC RFC3339 Z.")
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        if parsed.tzinfo is None:
            raise ValueError("Datetime field is naive.")
        return parsed
    if isinstance(expected_type, type) and issubclass(expected_type, Enum):
        return expected_type(value)
    if isinstance(expected_type, type) and is_dataclass(expected_type):
        if type(value) is not dict:
            raise TypeError("Dataclass field must be a JSON object.")
        dataclass_fields = fields(expected_type)
        expected_keys = {field.name for field in dataclass_fields}
        required_keys = expected_keys - _V1_DEFAULTED_COMPAT_FIELDS.get(
            expected_type, frozenset()
        )
        if not required_keys <= set(value) or not set(value) <= expected_keys:
            raise ValueError("Dataclass payload fields are invalid.")
        hints = get_type_hints(expected_type)
        kwargs = {
            field.name: _decode(value[field.name], hints[field.name])
            for field in dataclass_fields
            if field.name in value
        }
        return expected_type(**kwargs)
    raise TypeError("Artifact field type is unsupported.")
