import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.routing import bounded, MAX_INPUT_BYTES


class Local:
    calls = 0
    assessment = 'needs_frontier_help'

    async def close(self):
        pass

    async def models(self):
        return ['test-local']

    async def stream(self, model, messages):
        self.calls += 1
        answer = 'Local result'
        if messages[0]['role'] == 'system':
            answer = json.dumps(dict(disposition=self.assessment, summary='Synthetic summary',
                                     facts_and_constraints='Synthetic only', task='Check the result',
                                     source_excerpts='', reason='A focused second review is needed.'))
        yield {'message': {'content': answer}, 'done': True, 'model': model}


def packets(response):
    assert response.status_code == 200, response.text
    return list(map(json.loads, response.text.splitlines()))


def save(client, mode, cents=1, acknowledged=True):
    return client.put('/api/settings', json=dict(mode=mode, daily_limit_cents=cents, acknowledged=acknowledged))


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv('OPENAI_MODEL', 'gpt-6-luna')
    seen = []

    async def stream(routing, messages):
        seen.append(messages)
        yield {'message': {'content': 'Frontier result'}, 'model': routing.model}
        yield {'done': True, 'prompt_eval_count': 20, 'eval_count': 4}

    monkeypatch.setattr('app.main.stream_openai', stream)
    return seen


@pytest.mark.parametrize('mode', ['always_local', 'manual_handoff', 'automatic_handoff', 'always_frontier'])
def test_settings_persist(tmp_path, configured, mode):
    path = tmp_path / 'chat.db'
    with TestClient(create_app(path, Local())) as client:
        assert client.get('/api/settings').json()['mode'] == 'always_local'
        assert save(client, mode).is_success
    with TestClient(create_app(path, Local())) as client:
        settings = client.get('/api/settings').json()
        assert settings == dict(mode=mode, daily_limit_cents=1, frontier_model='gpt-6-luna', provider_ready=True)


def test_settings_require_readiness_and_acknowledgment(tmp_path, configured, monkeypatch):
    with TestClient(create_app(tmp_path / 'ready.db', Local())) as client:
        assert save(client, 'always_frontier', acknowledged=False).status_code == 422
        assert save(client, 'automatic_handoff', cents=0).status_code == 422
    monkeypatch.delenv('OPENAI_API_KEY')
    with TestClient(create_app(tmp_path / 'offline.db', Local())) as client:
        assert save(client, 'manual_handoff').status_code == 422


@pytest.mark.parametrize('mode', ['always_local', 'manual_handoff', 'automatic_handoff', 'always_frontier'])
def test_routes(tmp_path, configured, mode):
    local = Local()
    path = tmp_path / 'chat.db'
    with TestClient(create_app(path, local)) as client:
        assert save(client, mode).is_success
        cid = client.post('/api/conversations').json()['id']
        base = f'/api/conversations/{cid}'
        result = packets(client.post(base + '/chat', json={'content': 'Synthetic request'}))
        if mode == 'manual_handoff':
            mid = result[0]['message_id']
            handoff = f'{base}/messages/{mid}/handoff'
            preview_response = client.post(handoff + '/preview')
            assert preview_response.is_success, preview_response.text
            preview = preview_response.json()
            assert configured == []
            preview['brief']['task'] = 'Edited task'
            packets(client.post(handoff, json=dict(preview['brief'], token=preview['token'])))
            assert 'Edited task' in configured[0][0]['content']
            assert client.post(handoff, json=dict(preview['brief'], token=preview['token'])).status_code == 409
        if mode == 'always_local':
            assert not configured
        elif mode == 'always_frontier':
            assert local.calls == 0
            assert configured == [[{'role': 'user', 'content': 'Synthetic request'}]]
        else:
            assert local.calls == 2
            assert len(configured) == 1
            assert 'Synthetic summary' in configured[0][0]['content']

    with TestClient(create_app(path, local)) as client:
        messages = client.get(base).json()['messages']
        if mode != 'always_local':
            assert messages[-1]['telemetry']['external_api_cost'] == 0.000004
            assert messages[-1]['telemetry']['input_tokens'] == 20
        if mode in ('manual_handoff', 'automatic_handoff'):
            assert messages[-1]['handoff_of'] == messages[-2]['id']
            assert messages[-2]['content'] == 'Local result'
            assert messages[-1]['handoff_brief'] == configured[0][0]['content']


