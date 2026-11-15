import asyncio
import json
import threading
import time
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.ollama_adapter import OllamaAdapter, OllamaError


class FakeOllama:
    def __init__(self, mode='ok'):
        self.mode = mode
        self.requests = []
        self.closed = False
        self.stream_closed = threading.Event()

    async def close(self):
        self.closed = True

    async def models(self):
        if self.mode == 'offline':
            raise OllamaError('Cannot connect to Ollama at localhost:11434.')
        return ['llama3.2:3b', 'other:small']

    async def stream(self, model, messages):
        self.requests.append((model, messages))
        try:
            if self.mode == 'timeout':
                raise OllamaError('Ollama timed out.')
            if self.mode == 'empty':
                yield {'done': True}
                return
            yield {'message': {'content': 'Hello '}}
            if self.mode == 'error':
                raise OllamaError('Ollama connection failed.')
            if self.mode == 'slow':
                await asyncio.sleep(60)
            yield {'message': {'content':'world'}, 'done':True, 'model':model,
                   'prompt_eval_count':9, 'eval_count':2}
        finally:
            self.stream_closed.set()


@contextmanager
def client_for(tmp_path, mode='ok'):
    fake = FakeOllama(mode)
    with TestClient(create_app(tmp_path / 'db.sqlite3', fake)) as client:
        yield client, fake
    assert fake.closed


def create(client):
    response = client.post('/api/conversations')
    assert response.status_code == 201
    return response.json()['id']


def send(client, cid, **body):
    return client.post(f'/api/conversations/{cid}/chat', json={'content':'hello', **body})


def packets(response):
    return [json.loads(line) for line in response.text.splitlines()]


def test_chat_followup_metrics_models_and_restart(tmp_path):
    with client_for(tmp_path) as (client, fake):
        assert client.get('/').status_code == 200
        assert client.get('/static/app.js').status_code == 200
        assert client.get('/api/health').json()['provider'] == 'local'
        assert client.get('/api/models').json()['models'] == ['llama3.2:3b','other:small']
        cid = create(client)
        result = packets(send(client, cid))
        assert [p['type'] for p in result] == ['start','delta','delta','done']
        assert result[-1]['output_tokens'] == 2
        assert result[-1]['latency_ms'] >= 0
        assert result[-1]['external_api_spend'] == 0
        send(client, cid, content='follow up', model='other:small')
        assert fake.requests[-1] == ('other:small', [
            {'role':'user','content':'hello'}, {'role':'assistant','content':'Hello world'},
            {'role':'user','content':'follow up'}])
    with client_for(tmp_path) as (client, fake):
        saved = client.get(f'/api/conversations/{cid}').json()
        assert len(saved['messages']) == 4
        assert saved['messages'][-1]['model'] == 'other:small'
        assert saved['messages'][-1]['prompt_tokens'] == 9
        assert client.get('/api/conversations').json()[0]['id'] == cid


@pytest.mark.parametrize('mode,fragment', [('empty','empty'), ('timeout','timed out'), ('error','connection failed')])
def test_generation_errors_saved_and_lock_released(tmp_path, mode, fragment):
    with client_for(tmp_path, mode) as (client, fake):
        cid = create(client)
        result = packets(send(client,cid))
        assert result[-1]['type'] == 'error'
        assert fragment in result[-1]['message']
        assert not any(p['type'] == 'done' for p in result)
        message = client.get(f'/api/conversations/{cid}').json()['messages'][-1]
        assert message['status'] == 'error'
        assert fake.stream_closed.is_set()
        fake.mode = 'ok'
        assert packets(send(client,cid))[-1]['type'] == 'done'
        assert all(m['content'] != 'Hello ' for m in fake.requests[-1][1])


