"""Offline-only Writer. No credentials, SDK, production adapter, or hidden retry."""
import json


class FakePreviewWriter:
    timeout_seconds = 30

    def policy(self):
        return dict(profile='COMMERCIAL_PREVIEW', writer='FakePreviewWriter', enabled=True,
                    model='FAKE', cost='UNKNOWN', production_authorized=False)

    def preparation(self):
        return dict(self.policy(), status='READY')

    def __init__(self):
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        spans = {s['span_id']: s for s in request['spans']}
        paragraphs = []
        for review in request['reviews']:
            for span_id in review['span_ids']:
                span = spans[span_id]
                headings = {'reader-question': 'The buyer question', 'scope': 'Applicable scope',
                            'limitations': 'Project limitations'}
                paragraphs.append(dict(heading=headings.get(review['obligation_id'], 'Documented capability'),
                                       text=span['quote'], source_ids=[span['source_id']],
                                       obligation_ids=[review['obligation_id']]))
        return json.dumps(dict(schema_version=1, title=request['task']['title'], paragraphs=paragraphs))
