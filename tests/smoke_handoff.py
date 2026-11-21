"""Real local-model handoff preparation; synthetic text, temporary DB, no cloud call."""
import os
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app.main as backend
from app.handoff import payload


os.environ['OPENAI_API_KEY'] = 'synthetic-key-never-sent'
os.environ['OPENAI_MODEL'] = 'gpt-6-luna'


async def forbidden(*args):
    raise AssertionError('This smoke check must never call a cloud model.')
    yield


backend.stream_openai = forbidden
with tempfile.TemporaryDirectory(prefix='localfirst-handoff-') as directory:
    with TestClient(backend.create_app(Path(directory) / 'chat.db')) as client:
        assert client.put('/api/settings', json={'mode':'manual_handoff','daily_limit_cents':10,'acknowledged':False}).is_success
        cid = client.post('/api/conversations').json()['id']
        question = 'Name the capital of France in one sentence.'
        response = client.post(f'/api/conversations/{cid}/chat', json={'model':'gemma4:e2b','content':question})
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[-1]['type'] == 'done', events[-1]
        mid = events[0]['message_id']
        preview = client.post(f'/api/conversations/{cid}/messages/{mid}/handoff/preview')
        assert preview.is_success, preview.text
        result = preview.json()
        assert result['brief']['latest_request'] == question
        assert payload(result['brief'])
        assert client.get('/api/usage?days=0').json()['overview']['requests'] == 1
        assert len(client.get(f'/api/conversations/{cid}').json()['messages']) == 2
        print('PASS: real Gemma answer and editable handoff preview; original request preserved; no cloud call.')
        print('Source fallback needed:', bool(result['preparation_note']))