def test_offline_validation_and_origin(tmp_path):
    with client_for(tmp_path, 'offline') as (client, fake):
        assert client.get('/api/models').status_code == 503
        cid = create(client)
        assert send(client,cid).status_code == 503
        fake.mode = 'ok'
        assert send(client,cid,model='not-installed').status_code == 400
        assert send(client,cid,content='  ').status_code == 422
        assert send(client,cid,content='x'*16001).status_code == 422
        assert send(client,'missing').status_code == 404
        assert client.post('/api/conversations',headers={'Origin':'https://example.com'}).status_code == 403
        assert client.get('/',headers={'Host':'evil.example'}).status_code == 400
        assert client.get(f'/api/conversations/{cid}').json()['messages'] == []
        assert packets(send(client,cid))[-1]['type'] == 'done'


def test_bounded_context_notice(tmp_path):
    with client_for(tmp_path) as (client,fake):
        cid = create(client)
        for _ in range(8):
            response = send(client,cid)
        assert packets(response)[0]['omitted_messages'] == 2
        assert len(fake.requests[-1][1]) == 13
        assert len(client.get(f'/api/conversations/{cid}').json()['messages']) == 16


async def test_disconnect_cancels_upstream_and_releases_lock(tmp_path):
    """Drive ASGI directly: TestClient buffers streams and cannot simulate disconnects."""
    fake = FakeOllama('slow')
    app = create_app(tmp_path / 'db.sqlite3', fake)
    async with app.router.lifespan_context(app):
        cid = app.state.storage.create()['id']
        got_delta = asyncio.Event()
        request_read = False
        response_packets = []

        async def receive():
            nonlocal request_read
            if not request_read:
                request_read = True
                return {'type':'http.request','body':json.dumps({'content':'hello'}).encode(),'more_body':False}
            await got_delta.wait()
            # Concurrent attempts must fail while the first stream is active.
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
                response = await client.post(f'/api/conversations/{cid}/chat', json={'content':'second'})
                assert response.status_code == 409
            return {'type':'http.disconnect'}

        async def send_event(event):
            if event['type'] == 'http.response.body' and event.get('body'):
                response_packets.append(event['body'])
                if b'"delta"' in event['body']:
                    got_delta.set()

        scope = {'type':'http','asgi':{'version':'3.0','spec_version':'2.0'},'http_version':'1.1',
                 'method':'POST','scheme':'http','path':f'/api/conversations/{cid}/chat',
                 'raw_path':f'/api/conversations/{cid}/chat'.encode(),'query_string':b'',
                 'headers':[(b'host',b'testserver'),(b'content-type',b'application/json')],
                 'client':('127.0.0.1',12345),'server':('testserver',80)}
        await asyncio.wait_for(app(scope, receive, send_event), timeout=5)
        assert fake.stream_closed.is_set()
        assert app.state.busy is False
        message = app.state.storage.conversation(cid)['messages'][-1]
        assert message['status'] == 'stopped' and message['content'] == 'Hello '
        telemetry = message['telemetry']
        assert telemetry['status'] == 'cancelled'
        assert telemetry['ttft_ms'] >= 0
        assert telemetry['output_tokens'] is None
        assert telemetry['external_api_cost'] == 0
        assert app.state.telemetry.analytics()['overview']['cancellation_rate'] == 100
        assert not any(b'"done"' in part for part in response_packets)


@pytest.mark.parametrize('kind', ['offline','timeout','404','500','bad_json','provider_error','truncated','empty'])
async def test_adapter_errors(kind):
    def handler(request):
        if kind == 'offline': raise httpx.ConnectError('offline', request=request)
        if kind == 'timeout': raise httpx.ReadTimeout('timeout', request=request)
        if kind in ('404','500'): return httpx.Response(int(kind))
        body = {'bad_json':'{invalid\n', 'provider_error':'{"error":"failure"}\n',
                'truncated':'{"message":{"content":"partial"}}\n', 'empty':''}[kind]
        return httpx.Response(200, content=body)
    adapter = OllamaAdapter(httpx.MockTransport(handler))
    try:
        with pytest.raises(OllamaError):
            async for _ in adapter.stream('llama3.2:3b', []):
                pass
    finally:
        await adapter.close()


