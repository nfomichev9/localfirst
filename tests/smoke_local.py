"""Opt-in real Ollama integration check; creates only a temporary database.
Run: .venv/bin/python tests/smoke_local.py
Starts a temporary loopback server, exercises streaming/restart/stop, then exits.
"""
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
                models = client.get('/api/models').json()['models']
                assert 'llama3.2:3b' in models
                cid = client.post('/api/conversations').json()['id']
                route = f'/api/conversations/{cid}/chat'
                def chat(prompt):
                    events, arrival = [], []
                    started = time.perf_counter()
                    with client.stream('POST', route, json={'content':prompt,'model':'llama3.2:3b'}) as response:
                        assert response.status_code == 200
                        for line in response.iter_lines():
                            if line:
                                event = json.loads(line)
                                events.append(event)
                                if event['type'] == 'delta':
                                    arrival.append(time.perf_counter()-started)
                    assert events[-1]['type'] == 'done', events[-1]
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
                with client.stream('POST', route, json={'content':'Write a very long essay about the history of mathematics.'}) as response:
                    for line in response.iter_lines():
                        if line and json.loads(line)['type'] == 'delta':
                            break
                for _ in range(50):
                    saved = client.get(f'/api/conversations/{cid}').json()['messages'][-1]
                    if saved['status'] != 'streaming':
                        break
                    time.sleep(.1)
                assert saved['status'] == 'stopped', saved['status']
                print('Real HTTP disconnect stops generation and saves incomplete status: PASS')
                assert client.get('/api/health').status_code == 200
        finally:
            stop()


if __name__ == '__main__':
    main()
