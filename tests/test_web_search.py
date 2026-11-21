import asyncio
from copy import deepcopy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.ollama_adapter import OllamaAdapter
from app.web_search import (MAX_INPUT_BYTES, MAX_RESPONSE_BYTES, WEB_CONTEXT_PREFIX,
                            WEB_CONTEXT_WINDOW, WebSearchError, parse_results,
                            search_query, search_web, source_url, web_context)
from pdf_fixtures import make_pdf
from test_api import FakeOllama, create, packets, send


RESULTS = '''<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnews">Official <b>release</b> news</a>
<a class="result__snippet">Published today: the launch is <b>December 12</b>.</a></div>'''
SNAPSHOT = {'query':'What is the latest release news?', 'provider':'DuckDuckGo',
            'retrieved_at':'2026-11-20T12:00:00+00:00', 'sources':parse_results(RESULTS)}


def test_result_parser_keeps_excerpts_deduplicates_and_unwraps_links():
    results = parse_results(RESULTS * 3)
    assert results == [{'number':1, 'title':'Official release news', 'url':'https://example.com/news',
                        'excerpt':'Published today: the launch is December 12.'}]
    with pytest.raises(WebSearchError, match='no usable results'):
        parse_results('<html>Search challenge or no matches</html>')
    html = ''.join(RESULTS.replace('example.com', f'example{i}.com') for i in range(8))
    assert len(parse_results(html)) == 4


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'file:///etc/passwd', 'http://localhost/x',
                                 'http://127.0.0.1/x', 'http://169.254.169.254/x', 'http://192.168.1.2/',
                                 'https://user:password@example.com/', 'https://example.com/\nheader',
                                 'http://[::1]/', 'http://machine.local/', 'http://localhost./', None, '',
                                 'https://example.com/' + 'x'*2050])
def test_result_urls_reject_non_public_or_unsafe_targets(url):
    assert source_url(url) is None


async def test_search_uses_only_fixed_provider_and_current_query():
    requests = []

    def handle(request):
        requests.append(request)
        assert request.url.host == 'html.duckduckgo.com'
        assert request.url.params['q'] == 'latest release'
        assert 'authorization' not in request.headers
        return httpx.Response(200, text=RESULTS)

    result = await search_web('latest release', transport=httpx.MockTransport(handle))
    assert result['sources'] == SNAPSHOT['sources']
    assert result['retrieved_at'] and len(requests) == 1


async def test_search_falls_back_to_lite_when_html_is_unavailable():
    hosts = []

    def handle(request):
        hosts.append(request.url.host)
        if len(hosts) == 1:
            return httpx.Response(202,text='Search unavailable')
        return httpx.Response(200,text=RESULTS.replace('result__a','result-link').replace('result__snippet','result-snippet'))

    result = await search_web('news',transport=httpx.MockTransport(handle))
    assert hosts == ['html.duckduckgo.com','lite.duckduckgo.com']
    assert result['sources'] == SNAPSHOT['sources']


@pytest.mark.parametrize('status,body', [(202,RESULTS), (429,RESULTS), (200,'<html>No results</html>'),
                                      (200,'x'*(MAX_RESPONSE_BYTES+1))])
async def test_search_failure_is_explicit(status, body):
    with pytest.raises(WebSearchError):
        await search_web('news', transport=httpx.MockTransport(lambda request: httpx.Response(status,text=body)))


async def test_search_timeout_and_cancellation_close_http_stream(monkeypatch):
    started, closed = asyncio.Event(), asyncio.Event()

    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            started.set()
            await asyncio.sleep(60)
            yield b''

        async def aclose(self):
            closed.set()

    transport = httpx.MockTransport(lambda request: httpx.Response(200,stream=Slow()))
    task = asyncio.create_task(search_web('news', transport=transport))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
    closed.clear()
    monkeypatch.setattr('app.web_search.SEARCH_TIMEOUT', .01)
    with pytest.raises(WebSearchError, match='Could not reach'):
        await search_web('news', transport=transport)
    assert closed.is_set()


def test_grounding_bounds_history_and_preserves_original_request():
    messages = [{'role':'user','content':'é'*3000}] * 12 + [{'role':'user','content':'What is new?'}]
    grounded, omitted = web_context(messages, SNAPSHOT)
    assert grounded[0]['content'].startswith(WEB_CONTEXT_PREFIX)
    assert 'untrusted data' in grounded[0]['content']
    assert 'December 12' in grounded[0]['content'] and 'not a publication date' in grounded[0]['content']
    assert grounded[-1] == messages[-1] and omitted > 0
    assert sum(len(m['content'].encode()) for m in grounded) <= MAX_INPUT_BYTES
    with pytest.raises(WebSearchError):
        search_query('x'*601)


