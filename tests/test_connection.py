import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.credentials import CredentialError
from app.main import create_app
from app.openai_adapter import check_connection
from app.ollama_adapter import OllamaError
from test_routing import Local, packets, save


class MemorySecrets:
    def __init__(self):
        self.values = {}
        self.fail = False

    def get(self, identifier):
        return self.values.get(identifier)

    def set(self, identifier, key):
        if self.fail:
            raise CredentialError('Secure storage unavailable.')
        self.values[identifier] = key

    def delete(self, identifier):
        self.values.pop(identifier, None)


@pytest.fixture
def verified(monkeypatch):
    seen = []

    async def check(key, model):
        seen.append((key, model))
        if key == 'invalid-key':
            raise OllamaError('OpenAI did not accept that API key.')

    monkeypatch.setattr('app.main.check_connection', check)
    return seen


def test_connection_persists_only_reference_and_restores_after_restart(tmp_path, monkeypatch, verified):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_MODEL', raising=False)
    path, secrets = tmp_path / 'chat.db', MemorySecrets()
    key = 'sk-synthetic-only-do-not-use'
    with TestClient(create_app(path, Local(), secrets)) as client:
        assert client.get('/api/settings').json()['provider_ready'] is False
        config = client.get('/api/provider/connection').json()
        assert config['model'] == 'gpt-6-luna'
        response = client.put('/api/provider/connection', json={'model':'gpt-6-luna','key':key})
        assert response.status_code == 200, response.text
        assert response.json()['provider_ready'] is True
        assert response.json()['mode'] == 'always_local', 'connecting does not authorize cloud routing'
        assert response.json()['daily_limit_cents'] == 0
        assert key not in response.text + client.get('/api/provider/connection').text
        assert len(secrets.values) == 1
        assert verified == [(key, 'gpt-6-luna')]
        assert client.get('/api/usage?days=0').json()['overview']['requests'] == 0
    assert key.encode() not in path.read_bytes()
    with TestClient(create_app(path, Local(), secrets)) as client:
        assert client.get('/api/settings').json()['provider_ready'] is True
        assert save(client, 'manual_handoff', cents=10).is_success
        assert client.put('/api/provider/connection', json={'model':'gpt-6-luna','key':None}).is_success
        assert len(secrets.values) == 1, 'old app-owned credential is cleaned up'
        assert client.get('/api/settings').json()['mode'] == 'manual_handoff'
    with TestClient(create_app(path, Local(), MemorySecrets())) as client:
        assert client.get('/api/settings').json()['provider_ready'] is False
        assert 'unavailable' in client.get('/api/provider/connection').json()['error']
        assert client.get('/api/health').is_success


def test_connection_failures_do_not_replace_existing_config_or_echo_keys(tmp_path, monkeypatch, verified):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_MODEL', raising=False)
    secrets = MemorySecrets()
    app = create_app(tmp_path / 'chat.db', Local(), secrets)
    with TestClient(app) as client:
        route = '/api/provider/connection'
        key = 'sk-previous-synthetic-key'
        assert client.put(route, json={'model':'gpt-6-luna','key':key}).is_success
        for body in [{'key':key}, {'model':'not-supported','key':key},
                     {'model':'gpt-6-luna','key':'invalid-key'},
                     {'model':'gpt-6-luna','key':'sk-key\nwith-newline'}]:
            response = client.put(route, json=body)
            assert response.status_code == 422
            assert key not in response.text
            assert app.state.routing.key == key
        secrets.fail = True
        response = client.put(route, json={'model':'gpt-4o-mini','key':'sk-another-synthetic-key'})
        assert response.status_code == 422
        assert app.state.routing.model == 'gpt-6-luna'
        assert app.state.routing.key == key
        assert app.state.busy is False
        assert client.put(route, json={'model':'gpt-6-luna','key':key}, headers={'Origin':'https://evil.example'}).status_code == 403
        app.state.busy = True
        assert client.put(route, json={'model':'gpt-6-luna','key':key}).status_code == 409
        app.state.busy = False


