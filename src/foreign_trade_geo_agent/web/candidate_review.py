"""Local Review of retained native model output, with no execution capability."""
from datetime import UTC, datetime

from foreign_trade_geo_agent.core.content_draft import ContentDraftInput, MAX_RAW_OUTPUT_CHARS, MAX_RAW_OUTPUT_BYTES
from foreign_trade_geo_agent.core.draft_candidate_review import CandidateDecision, digest, effective_decisions
from foreign_trade_geo_agent.core.evidence_intake import snapshot_digest
from foreign_trade_geo_agent.storage.content_draft_review import SQLiteLocalDraftReviewStore
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.web.generation import read_json, check
from foreign_trade_geo_agent.workflows.content_draft import inspect_candidate_output


class LocalCandidateReview:
    def __init__(self, service):
        self.service = service

    def load(self, key):
        check(type(key) is str and len(key) == 64 and all(c in '0123456789abcdef' for c in key), 'LOCAL_RECORD_INVALID')
        output = self.service.generation.root / key
        result = read_json(output / 'result.json')
        check(result['binding_sha256'] == key and result['production_authorized'] is False
              and result.get('candidate_available') is True and result['mode'] in {'MOCK', 'LIVE'}, 'LOCAL_RECORD_INVALID')
        value = _decode(read_json(output / 'native-input.json', 160000), ContentDraftInput)
        # Bounded exact output read; never repaired or served as executable HTML.
        with (output / 'model-output.txt').open('r', encoding='utf-8', newline='') as stream:
            original = stream.read(MAX_RAW_OUTPUT_CHARS + 1)
        check(0 < len(original) <= MAX_RAW_OUTPUT_CHARS
              and len(original.encode('utf-8')) <= MAX_RAW_OUTPUT_BYTES
              and digest(original) == result['model_text_sha256'], 'LOCAL_RECORD_INVALID')
        journal = SQLiteLocalDraftReviewStore(output / 'local-review.sqlite3')
        history = journal.revisions(digest(original))
        check(bool(history) and history[0].body_text == original, 'LOCAL_RECORD_INVALID')
        session, _, store, _, _ = self.service._load()
        current = self.service._current(store, session)
        check((current.task.project_id, current.task.task_id) ==
              (value.customer_evidence.project_id, value.customer_evidence.task_id), 'LOCAL_RECORD_INVALID')
        latest = history[-1]
        view = inspect_candidate_output(value, latest.body_text, current_snapshot_sha256=snapshot_digest(current))
        return dict(candidate_key=key, candidate_check=view, candidate_original=original,
            candidate_max_chars=MAX_RAW_OUTPUT_CHARS,
            candidate_raw=latest.body_text, candidate_history=history, candidate_latest=latest,
            candidate_decisions=effective_decisions(view, latest), candidate_mode=result['mode'],
            candidate_journal=journal, candidate_value=value, candidate_snapshot=current)

    def save(self, *, key, version, binding, claim_id, decision, note, body_text):
        view = self.load(key)
        latest, checked = view['candidate_latest'], view['candidate_check']
        check(str(latest.version) == version and binding == checked.binding_sha256, 'STALE_BINDING')
        decisions = dict(view['candidate_decisions']) if body_text == latest.body_text else {}
        if decision != 'EDIT':
            check(body_text == latest.body_text and not checked.errors
                  and any(c.claim_id == claim_id and c.proposal is not None for c in checked.claims), 'CANDIDATE_NOT_REVIEWABLE')
            decisions[claim_id] = CandidateDecision(binding, claim_id, decision, note)
        else:
            # Validate syntax before appending, but retain deterministic rejects.
            inspect_candidate_output(view['candidate_value'], body_text,
                current_snapshot_sha256=snapshot_digest(view['candidate_snapshot']))
        return view['candidate_journal'].append(origin_sha256=latest.origin_sha256,
            expected_version=latest.version, original_body=view['candidate_original'], body_text=body_text,
            note=note, status='CHANGES_REQUESTED' if decision in {'REJECT', 'REQUEST_CHANGES'} else 'PENDING_REVIEW',
            frozen_evidence_sha256=latest.frozen_evidence_sha256,
            observed_evidence_sha256=snapshot_digest(view['candidate_snapshot']), saved_at=datetime.now(UTC),
            candidate_decisions=tuple(decisions.values()))