@pytest.mark.parametrize('disposition', ['answered', 'needs_user_input', 'uncertain'])
def test_automatic_outcomes_stay_local(tmp_path, configured, disposition):
    local = Local()
    local.assessment = disposition
    with TestClient(create_app(tmp_path / 'chat.db', local)) as client:
        assert save(client, 'automatic_handoff').is_success
        cid = client.post('/api/conversations').json()['id']
        packets(client.post(f'/api/conversations/{cid}/chat', json={'content': 'Synthetic request'}))
        assert not configured


def test_reservations_are_atomic_and_unknown_survives_restart(tmp_path, configured):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / 'chat.db'
    app = create_app(path, Local())
    with TestClient(app) as client:
        assert save(client, 'always_frontier').is_success
        routing = app.state.routing
        messages = bounded([{'role': 'user', 'content': 'é' * MAX_INPUT_BYTES}])
        assert len(messages[0]['content'].encode()) == MAX_INPUT_BYTES
        with ThreadPoolExecutor(max_workers=12) as pool:
            reserved = list(pool.map(lambda number: routing.reserve(str(number), messages, 1), range(16)))
        assert sum(reserved) == 10_000_000 // routing.estimate(messages)

    with TestClient(create_app(path, Local())) as client:
        budget = client.get('/api/usage').json()['cloud_budget']
        assert 0 < budget['unresolved_estimate'] == budget['reserved_or_charged'] <= 0.01
        cid = client.post('/api/conversations').json()['id']
        # Fill the remaining allowance so even a small request cannot reserve funds.
        while client.app.state.routing.reserve(f'fill-{budget["reserved_or_charged"]}', [{'role': 'user', 'content': 'x'}], 1):
            budget = client.app.state.routing.daily_usage()
        response = client.post(f'/api/conversations/{cid}/chat', json={'content': 'x'})
        assert response.status_code == 409
        assert not configured


def test_failed_frontier_keeps_partial_and_reservation(tmp_path, configured, monkeypatch):
    from app.ollama_adapter import OllamaError

    async def fail_after_delta(routing, messages):
        yield {'message': {'content': 'Partial'}}
        raise OllamaError('OpenAI stream failed.')

    monkeypatch.setattr('app.main.stream_openai', fail_after_delta)
    path = tmp_path / 'chat.db'
    with TestClient(create_app(path, Local())) as client:
        assert save(client, 'always_frontier').is_success
        cid = client.post('/api/conversations').json()['id']
        base = f'/api/conversations/{cid}'
        turn = packets(client.post(base + '/chat', json={'content': 'A synthetic request'}))
        assert [packet['type'] for packet in turn] == ['start', 'delta', 'error']
    with TestClient(create_app(path, Local())) as client:
        reply = client.get(base).json()['messages'][-1]
        assert reply['status'] == 'error'
        assert reply['content'] == 'Partial'
        assert reply['telemetry']['input_tokens'] is None
        assert reply['telemetry']['external_api_cost'] is None
        assert client.get('/api/usage').json()['cloud_budget']['unresolved_estimate'] > 0


def test_adapter_sends_bounded_stream_request_and_translates_usage(monkeypatch):
    import asyncio

    import httpx

    from app.openai_adapter import stream_openai
    from app.routing import MAX_OUTPUT_TOKENS

    client_class = httpx.AsyncClient
    data = [
        {'model': 'gpt-6-luna', 'choices': [{'delta': {'content': 'ACK'}}]},
        {'choices': [], 'usage': {'prompt_tokens': 11, 'completion_tokens': 2}},
    ]

    def handle(request):
        assert str(request.url) == 'https://api.openai.com/v1/chat/completions'
        assert request.headers['Authorization'] == 'Bearer test-key'
        assert json.loads(request.content) == {
            'model': 'gpt-6-luna', 'messages': [{'role': 'user', 'content': 'ACK'}],
            'stream': True, 'stream_options': {'include_usage': True},
            'max_completion_tokens': MAX_OUTPUT_TOKENS, 'store': False, 'service_tier': 'default',
            'reasoning_effort': 'none',
        }
        frames = ''.join(f'data: {json.dumps(packet)}\n\n' for packet in data)
        return httpx.Response(200, text=frames + 'data: [DONE]\n\n')

    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: client_class(transport=httpx.MockTransport(handle), **kwargs))

    async def collect():
        from types import SimpleNamespace

        config = SimpleNamespace(model='gpt-6-luna', key='test-key')
        return [packet async for packet in stream_openai(config, [{'role': 'user', 'content': 'ACK'}])]

    first, last = asyncio.run(collect())
    assert first['message']['content'] == 'ACK'
    assert last == {'done': True, 'prompt_eval_count': 11, 'eval_count': 2}