async def test_adapter_incremental_stream_and_cleanup():
    class Stream(httpx.AsyncByteStream):
        closed = False
        async def __aiter__(self):
            yield b'{"message":{"content":"one"}}\n'
            await asyncio.sleep(0)
            yield b'{"message":{"content":"two"},"done":true,"eval_count":2}\n'
        async def aclose(self):
            self.closed = True
    stream = Stream()
    def handler(request):
        if request.url.path == '/api/tags': return httpx.Response(200,json={'models':[{'name':'llama3.2:3b'}]})
        payload = json.loads(request.content)
        assert payload['stream'] is True and payload['options']['num_ctx'] == 4096
        return httpx.Response(200,stream=stream)
    adapter = OllamaAdapter(httpx.MockTransport(handler))
    try:
        assert await adapter.models() == ['llama3.2:3b']
        values = [p async for p in adapter.stream('llama3.2:3b',[])]
        assert [p['message']['content'] for p in values] == ['one','two']
        assert stream.closed
    finally:
        await adapter.close()


def test_total_generation_timeout_closes_stream(tmp_path, monkeypatch):
    monkeypatch.setattr('app.main.GENERATION_TIMEOUT_SECONDS', .01)
    with client_for(tmp_path, 'slow') as (client, fake):
        cid = create(client)
        result = packets(send(client, cid))
        assert result[-1]['type'] == 'error'
        assert 'limit' in result[-1]['message']
        assert fake.stream_closed.is_set()
        assert client.get(f'/api/conversations/{cid}').json()['messages'][-1]['status'] == 'error'
        fake.mode = 'ok'
        assert packets(send(client, cid))[-1]['type'] == 'done'


@pytest.mark.parametrize('payload', [{}, {'models':None}, {'models':[{'name':None}]}, {'models':[{}]}])
async def test_invalid_models(payload):
    adapter = OllamaAdapter(httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))
    try:
        with pytest.raises(OllamaError, match='invalid model list'):
            await adapter.models()
    finally:
        await adapter.close()


async def test_no_models_is_valid_discovery():
    adapter = OllamaAdapter(httpx.MockTransport(lambda request: httpx.Response(200, json={'models':[]})))
    try:
        assert await adapter.models() == []
    finally:
        await adapter.close()


def test_gemma_preferred_only_when_installed_and_explicit_selection_preserved(tmp_path):
    with client_for(tmp_path) as (client, fake):
        assert client.get('/api/models').json()['default'] == 'llama3.2:3b'
        async def installed():
            return ['llama3.2:3b', 'gemma4:e2b']
        fake.models = installed
        models = client.get('/api/models').json()
        assert models['default'] == 'gemma4:e2b'
        assert models['labels']['gemma4:e2b'] == 'Lightweight · Gemma 4 E2B'
        cid = create(client)
        result = packets(send(client, cid))
        assert fake.requests[-1][0] == 'gemma4:e2b'
        assert result[-1]['telemetry']['model'] == 'gemma4:e2b'
        send(client, cid, model='llama3.2:3b')
        assert fake.requests[-1][0] == 'llama3.2:3b'
        assert send(client, cid, model='gemma4:missing').status_code == 400


@pytest.mark.parametrize('model,thinking', [('gemma4:e2b', False), ('llama3.2:3b', None)])
async def test_gemma_lightweight_thinking_policy(model, thinking):
    def handler(request):
        payload = json.loads(request.content)
        assert payload.get('think') is thinking
        assert payload['model'] == model
        return httpx.Response(200, content='{"message":{"content":"Answer"},"done":true}\n')
    adapter = OllamaAdapter(httpx.MockTransport(handler))
    try:
        values = [packet async for packet in adapter.stream(model, [])]
        assert values[-1]['done'] is True
    finally:
        await adapter.close()