def test_file_connection_loads_without_exposing_or_persisting_key(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_MODEL', raising=False)
    monkeypatch.setenv('SYNTHETIC_SUFFIX', 'must-not-expand')
    env_file = tmp_path / '.env'
    key = 'sk-synthetic-${SYNTHETIC_SUFFIX}'
    env_file.write_text(f'OPENAI_API_KEY={key}\n')
    (tmp_path / 'app' / 'static').mkdir(parents=True)
    monkeypatch.setattr('app.main.ROOT', tmp_path / 'app')
    app = create_app(adapter=Local())
    with TestClient(app) as client:
        assert app.state.routing.key == key
        settings = client.get('/api/settings')
        assert settings.json()['provider_ready'] is True
        assert settings.json()['frontier_model'] == 'gpt-6-luna'
        assert settings.json()['mode'] == 'always_local'
        assert settings.json()['daily_limit_cents'] == 0
        assert key not in settings.text + client.get('/api/provider/connection').text
    assert key.encode() not in (tmp_path / 'data' / 'localfirst.sqlite3').read_bytes()
    with TestClient(create_app(tmp_path / 'isolated.db', Local())) as client:
        assert client.get('/api/settings').json()['provider_ready'] is False


def test_file_and_environment_override_saved_connection(tmp_path, monkeypatch, verified):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_MODEL', raising=False)
    path, secrets = tmp_path / 'chat.db', MemorySecrets()
    with TestClient(create_app(path, Local(), secrets)) as client:
        assert client.put('/api/provider/connection', json={'model':'gpt-6-luna','key':'sk-synthetic-saved'}).is_success
    env_file = tmp_path / '.env'
    env_file.write_text('OPENAI_API_KEY=sk-synthetic-file\nOPENAI_MODEL=gpt-4o-mini\n')
    app = create_app(path, Local(), secrets, env_file=env_file)
    with TestClient(app):
        assert (app.state.routing.key, app.state.routing.model) == ('sk-synthetic-file', 'gpt-4o-mini')
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-synthetic-environment')
    monkeypatch.setenv('OPENAI_MODEL', 'gpt-6-luna')
    with TestClient(app):
        assert (app.state.routing.key, app.state.routing.model) == ('sk-synthetic-environment', 'gpt-6-luna')
    monkeypatch.delenv('OPENAI_API_KEY')
    monkeypatch.delenv('OPENAI_MODEL')
    env_file.write_text('OPENAI_API_KEY=\nOPENAI_MODEL=gpt-4o-mini\n')
    with TestClient(app):
        assert (app.state.routing.key, app.state.routing.model) == ('sk-synthetic-saved', 'gpt-6-luna')


@pytest.mark.parametrize('status, message', [(401,'did not accept'), (403,'cannot access'),
                                            (404,'cannot access'), (429,'could not verify')])
async def test_connection_metadata_errors_are_safe_and_never_generate(monkeypatch, status, message):
    original = httpx.AsyncClient

    def handle(request):
        assert request.method == 'GET'
        assert str(request.url) == 'https://api.openai.com/v1/models/gpt-6-luna'
        assert request.headers['authorization'] == 'Bearer test-key'
        return httpx.Response(status, json={'error':{'message':'Never surface this raw key: test-key'}})

    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    with pytest.raises(OllamaError, match=message) as error:
        await check_connection('test-key', 'gpt-6-luna')
    assert 'test-key' not in str(error.value)


async def test_connection_metadata_success(monkeypatch):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'id':'gpt-6-luna'})), **kw))
    await check_connection('test-key', 'gpt-6-luna')


def test_missing_setup_has_actionable_handoff_errors(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_MODEL', raising=False)
    app = create_app(tmp_path / 'chat.db', Local())
    with TestClient(app) as client:
        app.state.routing.save(type('Settings', (), {'mode':'manual_handoff','daily_limit_cents':10})())
        cid = client.post('/api/conversations').json()['id']
        mid = packets(client.post(f'/api/conversations/{cid}/chat', json={'content':'Synthetic request'}))[0]['message_id']
        route = f'/api/conversations/{cid}/messages/{mid}/handoff/preview'
        response = client.post(route)
        assert response.status_code == 503
        assert response.headers['X-LocalFirst-Action'] == 'connect-openai'
        assert app.state.busy is False
        app.state.routing.key, app.state.routing.model = 'test-key', 'gpt-6-luna'
        app.state.routing.save(type('Settings', (), {'mode':'manual_handoff','daily_limit_cents':0})())
        response = client.post(route)
        assert response.status_code == 409
        assert response.headers['X-LocalFirst-Action'] == 'set-cloud-limit'


def test_manual_bad_local_json_offers_reviewable_fallback_without_sending(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv('OPENAI_MODEL', 'gpt-6-luna')

    class InvalidLocal(Local):
        async def stream(self, model, messages):
            yield {'message':{'content':'Not JSON; original draft.'}, 'done':True, 'model':model}

    with TestClient(create_app(tmp_path / 'chat.db', InvalidLocal())) as client:
        save(client, 'manual_handoff')
        cid = client.post('/api/conversations').json()['id']
        mid = packets(client.post(f'/api/conversations/{cid}/chat', json={'content':'Explain compound interest simply.'}))[0]['message_id']
        response = client.post(f'/api/conversations/{cid}/messages/{mid}/handoff/preview')
        assert response.is_success, response.text
        preview = response.json()
        assert preview['preparation_note']
        assert preview['brief']['latest_request'] == 'Explain compound interest simply.'
        assert 'Not JSON; original draft.' in preview['brief']['source_excerpts']
        assert client.get('/api/usage?days=0').json()['overview']['requests'] == 1
