"""Real public search + installed Gemma, synthetic question and temporary DB."""
import json
import re
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app.main as backend


async def no_cloud(*args, **kwargs):
    raise AssertionError('This check must never call a cloud model.')
    yield


backend.stream_openai = no_cloud
with tempfile.TemporaryDirectory(prefix='localfirst-web-') as directory:
    path = Path(directory) / 'chat.db'
    with TestClient(backend.create_app(path)) as client:
        catalog = client.get('/api/models').json()
        assert 'gemma4:e2b' in catalog.get('models', []), catalog
        cid = client.post('/api/conversations').json()['id']
        response = client.post(f'/api/conversations/{cid}/chat',json={
            'content':'What is Grand Theft Auto VI?',
            'model':'gemma4:e2b', 'web_search':True})
        assert response.status_code == 200, response.text
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[-1]['type'] == 'done', events[-1]
        sources = next(e['web_context'] for e in events if e['type'] == 'web_sources')
        answer = ''.join(e['content'] for e in events if e['type'] == 'delta')
        assert sources['sources'] and any('rockstargames.com' in s['url'] for s in sources['sources']), sources
        assert 'Grand Theft Auto' in answer and re.search(r'\[[1-4](?:,\s*[1-4])*\]', answer), answer
        assert events[-1]['telemetry']['execution_location'] == 'local'
        before = client.get(f'/api/conversations/{cid}').json()
        assert before['messages'][-1]['web_context'] == sources
        print('Search sources:', json.dumps([{'title':s['title'],'url':s['url'],'excerpt':s['excerpt']} for s in sources['sources']], ensure_ascii=False))
        print('Real Gemma answer:', answer)
    with TestClient(backend.create_app(path)) as client:
        assert client.get(f'/api/conversations/{cid}').json() == before
    print('PASS: real public search, local Gemma answer with source links and persisted sources; no cloud model call.')
