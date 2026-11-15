"""Opt-in real Ollama integration check; creates only a temporary database.
Run: .venv/bin/python tests/smoke_local.py
Starts a temporary loopback server, exercises streaming/restart/stop, then exits.
"""
import argparse
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', help='Installed Ollama model; defaults to the app preference')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='localfirst-smoke-') as directory:
        path = Path(directory) / 'smoke.sqlite3'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        process = None

        def start():
            nonlocal process
            code = ('from app.main import create_app; import uvicorn; '
                    f'uvicorn.run(create_app(db_path={str(path)!r}), host="127.0.0.1", port={port}, log_level="error", access_log=False)')
            process = subprocess.Popen([sys.executable, '-c', code], cwd=ROOT)
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('Smoke server exited early')
                try:
                    if httpx.get(base + '/api/health', timeout=1, trust_env=False).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
            raise RuntimeError('Smoke server did not start')

        def stop():
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        try:
            start()
            with httpx.Client(base_url=base, timeout=180, trust_env=False) as client:
                assert client.get('/').status_code == 200
                assert client.get('/static/styles.css').status_code == 200
                catalog = client.get('/api/models').json()
                model = args.model or catalog['default']
                assert model in catalog['models'], 'Select an installed model with --model'
                print('Testing installed model:', model)
                cid = client.post('/api/conversations').json()['id']
                route = f'/api/conversations/{cid}/chat'
                def chat(prompt):
                    events, arrival = [], []
                    started = time.perf_counter()
                    with client.stream('POST', route, json={'content':prompt,'model':model}) as response:
                        assert response.status_code == 200
                        for line in response.iter_lines():
                            if line:
                                event = json.loads(line)
                                events.append(event)
                                if event['type'] == 'delta':
                                    arrival.append(time.perf_counter()-started)
                    assert events[-1]['type'] == 'done', events[-1]
                    telemetry = events[-1]['telemetry']
                    assert telemetry['status'] == 'success'
                    assert telemetry['external_api_cost'] == 0
                    assert telemetry['tokens_per_second'] is not None
                    assert telemetry['ttft_ms'] >= 0
                    result = ''.join(e['content'] for e in events if e['type']=='delta')
                    print(f"Real chat: {len(arrival)} deltas, first={arrival[0]:.2f}s, total={events[-1]['latency_ms']/1000:.2f}s, output_tokens={events[-1]['output_tokens']}")
                    return result
                chat('Remember this code word: juniper. Reply with a short acknowledgement.')
                followup = chat('What code word did I ask you to remember? Reply with just the word.')
                assert 'juniper' in followup.lower(), 'Model did not recall the code word'
                before = client.get(f'/api/conversations/{cid}').json()
                assert len(before['messages']) == 4
                stop()
                start()
                after = client.get(f'/api/conversations/{cid}').json()
                assert after == before
                print('Follow-up context and server-restart persistence: PASS')
                with client.stream('POST', route, json={'content':'Write a very long essay about the history of mathematics.', 'model':model}) as response:
                    for line in response.iter_lines():
                        if line and json.loads(line)['type'] == 'delta':
                            break
                for _ in range(50):
                    saved = client.get(f'/api/conversations/{cid}').json()['messages'][-1]
                    if saved['status'] != 'streaming':
                        break
                    time.sleep(.1)
                assert saved['status'] == 'stopped', saved['status']
                assert saved['telemetry']['status'] == 'cancelled'
                overview = client.get('/api/usage?days=0').json()['overview']
                assert overview['requests'] == 3
                assert overview['local_percentage'] == 100
                assert overview['external_api_cost'] == 0
                print('Real HTTP disconnect stops generation and saves incomplete status: PASS')
                assert client.get('/api/health').status_code == 200
        finally:
            stop()


if __name__ == '__main__':
    main()
