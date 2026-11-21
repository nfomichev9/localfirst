"""Opt-in isolation harness for three small paid OpenAI chat requests."""
import argparse
import json
import tempfile
from pathlib import Path

import httpx
import uvicorn

from app.main import create_app
from test_routing import Local, packets, save


def run(base_url):
    with httpx.Client(base_url=base_url, timeout=90, trust_env=False) as client:
        readiness = client.get('/api/settings').raise_for_status().json()
        if not readiness['provider_ready'] or readiness['daily_limit_cents'] != 1:
            raise SystemExit('Configure the smoke server and save a $0.01 daily limit before running.')
        if client.get('/api/conversations').raise_for_status().json():
            raise SystemExit('Use a fresh, isolated smoke server.')
        for mode in ('always_frontier', 'manual_handoff', 'automatic_handoff'):
            save(client, mode).raise_for_status()
            cid = client.post('/api/conversations').raise_for_status().json()['id']
            base = f'/api/conversations/{cid}'
            turn = packets(client.post(base + '/chat', json={'content': 'Synthetic smoke test. Reply with a short ACK.'}))
            starts = [packet for packet in turn if packet['type'] == 'start']
            if mode == 'always_frontier':
                assert [packet['provider'] for packet in starts] == ['openai']
            elif mode == 'manual_handoff':
                assert [packet['provider'] for packet in starts] == ['ollama']
                handoff = f"{base}/messages/{starts[0]['message_id']}/handoff"
                preview = client.post(handoff + '/preview').raise_for_status().json()
                packets(client.post(handoff, json=dict(preview['brief'], token=preview['token'])))
            else:
                assert [packet['provider'] for packet in starts] == ['ollama', 'openai']
            messages = client.get(base).raise_for_status().json()['messages']
            reply = messages[-1]
            assert reply['status'] == 'complete', reply['error']
            assert reply['content'].strip()
            assert reply['telemetry']['provider'] == 'openai'
            if mode != 'always_frontier':
                assert reply['handoff_of'] == messages[-2]['id']
                assert 'Synthetic summary' in reply['handoff_brief']
            usage = reply['telemetry']
            assert usage['input_tokens'] > 0 and usage['output_tokens'] > 0
            print(json.dumps(dict(mode=mode, model=reply['model'], input_tokens=usage['input_tokens'],
                                  output_tokens=usage['output_tokens'], charge=usage['external_api_cost'])))
        save(client, 'always_local').raise_for_status()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('serve', 'run'))
    parser.add_argument('--port', type=int, default=8013)
    args = parser.parse_args()
    if args.action == 'serve':
        # Deterministic local responses keep the smoke test focused on the paid boundary.
        with tempfile.TemporaryDirectory(prefix='localfirst-openai-smoke-') as directory:
            uvicorn.run(create_app(Path(directory) / 'smoke.db', Local()), host='127.0.0.1', port=args.port)
    else:
        run(f'http://127.0.0.1:{args.port}')