@pytest.mark.parametrize('mode', ['always_local','manual_handoff','automatic_handoff','always_frontier'])
def test_web_answer_stays_local_and_sources_survive_restart_and_retry(tmp_path, monkeypatch, mode):
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-only')
    monkeypatch.setenv('OPENAI_MODEL', 'gpt-6-luna')
    searches = []

    async def search(query):
        searches.append(query)
        return deepcopy(SNAPSHOT)

    async def forbidden(*args, **kwargs):
        pytest.fail('Web answers reached a frontier/preparation adapter')
        yield

    monkeypatch.setattr('app.main.stream_openai', forbidden)
    monkeypatch.setattr('app.main.prepare', forbidden)
    path, local = tmp_path / 'chat.db', FakeOllama('error')
    app = create_app(path, local, web_searcher=search)
    with TestClient(app) as client:
        assert client.put('/api/settings',json={'mode':mode,'daily_limit_cents':1,'acknowledged':True}).is_success
        cid = create(client)
        result = packets(send(client,cid,content=SNAPSHOT['query'],web_search=True))
        assert result[0]['routing_mode'] == 'always_local'
        assert result[1]['type'] == 'web_status' and result[2]['type'] == 'web_sources'
        assert result[-1]['type'] == 'error'
        mid = result[0]['message_id']
        original = deepcopy(local.requests[-1][1])
        assert original[0]['content'].startswith(WEB_CONTEXT_PREFIX)
        assert original[-1]['content'] == SNAPSHOT['query']
        assert searches == [SNAPSHOT['query']]
        assert client.get('/api/settings').json()['mode'] == mode
    local = FakeOllama()
    with TestClient(create_app(path,local,web_searcher=search)) as client:
        result = packets(client.post(f'/api/conversations/{cid}/messages/{mid}/retry',json={'model':'other:small'}))
        assert result[-1]['type'] == 'done'
        assert searches == [SNAPSHOT['query']], 'retry uses the same source snapshot'
        assert local.requests[-1][1] == original
        saved = client.get(f'/api/conversations/{cid}').json()['messages']
        assert [m['role'] for m in saved] == ['user','assistant','assistant']
        assert saved[-1]['web_context'] == SNAPSHOT
        assert saved[-1]['telemetry']['execution_location'] == 'local'
        assert client.post(f'/api/conversations/{cid}/messages/{saved[-1]["id"]}/handoff/preview').status_code == 409


def test_web_errors_retry_and_ordinary_pdf_turns_never_search(tmp_path):
    attempts = []

    async def search(query):
        attempts.append(query)
        if len(attempts) == 1:
            raise WebSearchError('Synthetic search unavailable.')
        return deepcopy(SNAPSHOT)

    local = FakeOllama()
    with TestClient(create_app(tmp_path/'chat.db',local,web_searcher=search)) as client:
        cid = create(client)
        assert packets(send(client,cid))[-1]['type'] == 'done'
        assert attempts == []
        assert send(client,cid,content='x'*601,web_search=True).status_code == 422
        assert send(client,cid,web_search='true').status_code == 422
        result = packets(send(client,cid,content=SNAPSHOT['query'],web_search=True))
        assert result[-1] == {'type':'error','message':'Synthetic search unavailable.'}
        assert len(local.requests) == 1, 'failed search never generates an ungrounded answer'
        mid = result[0]['message_id']
        result = packets(client.post(f'/api/conversations/{cid}/messages/{mid}/retry',json={'model':'llama3.2:3b'}))
        assert result[-1]['type'] == 'done' and len(attempts) == 2
        cid = create(client)
        doc = client.post(f'/api/conversations/{cid}/documents?filename=brief.pdf',content=make_pdf(['Local secret']),
                          headers={'Content-Type':'application/pdf'}).json()
        assert send(client,cid,document_id=doc['id'],web_search=True).status_code == 409
        assert packets(send(client,cid,document_id=doc['id']))[-1]['type'] == 'done'
        assert send(client,cid,web_search=True).status_code == 409
        assert len(attempts) == 2


async def test_ollama_web_context_gets_larger_window_without_changing_normal_chat():
    payloads = []

    def handle(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200,text='{"done":true}\n')

    adapter = OllamaAdapter(transport=httpx.MockTransport(handle))
    try:
        async for _ in adapter.stream('gemma4:e2b',web_context([{'role':'user','content':'News?'}],SNAPSHOT)[0]):
            pass
        async for _ in adapter.stream('gemma4:e2b',[{'role':'user','content':'Hello'}]):
            pass
    finally:
        await adapter.close()
    assert [p['options']['num_ctx'] for p in payloads] == [WEB_CONTEXT_WINDOW,4096]
    assert all(p['think'] is False for p in payloads)
