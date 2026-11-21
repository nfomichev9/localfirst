import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.documents import (DocumentError, MAX_FILE_BYTES, MAX_INPUT_BYTES, PDF_CONTEXT_PREFIX,
                           PDF_CONTEXT_WINDOW, extract_pdf, pdf_context, read_pdf)
from app.main import create_app
from app.ollama_adapter import OllamaAdapter
from pdf_fixtures import make_pdf
from test_api import FakeOllama, create, packets, send


def upload(client, cid, content=None, filename='brief.pdf'):
    return client.post(f'/api/conversations/{cid}/documents', params={'filename': filename},
                       content=content if content is not None else make_pdf([
                           'Project CedarMoon\nThe approved budget is USD 18400.',
                           'The launch date is December 12.\nThe lead is Riley.',
                       ]), headers={'Content-Type': 'application/pdf'})


def test_extraction_page_labels_missing_text_and_invalid_documents():
    result = extract_pdf(make_pdf(['First page', None, 'Third page']))
    assert result['page_count'] == 3
    assert result['unreadable_pages'] == [2]
    assert [p['text'] for p in result['pages']] == ['First page', '', 'Third page']
    for data, message in [(b'not pdf', 'not a readable PDF'), (b'%PDF-broken', 'Could not read'),
                          (make_pdf([None]), 'No readable text'),
                          (make_pdf(['Secret'], encrypted=True), 'password-protected'),
                          (make_pdf(['x'] * 151), '150 pages')]:
        with pytest.raises(DocumentError, match=message):
            extract_pdf(data)


def test_pdf_chat_followup_retry_restart_and_scope(tmp_path):
    path = tmp_path / 'chat.db'
    fake = FakeOllama('error')
    with TestClient(create_app(path, fake)) as client:
        cid = create(client)
        document = upload(client, cid).json()
        assert document['filename'] == 'brief.pdf'
        assert document['page_count'] == 2
        assert 'pages' not in document
        assert not fake.requests, 'upload does not generate or add telemetry'
        first = packets(send(client, cid, content='What is the approved budget?', document_id=document['id']))
        assert first[0]['document_context']['excerpts'] is False
        inputs = fake.requests[-1][1]
        assert inputs[0]['content'].startswith(PDF_CONTEXT_PREFIX)
        assert '[Page 1]' in inputs[0]['content'] and '18400' in inputs[0]['content']
        assert '[Page 2]' in inputs[0]['content']
        failed_id = first[0]['message_id']
        assert client.delete(f'/api/conversations/{cid}/documents/{document["id"]}').status_code == 409
        other = create(client)
        assert send(client, other, document_id=document['id']).status_code == 404
        assert client.delete(f'/api/conversations/{other}/documents/{document["id"]}').status_code == 409
    fake = FakeOllama()
    with TestClient(create_app(path, fake)) as client:
        retry = client.post(f'/api/conversations/{cid}/messages/{failed_id}/retry', json={'model': 'other:small'})
        assert packets(retry)[0]['document_context']['id'] == document['id']
        assert fake.requests[-1][1] == inputs
        followup = packets(send(client, cid, content='Who is the lead?'))
        assert followup[-1]['type'] == 'done'
        assert 'Riley' in fake.requests[-1][1][0]['content']
        saved = client.get(f'/api/conversations/{cid}').json()
        assert saved['document'] == document
        assert saved['messages'][0]['content'] == 'What is the approved budget?'
        assert saved['messages'][0]['document'] == document
        assert saved['messages'][-1]['document_context']['pages_used'] == [1, 2]
        assert saved['messages'][-1]['telemetry']['execution_location'] == 'local'
        assert client.get('/api/usage?days=0').json()['overview']['requests'] == 3
        pending = upload(client, cid, filename='replacement.pdf').json()
        assert client.delete(f'/api/conversations/{cid}/documents/{pending["id"]}').status_code == 204
        assert client.get(f'/api/conversations/{cid}').json()['document'] == document
    assert not list(tmp_path.glob('*.pdf')), 'original PDF bytes are not archived'


@pytest.mark.parametrize('mode', ['always_frontier', 'automatic_handoff', 'manual_handoff'])
def test_pdf_stays_local_in_every_routing_mode(tmp_path, monkeypatch, mode):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv('OPENAI_MODEL', 'gpt-6-luna')

    async def forbidden(*args, **kwargs):
        pytest.fail('PDF content reached a cloud or handoff adapter')
        yield

    monkeypatch.setattr('app.main.stream_openai', forbidden)
    monkeypatch.setattr('app.main.prepare', forbidden)
    with TestClient(create_app(tmp_path / 'chat.db', FakeOllama())) as client:
        assert client.put('/api/settings', json={'mode': mode, 'daily_limit_cents': 1, 'acknowledged': True}).is_success
        cid = create(client)
        doc = upload(client, cid).json()
        first = packets(send(client, cid, document_id=doc['id']))
        assert first[0]['routing_mode'] == 'always_local'
        assert first[0]['provider'] == 'ollama'
        assert packets(send(client, cid, content='Follow up'))[-1]['provider'] == 'local'
        mid = first[0]['message_id']
        assert client.post(f'/api/conversations/{cid}/messages/{mid}/handoff/preview').status_code == 409
        assert client.post(f'/api/conversations/{cid}/messages/{mid}/handoff', json={
            'summary':'x', 'facts_and_constraints':'x', 'task':'x', 'latest_request':'x',
            'source_excerpts':'x', 'token':'x'}).status_code == 409
        assert client.get('/api/settings').json()['mode'] == mode


