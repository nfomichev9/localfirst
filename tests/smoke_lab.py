"""Opt-in real Ollama Lab test. Isolated DB/server; no user tasks or cloud calls.
Run: .venv/bin/python tests/smoke_lab.py
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
    with tempfile.TemporaryDirectory(prefix='localfirst-lab-') as directory:
        path = Path(directory) / 'lab.db'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        process = None
        def start():
            nonlocal process
            command = f'from app.main import create_app; import uvicorn; uvicorn.run(create_app({str(path)!r}),host="127.0.0.1",port={port},log_level="error",access_log=False)'
            process = subprocess.Popen([sys.executable,'-c',command], cwd=ROOT)
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('Temporary Lab server exited.')
                try:
                    if httpx.get(base+'/api/health',trust_env=False,timeout=1).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
            raise RuntimeError('Temporary Lab server did not become ready.')
        def stop():
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
        try:
            start()
            with httpx.Client(base_url=base,trust_env=False,timeout=190) as client:
                assert client.get('/lab').status_code == 200
                catalog = client.get('/api/models').json()
                assert 'gemma4:e2b' in catalog['models']
                def task(**data):
                    response = client.post('/api/lab/tasks',json=data)
                    assert response.status_code == 201, response.text
                    return response.json()
                def operation(task, route, **body):
                    response = client.post(f"/api/lab/tasks/{task['id']}/{route}",json={'model':'gemma4:e2b','expected_revision':task['revision'],**body})
                    assert response.status_code == 200, response.text
                    packet = json.loads(response.text.splitlines()[-1])
                    assert packet['type'] == 'done', packet
                    record = packet['operation']
                    assert record['telemetry']['external_api_cost'] == 0
                    assert record['telemetry']['tokens_per_second'] is not None
                    print(f"Real Gemma {record['kind']}/{record['variant']}: latency={record['telemetry']['latency_ms']/1000:.2f}s, first content={record['telemetry']['ttft_ms']/1000:.2f}s")
                    return record
                arithmetic = task(title='Smoke arithmetic',prompt='Calculate 17 times 23. Output only the number.',context='',criteria=['Correct product','Only the number'],check_mode='exact',reference='391')
                original = operation(arithmetic,'runs')
                assert original['result']['passed'] is True
                prepared = operation(arithmetic,'runs',variant='prepared',prepared_prompt='Compute the product of the integers 17 and 23; return only its decimal representation.',confirmed=True)
                assert prepared['result']['passed'] is True
                email = task(title='Smoke missing context',prompt='Help me reply to the email I received.',context='',criteria=['Address the actual email','Do not invent the email content'])
                checked = operation(email,'prepare')
                assert checked['result']['context_sufficient'] is False
                assert checked['result']['missing_information']
                assert checked['result']['clarifying_questions']
                assert client.get('/api/conversations').json() == []
                before = client.get(f"/api/lab/tasks/{arithmetic['id']}").json()
                stop(); start()
                assert client.get(f"/api/lab/tasks/{arithmetic['id']}").json() == before
                cid = client.post('/api/conversations').json()['id']
                response = client.post(f'/api/conversations/{cid}/chat',json={'model':'gemma4:e2b','content':'Calculate 17 times 23. Output only the number.'})
                assert json.loads(response.text.splitlines()[-1])['type'] == 'done'
                message = client.get(f'/api/conversations/{cid}').json()['messages'][-1]
                source = client.get(f"/api/lab/chat-turns/{message['id']}").json()
                assert source['context_source'] == 'recorded'
                before_import = client.get('/api/usage').json()['overview']['requests']
                imported = client.post(f"/api/lab/chat-turns/{message['id']}/import",json={'criteria':['Return the correct product.','Only the number.']}).json()
                assert client.get('/api/usage').json()['overview']['requests'] == before_import
                saved = client.get(f"/api/lab/tasks/{imported['id']}").json()['operations'][0]
                assert saved['origin'] == 'chat' and saved['output'] == message['content']
                replay = operation(imported,'runs')
                assert replay['input_messages'] == source['input_messages']
                assert replay['output'].strip() == '391'
                print('PASS: real chat import reuses answer/metrics, adds zero usage, and replays recorded message input')
                long = task(title='Smoke stop',prompt='Write a very long detailed essay about mathematics.',context='',criteria=['A detailed essay'])
                with client.stream('POST',f"/api/lab/tasks/{long['id']}/runs",json={'expected_revision':1,'model':'gemma4:e2b'}) as response:
                    assert response.status_code == 200
                    for line in response.iter_lines():
                        if line and json.loads(line)['type'] == 'delta':
                            break
                for _ in range(50):
                    record = client.get(f"/api/lab/tasks/{long['id']}").json()['operations'][0]
                    if record['status'] != 'running': break
                    time.sleep(.1)
                # The model may finish between the first chunk and socket closure.
                # Both a saved cancellation and an already-completed response are valid.
                assert record['status'] == record['telemetry']['status']
                assert record['status'] in ('cancelled', 'success')
                assert record['review'] is None
                print('Real HTTP disconnect terminal status:', record['status'])
                assert client.get('/api/usage?days=0').json()['overview']['requests'] == 6
                print('PASS: real original/prepared results, missing-context JSON, local metrics, restart snapshots, cancellation, no chat pollution')
        finally:
            stop()


if __name__ == '__main__':
    main()
