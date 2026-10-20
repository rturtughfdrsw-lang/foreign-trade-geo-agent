"""Offline acceptance over a real loopback HTTP server; all outbound boundaries mocked."""
import argparse
import json
import os
from pathlib import Path
import socket
import threading
import time
from uuid import uuid4

import httpx
import uvicorn

from foreign_trade_geo_agent.core.commercial_preview import ExecutionConfirmation
from foreign_trade_geo_agent.web.commercial_preview import create_preview_app
from tests.test_commercial_preview import Forms, SAMPLES
from tests.test_commercial_preview_v11 import KEY, SITE, WEBSITE_QUOTE, MockBoundaries


def exercise(client, flow, mock):
    transcript = []

    def post(page, path, extra):
        response = client.post(path, data=dict(Forms(page.text).forms[path], **extra))
        transcript.append(dict(path=path, status=response.status_code))
        assert response.status_code == 303, response.text[:500]
        return response

    page = client.get('/')
    response = post(page, '/analyze', dict(website=SITE+'/', mode='REAL_SITE', allowed_urls=SITE+'/', site_ack='yes'))
    url = response.headers['location']
    page = client.get(url)
    post(page, url+'/task', dict(title='Aster Stainless Steel Enclosures: A Factual Overview',
        reader_question='What does Aster supply and what must a buyer confirm?',
        fact_0='Describe the enclosure product.', fact_1='Describe the fabrication capability.',
        scope='Aster stainless steel enclosure fabrication for reviewed industrial equipment drawings.',
        limitations='Project-specific suitability, ratings and delivery must be separately confirmed.', task_ack='yes'))
    page = client.get(url)
    run_id = url.split('/')[-1]
    source = flow.store.read(run_id)['sources'][0]
    # Exact website text joins the same reviewed evidence chain as owner documents.
    post(page, url+'/bind-page', dict(source_id=source['source_id'], obligation_id='fact-1', quote=WEBSITE_QUOTE))
    page = client.get(url)
    for key, value in SAMPLES.items():
        post(page, url+'/evidence', dict(obligation_id=key, content=value,
                                       label='Offline acceptance owner document', locator='local://'+key))
        page = client.get(url)
    for key in SAMPLES:
        state = flow.store.read(run_id)
        spans = [span['span_id'] for span in state['spans'] if span['obligation_id'] == key]
        post(page, url+'/review', dict(obligation_id=key, span_id=spans, verdict='SUPPORTED',
            note='Offline operator checked the exact text and scope.', review_ack='LOCAL_PREVIEW_REVIEW'))
        page = client.get(url)
    assert len(mock.model_requests) == 0
    post(page, url+'/confirm', dict(execution_ack='yes'))
    page = client.get(url)
    fields = Forms(page.text).forms[url+'/generate']
    for _ in range(2):
        response = client.post(url+'/generate', data=fields)
        assert response.status_code == 303
        transcript.append(dict(path=url+'/generate', status=response.status_code))
    page = client.get(url)
    assert '<article>' in page.text and 'NEEDS_REVIEW' in page.text
    post(page, url+'/feedback', dict(note='Loopback HTTP offline V1.1 acceptance feedback.'))
    page = client.get(url)
    assert 'Loopback HTTP offline V1.1 acceptance feedback.' in page.text
    assert len(mock.model_requests) == 1
    result = flow.result(run_id)
    assert result['result']['TECHNICAL'] == 'SUCCEEDED'
    assert result['result']['EVIDENCE'] == 'NEEDS_REVIEW'
    assert 300 <= result['result']['word_count'] <= 500
    assert result['production_authorized'] is False
    return url, transcript, page.text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8027)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--keep-serving', action='store_true')
    parser.add_argument('--read-existing', action='store_true')
    args = parser.parse_args()
    assert 1024 <= args.port <= 65535 and args.port not in {8002, 8003}
    directory = args.data_dir or Path('.data')/('commercial-preview-v11-offline-'+str(uuid4()))
    directory.mkdir(parents=True, exist_ok=True)
    # Only a placeholder key; this harness cannot construct a real outbound transport/resolver.
    os.environ['DEEPSEEK_API_KEY'] = KEY
    mock = MockBoundaries()
    flow = mock.flow(directory)
    server = uvicorn.Server(uvicorn.Config(create_preview_app(flow), host='127.0.0.1', port=args.port,
                                          log_level='warning', access_log=False))
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', args.port))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic()+10
            while not server.started:
                assert thread.is_alive() and time.monotonic() < deadline
                time.sleep(.05)
            base = 'http://127.0.0.1:'+str(args.port)
            with httpx.Client(base_url=base, trust_env=False, timeout=60) as client:
                if args.read_existing:
                    run_id = flow.store.list_runs()[-1]
                    url = '/runs/'+run_id
                    page = client.get(url)
                    assert '<article>' in page.text and 'Loopback HTTP offline V1.1 acceptance feedback.' in page.text
                    assert not mock.model_requests and not mock.site_requests
                    verification = dict(restarted=True, url=base+url, writer_calls=flow.writer.calls,
                                        mock_model_requests=0, mock_site_requests=0, result_preserved=True)
                    (directory/'restart.json').write_text(json.dumps(verification, indent=2), encoding='utf-8')
                else:
                    assert not flow.store.list_runs(), 'Use a new acceptance directory; existing data is never overwritten.'
                    url, transcript, html = exercise(client, flow, mock)
                    run_id = url.split('/')[-1]
                    result = flow.result(run_id)
                    verification = dict(offline=True, real_network_requests=0, url=base+url,
                        run_id=run_id, mock_site_requests=mock.site_requests, mock_model_requests=len(mock.model_requests),
                        repeated_generate_posts=2, writer_calls=flow.writer.calls, word_count=result['result']['word_count'],
                        TECHNICAL=result['result']['TECHNICAL'], EVIDENCE=result['result']['EVIDENCE'],
                        EDITORIAL_REVIEW=result['result']['EDITORIAL_REVIEW'],
                        PRODUCTION_AUTHORIZATION=result['result']['PRODUCTION_AUTHORIZATION'],
                        production_authorized=False, transcript=transcript)
                    for name, data in (('verification.json', verification), ('result.json', result),
                                       ('state.json', flow.store.read(run_id))):
                        (directory/name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                    (directory/'result.html').write_text(html, encoding='utf-8')
                print(json.dumps(dict(directory=str(directory.resolve()), **verification), ensure_ascii=False), flush=True)
            while args.keep_serving:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            server.should_exit = True
            thread.join(10)
            assert not thread.is_alive()


if __name__ == '__main__':
    main()