def test_upload_limits_errors_and_no_state_mutation(tmp_path):
    app = create_app(tmp_path / 'chat.db', FakeOllama())
    with TestClient(app) as client:
        cid = create(client)
        assert upload(client, 'missing').status_code == 404
        assert upload(client, cid, filename='bad.pptx').status_code == 422
        assert upload(client, cid, b'bad').status_code == 422
        assert 'not a readable PDF' in upload(client, cid, b'bad').json()['detail']
        assert 'OCR' in upload(client, cid, make_pdf([None])).json()['detail']
        assert 'password-protected' in upload(client, cid, make_pdf(['Secret'], encrypted=True)).json()['detail']
        assert upload(client, cid, b'x' * (MAX_FILE_BYTES + 1)).status_code == 413
        assert client.post(f'/api/conversations/{cid}/documents?filename=test.pdf', content=b'x',
                           headers={'Origin': 'https://evil.example'}).status_code == 403
        app.state.pdf_busy = True
        assert upload(client, cid).status_code == 409
        assert send(client, cid).status_code == 409
        app.state.pdf_busy = False
        assert client.get(f'/api/conversations/{cid}').json()['messages'] == []
        assert client.get('/api/usage?days=0').json()['overview']['requests'] == 0
        assert upload(client, cid, filename='../safe.pdf').json()['filename'] == 'safe.pdf'


def test_long_documents_retrieve_late_pages_and_bound_utf8_context():
    document = dict(id='doc', filename='long.pdf', page_count=100, unreadable_pages=[],
                    pages=[{'number': i, 'text': ('General information ' * 100) +
                            (' The secret launch code is JUNIPER.' if i == 99 else '')} for i in range(1, 101)])
    history = [{'role':'user', 'content':'Earlier question ' * 1000}] * 12
    messages, omitted, coverage = pdf_context(document, history, 'What is the secret launch code?')
    assert 'JUNIPER' in messages[0]['content']
    assert coverage['excerpts'] is True and 99 in coverage['pages_used']
    assert omitted == 12
    assert sum(len(m['content'].encode()) for m in messages) <= MAX_INPUT_BYTES
    messages, _, coverage = pdf_context(document, [], 'Explain page 100')
    assert 100 in coverage['pages_used']
    _, _, overview = pdf_context(document, [], 'Summarize this PDF')
    assert 1 in overview['pages_used'] and 100 in overview['pages_used']
    document['pages'] = [{'number':1, 'text':'🌿' * 20_000}]
    messages, _, _ = pdf_context(document, [], 'What does it say?')
    assert sum(len(m['content'].encode()) for m in messages) <= MAX_INPUT_BYTES
    with pytest.raises(DocumentError, match='4 KB'):
        pdf_context(document, [], 'é' * 3000)


async def test_parser_timeout_and_cancellation_reap_process(monkeypatch):
    class Process:
        returncode = None
        killed = False
        reaped = False

        async def communicate(self, data):
            await asyncio.sleep(60)

        def kill(self):
            self.killed = True
            self.returncode = -9

        async def wait(self):
            self.reaped = True

    processes = []

    async def spawn(*args, **kwargs):
        process = Process()
        processes.append(process)
        return process

    monkeypatch.setattr('app.documents.asyncio.create_subprocess_exec', spawn)
    monkeypatch.setattr('app.documents.PARSE_TIMEOUT', .01)
    with pytest.raises(DocumentError, match='too long'):
        await read_pdf(b'pdf')
    assert processes[-1].killed and processes[-1].reaped
    task = asyncio.create_task(read_pdf(b'pdf'))
    await asyncio.sleep(.001)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert processes[-1].killed and processes[-1].reaped


async def test_upload_disconnect_cancels_reading_and_releases_lock(tmp_path, monkeypatch):
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def reading(data):
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.set()

    monkeypatch.setattr('app.main.read_pdf', reading)
    app = create_app(tmp_path / 'chat.db', FakeOllama())
    sent = []
    body_sent = False

    async def receive():
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {'type':'http.request', 'body':make_pdf(['Hello']), 'more_body':False}
        await started.wait()
        return {'type':'http.disconnect'}

    async def send_message(message):
        sent.append(message)

    async with app.router.lifespan_context(app):
        cid = app.state.storage.create()['id']
        path = f'/api/conversations/{cid}/documents'
        scope = {'type':'http', 'asgi':{'version':'3.0'}, 'http_version':'1.1',
                 'method':'POST', 'scheme':'http', 'path':path, 'raw_path':path.encode(),
                 'query_string':b'filename=test.pdf', 'root_path':'',
                 'headers':[(b'host', b'testserver'), (b'content-type', b'application/pdf')],
                 'client':('127.0.0.1', 1234), 'server':('testserver', 80)}
        await asyncio.wait_for(app(scope, receive, send_message), 2)
        assert cancelled.is_set()
        assert app.state.pdf_busy is False
        with app.state.storage.connect() as db:
            assert db.execute('SELECT count(*) FROM pdf_documents').fetchone()[0] == 0


async def test_adapter_uses_pdf_window_only_for_pdf_requests():
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, text='{"done":true}\n')

    adapter = OllamaAdapter(httpx.MockTransport(handle))
    try:
        for messages in [[{'role':'user','content':'Hello'}], [{'role':'system','content':PDF_CONTEXT_PREFIX}]]:
            _ = [p async for p in adapter.stream('gemma4:e2b', messages)]
    finally:
        await adapter.close()
    assert seen[0]['options']['num_ctx'] == 4096
    assert seen[1]['options']['num_ctx'] == PDF_CONTEXT_WINDOW
