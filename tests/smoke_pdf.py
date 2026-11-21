"""Real installed-Gemma PDF smoke test; synthetic PDF, temporary DB, no paid calls."""
import sys
import tempfile
import json
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import create_app
from pdf_fixtures import make_pdf


def main():
    with tempfile.TemporaryDirectory(prefix='localfirst-pdf-') as directory:
        path = Path(directory) / 'chat.sqlite3'
        with TestClient(create_app(path)) as client:
            catalog = client.get('/api/models').json()
            assert 'gemma4:e2b' in catalog.get('models', []), catalog
            cid = client.post('/api/conversations').json()['id']
            base = f'/api/conversations/{cid}'
            upload = client.post(base + '/documents?filename=synthetic.pdf',
                                 content=make_pdf(['Project CedarMoon\nThe approved budget is USD 18400.',
                                                   'The lead for Project CedarMoon is Riley.']),
                                 headers={'Content-Type':'application/pdf'})
            assert upload.status_code == 201, upload.text
            doc = upload.json()
            for body, expected in [({'content':'What is the approved budget? Cite the page.', 'document_id':doc['id']}, '18400'),
                                   ({'content':'Who is the project lead? Cite the page.'}, 'Riley')]:
                response = client.post(base + '/chat', json=dict(body, model='gemma4:e2b'))
                assert response.status_code == 200, response.text
                events = [json.loads(line) for line in response.text.splitlines()]
                assert events[-1]['type'] == 'done', events[-1]
                answer = ''.join(e['content'] for e in events if e['type'] == 'delta')
                assert expected in (re.sub(r'\D', '', answer) if expected.isdigit() else answer), answer
                assert events[-1]['telemetry']['execution_location'] == 'local'
                print('Real Gemma PDF answer:', answer)
            before = client.get(base).json()
        with TestClient(create_app(path)) as client:
            assert client.get(base).json() == before
            assert client.get('/api/usage?days=0').json()['overview']['external_api_cost'] == 0
        print('PASS: real Gemma reads PDF, answers follow-up, and preserves local context across restart.')


if __name__ == '__main__':
    main()
