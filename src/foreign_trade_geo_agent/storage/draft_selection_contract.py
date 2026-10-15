"""Separate versioned JSON files; deliberately outside the V1 SQLite codec."""
from dataclasses import asdict, fields
import json
from pathlib import Path

from foreign_trade_geo_agent.core.draft_selection_contract import (
    DraftSelectionContract, SectionEvidenceBudget, FactSelectionReason,
    canonical_json, require, selection_digest,
)
from foreign_trade_geo_agent.core.draft_explanation_contract import ExplanationContract, ExplanationAnnotation

MAX_ARTIFACT_BYTES = 262144


def _object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'SELECTION_ARTIFACT_DUPLICATE_KEY')
        value[key] = item
    return value


def _shape(raw, cls):
    require(type(raw) is dict and set(raw) == {f.name for f in fields(cls)}, 'SELECTION_ARTIFACT_FIELDS')
    return dict(raw)


def _tuple_fields(raw, names):
    for key in names:
        require(type(raw[key]) is list, 'SELECTION_ARTIFACT_LIST')
        raw[key] = tuple(raw[key])
    return raw


def encode_selection_artifact(contract: DraftSelectionContract) -> str:
    require(type(contract) is DraftSelectionContract, 'SELECTION_ARTIFACT_TYPE')
    raw = canonical_json(dict(artifact_type='draft_fact_selection', payload_version=2,
        contract_sha256=selection_digest(contract), payload=asdict(contract)))
    require(len(raw.encode('utf-8')) <= MAX_ARTIFACT_BYTES, 'SELECTION_ARTIFACT_SIZE')
    return raw


def decode_selection_artifact(raw: str) -> DraftSelectionContract:
    """Strict shape and intrinsic invariants; evidence/Plan validation follows at use."""
    require(type(raw) is str and len(raw) <= MAX_ARTIFACT_BYTES
            and len(raw.encode('utf-8')) <= MAX_ARTIFACT_BYTES, 'SELECTION_ARTIFACT_SIZE')
    try:
        data = json.loads(raw, object_pairs_hook=_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('SELECTION_ARTIFACT_NUMBER')))
        require(type(data) is dict and set(data) == {'artifact_type', 'payload_version', 'contract_sha256', 'payload'},
                'SELECTION_ARTIFACT_FIELDS')
        require(data['artifact_type'] == 'draft_fact_selection' and type(data['payload_version']) is int
                and data['payload_version'] == 2, 'SELECTION_ARTIFACT_VERSION')
        payload = _shape(data['payload'], DraftSelectionContract)
        require(type(payload['sections']) is list and 1 <= len(payload['sections']) <= 24
            and type(payload['fact_reasons']) is list and 1 <= len(payload['fact_reasons']) <= 64,
            'SELECTION_ARTIFACT_LIST')
        payload['sections'] = tuple(SectionEvidenceBudget(**_tuple_fields(_shape(s, SectionEvidenceBudget),
            ('requirement_ids', 'required_sources', 'required_facts', 'optional_facts',
             'selected_facts', 'required_direct_facts'))) for s in payload['sections'])
        payload['fact_reasons'] = tuple(FactSelectionReason(**_tuple_fields(_shape(r, FactSelectionReason),
            ('selected_sections',))) for r in payload['fact_reasons'])
        contract = DraftSelectionContract(**payload)
        require(data['contract_sha256'] == selection_digest(contract), 'SELECTION_ARTIFACT_HASH')
        return contract
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as exc:
        raise ValueError('SELECTION_ARTIFACT_INVALID') from exc


def write_selection_artifact(path: str | Path, contract: DraftSelectionContract) -> None:
    """Create-only local audit file. Never replace historical artifacts."""
    raw = encode_selection_artifact(contract)
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(raw)


def encode_explanation_contract(contract: ExplanationContract) -> str:
    require(type(contract) is ExplanationContract, 'EXPLANATION_ARTIFACT_TYPE')
    raw = canonical_json(asdict(contract))
    require(len(raw.encode('utf-8')) <= MAX_ARTIFACT_BYTES, 'EXPLANATION_ARTIFACT_SIZE')
    return raw


def decode_explanation_contract(raw: str) -> ExplanationContract:
    require(type(raw) is str and len(raw) <= MAX_ARTIFACT_BYTES
        and len(raw.encode('utf-8')) <= MAX_ARTIFACT_BYTES, 'EXPLANATION_ARTIFACT_SIZE')
    try:
        payload = _shape(json.loads(raw, object_pairs_hook=_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('EXPLANATION_ARTIFACT_NUMBER'))), ExplanationContract)
        require(type(payload['explanations']) is list and len(payload['explanations']) <= 48, 'EXPLANATION_ARTIFACT_LIST')
        payload['explanations'] = tuple(ExplanationAnnotation(**_tuple_fields(_shape(a, ExplanationAnnotation),
            ('selected_fact_refs',))) for a in payload['explanations'])
        return ExplanationContract(**payload)
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as exc:
        raise ValueError('EXPLANATION_ARTIFACT_INVALID') from exc
