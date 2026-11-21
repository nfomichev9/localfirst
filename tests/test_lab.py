import asyncio
import json
import sqlite3
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.lab_storage import LabStorage
from app.storage import Storage
from app.telemetry import Telemetry
from app.ollama_adapter import OllamaError

PREPARATION = dict(context_sufficient=False, missing_information=['The email body'],
                   clarifying_questions=['What does the email say?'], assumptions=[],
                   prepared_prompt='Draft a reply addressing the supplied email. Do not invent its contents.')
TASK = dict(title='Arithmetic', prompt='What is 17 times 23? Return only the number.', context='',
            criteria=['Correct product', 'Number only'], check_mode='exact', reference='391')


class LabAdapter:
    def __init__(self, mode='ok'):
        self.mode, self.requests, self.closed_stream = mode, [], False

    async def models(self):
        if self.mode == 'offline':
            raise OllamaError('Ollama unavailable.')
        return ['gemma4:e2b', 'llama3.2:3b']

    async def close(self):
        pass

    async def stream(self, model, messages):
        self.requests.append((model, messages))
        preparing = messages[0]['content'].startswith('You are a local request editor')
        text = json.dumps(PREPARATION) if preparing else '391'
        if self.mode == 'invalid':
            text = 'Invalid context-check JSON'
        try:
            yield {'message':{'content':text[:3]}}
            if self.mode == 'slow':
                await asyncio.sleep(60)
            if self.mode == 'error':
                raise OllamaError('Generation interrupted.')
            yield {'message':{'content':text[3:]}, 'done':True, 'model':model,
                   'prompt_eval_count':12, 'eval_count':4, 'eval_duration':100_000_000}
        finally:
            self.closed_stream = True


@contextmanager
def lab_client(tmp_path, mode='ok'):
    fake = LabAdapter(mode)
    with TestClient(create_app(tmp_path / 'lab.db', fake)) as client:
        yield client, fake


def new_task(client, **overrides):
    response = client.post('/api/lab/tasks', json={**TASK, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def run(client, task, **overrides):
    return client.post(f"/api/lab/tasks/{task['id']}/runs", json={'expected_revision':task['revision'], **overrides})


def prepare(client, task, **overrides):
    return client.post(f"/api/lab/tasks/{task['id']}/prepare", json={'expected_revision':task['revision'], **overrides})


def terminal(response):
    assert response.status_code == 200, response.text
    return json.loads(response.text.splitlines()[-1])


def test_lab_run_persistence_reference_check_review_and_no_chat_pollution(tmp_path):
    with lab_client(tmp_path) as (client, fake):
        task = new_task(client)
        assert client.get('/lab').status_code == 200
        result = terminal(run(client, task))
        assert result['type'] == 'done'
        record = result['operation']
        assert record['result']['passed'] is True
        assert record['review'] is None
        assert record['output'] == '391'
        assert record['telemetry']['conversation_id'] is None
        assert record['telemetry']['purpose'] == 'lab_run'
        assert record['telemetry']['task_id'] == task['id']
        assert record['telemetry']['benchmark_run_id'] == record['id']
        assert record['telemetry']['tokens_per_second'] == 40
        assert record['telemetry']['external_api_cost'] == 0
        assert client.get('/api/conversations').json() == []
        assert client.get('/api/usage').json()['overview']['requests'] == 1
        oid = record['id']
        invalid = dict(verdict='pass', criteria=['pass','uncertain'], notes='Not all criteria established.')
        assert client.put(f'/api/lab/operations/{oid}/review', json=invalid).status_code == 422
        assert client.put(f'/api/lab/operations/{oid}/review', json={**invalid, 'criteria':['pass']}).status_code == 422
        assessment = dict(verdict='pass', criteria=['pass','pass'], notes='Verified independently: 17 × 23 = 391; answer contains digits only.')
        reviewed = client.put(f'/api/lab/operations/{oid}/review', json=assessment).json()
        assert reviewed['review']['source'] == 'human'
        assert reviewed['review']['verdict'] == 'pass'
    with lab_client(tmp_path) as (client, fake):
        loaded = client.get(f"/api/lab/tasks/{task['id']}").json()
        assert loaded['operations'][0]['review']['notes'] == assessment['notes']
        assert loaded['operations'][0]['output'] == '391'


def test_preparation_draft_confirmation_added_context_and_reference_non_disclosure(tmp_path):
    with lab_client(tmp_path) as (client, fake):
        task = new_task(client, reference='SECRET_REFERENCE_NOT_FOR_THE_MODEL')
        result = terminal(prepare(client, task))['operation']
        assert result['result'] == PREPARATION
        assert result['telemetry']['purpose'] == 'lab_prepare'
        assert task['reference'] not in fake.requests[-1][1][0]['content']
        assert run(client, task, variant='prepared', prepared_prompt='Edited draft').status_code == 422
        result = terminal(run(client, task, variant='prepared', prepared_prompt='Edited draft',
            preparation_id=result['id'], added_context='User supplied the actual email.', confirmed=True))['operation']
        assert result['added_context'] == 'User supplied the actual email.'
        assert result['prepared_prompt'] == 'Edited draft'
        assert task['reference'] not in result['submitted_prompt']
        assert result['result']['passed'] is False
        assert result['snapshot']['reference'] == task['reference']
        assert run(client, task, added_context='hidden new data').status_code == 422


def test_version_snapshots_stale_requests_and_preparation_provenance(tmp_path):
    with lab_client(tmp_path) as (client, fake):
        task = new_task(client)
        old = terminal(run(client, task))['operation']
        draft = terminal(prepare(client, task))['operation']
        response = client.put(f"/api/lab/tasks/{task['id']}", json={**TASK,'prompt':'New prompt','expected_revision':1})
        updated = response.json()
        assert updated['revision'] == 2
        assert run(client, task).status_code == 409
        assert client.put(f"/api/lab/tasks/{task['id']}", json={**TASK,'expected_revision':1}).status_code == 409
        assert run(client, updated, variant='prepared', preparation_id=draft['id'], prepared_prompt='Old draft', confirmed=True).status_code == 422
        other = new_task(client)
        assert run(client, other, variant='prepared', preparation_id=draft['id'], prepared_prompt='Other task', confirmed=True).status_code == 422
        loaded = client.get(f"/api/lab/tasks/{task['id']}").json()
        trial = next(o for o in loaded['operations'] if o['id'] == old['id'])
        assert trial['snapshot']['prompt'] == TASK['prompt'] and trial['revision'] == 1
        manual = terminal(run(client, updated, variant='prepared', prepared_prompt='Manual draft', confirmed=True))['operation']
        assert manual['preparation_id'] is None


@pytest.mark.parametrize('mode', ['invalid','error','offline'])
def test_operation_failures_persist_and_release_lock(tmp_path, mode):
    with lab_client(tmp_path, mode) as (client, fake):
        task = new_task(client)
        response = prepare(client, task)
        if mode == 'offline':
            assert response.status_code == 503
        else:
            assert terminal(response)['type'] == 'error'
        saved = client.get(f"/api/lab/tasks/{task['id']}").json()['operations'][0]
        assert saved['status'] == 'error' and saved['telemetry']['status'] == 'error'
        if mode == 'invalid':
            assert saved['output'] == 'Invalid context-check JSON' and saved['result'] is None
        fake.mode = 'ok'
        assert terminal(run(client, task))['type'] == 'done'


def test_validation_and_string_checks(tmp_path):
    with lab_client(tmp_path) as (client, fake):
        for patch in ({'title':' '}, {'prompt':' '}, {'criteria':[]}, {'criteria':[' ']}, {'reference':''}, {'criteria':['x'*501]}):
            assert client.post('/api/lab/tasks', json={**TASK, **patch}).status_code == 422
        task = new_task(client, check_mode='contains', reference='91')
        assert terminal(run(client, task))['operation']['result']['passed'] is True
        assert prepare(client, task, model='not-installed').status_code == 400
        assert client.get('/api/lab/tasks/missing').status_code == 404
        assert client.put('/api/lab/operations/missing/review', json={'verdict':'uncertain','criteria':['uncertain'],'notes':'Unknown'}).status_code == 404
        assert client.post('/api/lab/tasks', json=TASK, headers={'Origin':'https://external.example'}).status_code == 403


def test_recovery_marks_inflight_lab_cancelled_without_fabricating_metrics(tmp_path):
    path = tmp_path / 'recovery.db'
    storage = Storage(path)
    lab = LabStorage(storage)
    task = lab.save(TASK)
    telemetry = Telemetry(storage)
    rid = telemetry.start(None, 'test', purpose='lab_run', task_id=task['id'], run_id='op')
    lab.begin('op', task, 'run', 'original', 'test', rid, 'stored input')
    restarted = LabStorage(Storage(path))
    record = restarted.operation('op')
    assert record['status'] == 'cancelled' and record['telemetry']['status'] == 'cancelled'
    assert record['telemetry']['latency_ms'] is None
    assert restarted.tasks()[0]['id'] == task['id']
    with storage.connect() as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


async def test_lab_disconnect_and_shared_chat_generation_lock(tmp_path):
    fake = LabAdapter('slow')
    app = create_app(tmp_path / 'test.db', fake)
    async with app.router.lifespan_context(app):
        task = app.state.lab.save(TASK)
        cid = app.state.storage.create()['id']
        got_delta = asyncio.Event()
        read = False
        async def receive():
            nonlocal read
            if not read:
                read = True
                return {'type':'http.request','body':json.dumps({'expected_revision':1}).encode(),'more_body':False}
            await got_delta.wait()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
                assert (await client.post(f'/api/conversations/{cid}/chat', json={'content':'concurrent'})).status_code == 409
                assert (await client.post(f"/api/lab/tasks/{task['id']}/prepare", json={'expected_revision':1})).status_code == 409
            return {'type':'http.disconnect'}
        async def send(event):
            if event['type'] == 'http.response.body' and b'"delta"' in event.get('body',b''):
                got_delta.set()
        route = f"/api/lab/tasks/{task['id']}/runs"
        scope = {'type':'http','asgi':{'version':'3.0','spec_version':'2.0'},'http_version':'1.1',
                 'method':'POST','scheme':'http','path':route,'raw_path':route.encode(),'query_string':b'',
                 'headers':[(b'host',b'testserver'),(b'content-type',b'application/json')],
                 'client':('127.0.0.1',12345),'server':('testserver',80)}
        await asyncio.wait_for(app(scope, receive, send), timeout=5)
        assert app.state.busy is False and fake.closed_stream
        record = app.state.lab.operations(task['id'])[0]
        assert record['status'] == record['telemetry']['status'] == 'cancelled'
        assert record['output'] == '391'[:3]


def test_lab_timeout_closes_stream(tmp_path, monkeypatch):
    monkeypatch.setattr('app.lab.TIMEOUT_SECONDS', .01)
    with lab_client(tmp_path, 'slow') as (client, fake):
        task = new_task(client)
        result = terminal(run(client, task))
        assert result['type'] == 'error' and fake.closed_stream
        assert result['operation']['status'] == 'error'


def legacy_database(path):
    from pathlib import Path
    with sqlite3.connect(path) as db:
        db.executescript((Path(__file__).parent / 'fixtures/schema_v1.sql').read_text())
        db.execute("INSERT INTO conversations(id,title) VALUES ('existing','Existing conversation')")
        db.execute("INSERT INTO messages(id,conversation_id,role,content,model,status) VALUES (1,'existing','assistant','# Raw Markdown','old-model','complete')")
        db.execute('''INSERT INTO inference_attempts
            (request_id,conversation_id,message_id,provider,model,execution_location,input_tokens,output_tokens,
             latency_ms,ttft_ms,generation_duration_ms,tokens_per_second,external_api_cost,status,feedback)
            VALUES ('existing-request','existing',1,'ollama','old-model','local',10,3,400,20,100,30,0,'success',1)''')
        db.row_factory = sqlite3.Row
        return dict(db.execute('SELECT * FROM inference_attempts').fetchone())


def test_v1_ledger_migration_retains_every_field_and_message_link(tmp_path):
    path = tmp_path / 'legacy.db'
    before = legacy_database(path)
    for _ in range(2):
        storage = Storage(path)
        LabStorage(storage)
        with storage.connect() as db:
            after = dict(db.execute('SELECT * FROM inference_attempts').fetchone())
            assert after.pop('purpose') == 'chat'
            assert after == before
            assert [r[0] for r in db.execute('SELECT version FROM schema_migrations ORDER BY version')] == [1,2,3,4]
            assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        message = storage.conversation('existing')['messages'][0]
        assert message['content'] == '# Raw Markdown'
        assert message['telemetry']['feedback'] == 1


def test_telemetry_migration_rolls_back_if_version_record_fails(tmp_path):
    path = tmp_path / 'rollback.db'
    before = legacy_database(path)
    with sqlite3.connect(path) as db:
        db.executescript("""CREATE TRIGGER reject_v2 BEFORE INSERT ON schema_migrations
            WHEN NEW.version=2 BEGIN SELECT RAISE(ABORT,'migration blocked'); END;""")
    with pytest.raises(sqlite3.IntegrityError, match='migration blocked'):
        Storage(path)
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        assert dict(db.execute('SELECT * FROM inference_attempts').fetchone()) == before
        assert db.execute("SELECT name FROM sqlite_master WHERE name='inference_attempts_v2'").fetchone() is None
        assert db.execute('SELECT count(*) FROM schema_migrations WHERE version=2').fetchone()[0] == 0
        db.execute('DROP TRIGGER reject_v2')
    assert Telemetry(Storage(path)).get('existing-request')['purpose'] == 'chat'


def test_prompt_whitespace_preserved_and_prepared_confirmation_is_strict(tmp_path):
    with lab_client(tmp_path) as (client, fake):
        prompt, context = '  Explain this indented code.\n', '  if value:\n      return value\n'
        task = new_task(client, prompt=prompt, context=context)
        assert task['prompt'] == prompt and task['context'] == context
        record = terminal(run(client, task))['operation']
        assert prompt in record['input_messages'][0]['content'] and context in record['input_messages'][0]['content']
        assert run(client, task, variant='prepared', prepared_prompt='   ', confirmed=True).status_code == 422
        assert run(client, task, variant='prepared', prepared_prompt='Draft', confirmed=1).status_code == 422


def test_chat_inbox_import_reuses_saved_answer_and_replays_exact_roles(tmp_path):
    with lab_client(tmp_path) as (client, fake):
        cid = client.post('/api/conversations').json()['id']
        route = f'/api/conversations/{cid}/chat'
        client.post(route,json={'content':'Remember the code word juniper.'})
        client.post(route,json={'content':'What word did I give you?'})
        message = client.get(f'/api/conversations/{cid}').json()['messages'][-1]
        original_messages = fake.requests[-1][1]
        # Later messages must not leak into the original request or become its prompt.
        client.post(route,json={'content':'A future message not available to the earlier answer.'})
        preview = client.get(f"/api/lab/chat-turns/{message['id']}").json()
        assert preview['input_messages'] == original_messages
        assert preview['prompt'] == 'What word did I give you?'
        assert preview['context_source'] == 'recorded'
        assert preview['output'] == message['content']
        before_requests = client.get('/api/usage').json()['overview']['requests']
        before_calls = len(fake.requests)
        criteria = ['CRITERION_WITHHELD_FROM_CHAT_REPLAY','Use the prior context']
        imported = client.post(f"/api/lab/chat-turns/{message['id']}/import",json={'criteria':criteria}).json()
        assert len(fake.requests) == before_calls
        assert client.get('/api/usage').json()['overview']['requests'] == before_requests
        records = client.get(f"/api/lab/tasks/{imported['id']}").json()['operations']
        assert len(records) == 1
        baseline = records[0]
        assert baseline['origin'] == 'chat' and baseline['output'] == message['content']
        assert baseline['request_id'] == message['telemetry']['request_id']
        assert baseline['telemetry']['purpose'] == 'chat'
        assert baseline['snapshot']['source']['criteria_declared_after_answer'] is True
        again = client.post(f"/api/lab/chat-turns/{message['id']}/import",json={'criteria':['Different suggestion']}).json()
        assert again['id'] == imported['id'] and again['criteria'] == criteria
        answer = terminal(run(client,imported,model='llama3.2:3b'))['operation']
        assert fake.requests[-1] == ('llama3.2:3b',original_messages)
        assert answer['input_messages'] == original_messages
        assert criteria[0] not in str(fake.requests[-1])
        draft = terminal(run(client,imported,variant='prepared',prepared_prompt='Recall my code word.',added_context='Only repeat the word.',confirmed=True))['operation']
        assert fake.requests[-1][1][:-1] == original_messages[:-1]
        assert fake.requests[-1][1][-1]['content'] == 'Recall my code word.\n\nAdditional context supplied by the user:\nOnly repeat the word.'
        assert draft['added_context'] == 'Only repeat the word.'
        review_data = {'verdict':'pass','criteria':['pass','pass'],'notes':'Reviewed the saved answer against the declared criteria.'}
        response = client.put(f"/api/lab/operations/{baseline['id']}/review",json=review_data)
        assert response.status_code == 200 and response.json()['review']['source'] == 'human'
        inbox = client.get('/api/lab/chat-turns?limit=1').json()
        assert inbox['total'] == 3 and inbox['has_more'] is True
        assert len(client.get('/api/lab/chat-turns?offset=1').json()['items']) == 2
        assert client.get('/api/lab/chat-turns?offset=-1').status_code == 422


def test_legacy_chat_context_is_bounded_reconstructed_and_metrics_not_invented(tmp_path):
    path = tmp_path / 'lab.db'
    with lab_client(tmp_path) as (client,fake):
        store = Storage(path)
        cid = store.create()['id']
        for i in range(15):
            store.add(cid,'user' if i % 2 == 0 else 'assistant',f'prior-{i}')
        store.add(cid,'assistant','FAILED_OUTPUT_MUST_NOT_BE_CONTEXT',status='error')
        store.add(cid,'user','The actual prompt')
        mid = store.add(cid,'assistant','The original historical answer','legacy-model')
        store.finish(mid,'The original historical answer','complete','legacy-model',123,prompt_tokens=10,output_tokens=4)
        store.add(cid,'user','FUTURE_MESSAGE')
        turn = client.get(f'/api/lab/chat-turns/{mid}').json()
        assert turn['context_source'] == 'reconstructed' and turn['omitted_messages'] == 3
        assert len(turn['input_messages']) == 13
        assert turn['input_messages'][0]['content'] == 'prior-3'
        assert 'FAILED_OUTPUT' not in str(turn['input_messages']) and 'FUTURE_MESSAGE' not in str(turn['input_messages'])
        imported = client.post(f'/api/lab/chat-turns/{mid}/import',json={'criteria':['Useful answer']}).json()
        baseline = client.get(f"/api/lab/tasks/{imported['id']}").json()['operations'][0]
        assert baseline['request_id'] is None
        assert baseline['telemetry']['ttft_ms'] is None and baseline['telemetry']['tokens_per_second'] is None
        assert baseline['telemetry']['latency_ms'] == 123
        assert client.get('/api/usage').json()['overview']['requests'] == 0
        assert client.get('/api/lab/chat-turns/99999').status_code == 404
        assert client.post('/api/lab/chat-turns/99999/import',json={'criteria':['Useful']}).status_code == 404


def test_chat_import_and_recorded_inputs_survive_restart(tmp_path):
    with lab_client(tmp_path) as (client,fake):
        cid = client.post('/api/conversations').json()['id']
        client.post(f'/api/conversations/{cid}/chat',json={'content':'A real chat turn'})
        mid = client.get(f'/api/conversations/{cid}').json()['messages'][-1]['id']
        imported = client.post(f'/api/lab/chat-turns/{mid}/import',json={'criteria':['Addresses the request']}).json()
    with lab_client(tmp_path) as (client,fake):
        turn = client.get(f'/api/lab/chat-turns/{mid}').json()
        assert turn['context_source'] == 'recorded' and turn['task_id'] == imported['id']
        task = client.get(f"/api/lab/tasks/{imported['id']}").json()
        assert task['operations'][0]['origin'] == 'chat'
        assert task['operations'][0]['input_messages'] == turn['input_messages']


def test_migration_four_preserves_prior_lab_tasks_preparations_and_reviews(tmp_path):
    path = tmp_path / 'old-lab.db'
    store = Storage(path)
    lab = LabStorage(store)
    task = lab.save(TASK)
    ledger = Telemetry(store)
    rid = ledger.start(None,'model',purpose='lab_prepare')
    lab.begin('prep',task,'prepare','context_check','model',rid,'prep prompt')
    ledger.finish(rid,'success',10)
    lab.finish('prep','success','draft',PREPARATION)
    rid = ledger.start(None,'model',purpose='lab_run')
    lab.begin('trial',task,'run','prepared','model',rid,'run prompt',preparation_id='prep')
    ledger.finish(rid,'success',20)
    lab.finish('trial','success','391')
    lab.review('trial',{'verdict':'pass','notes':'Existing review'})
    with store.connect() as db:
        db.execute('DROP TABLE lab_chat_baselines')
        db.execute('ALTER TABLE lab_tasks DROP COLUMN source')
        db.execute('ALTER TABLE lab_operations DROP COLUMN input_messages')
        db.execute('DELETE FROM schema_migrations WHERE version=4')
    migrated = LabStorage(Storage(path))
    assert migrated.operation('trial')['review']['notes'] == 'Existing review'
    assert migrated.operation('trial')['preparation_id'] == 'prep'
    assert migrated.operation('prep')['result'] == PREPARATION
    with store.connect() as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def test_chat_criteria_do_not_leak_into_replays_and_source_edits_are_custom(tmp_path):
    with lab_client(tmp_path) as (client,fake):
        cid = client.post('/api/conversations').json()['id']
        client.post(f'/api/conversations/{cid}/chat',json={'content':'Give me a short answer.'})
        mid = client.get(f'/api/conversations/{cid}').json()['messages'][-1]['id']
        task = client.post(f'/api/lab/chat-turns/{mid}/import',json={'criteria':['POSTHOC_CRITERION'],'check_mode':'exact','reference':'391'}).json()
        baseline = client.get(f"/api/lab/tasks/{task['id']}").json()['operations'][0]
        assert baseline['result']['passed'] is True
        terminal(prepare(client,task))
        # The reference and the saved answer are not included in the context-check request.
        assert '391' not in fake.requests[-1][1][0]['content']
        assert 'POSTHOC_CRITERION' in fake.requests[-1][1][0]['content']
        terminal(run(client,task))
        assert 'POSTHOC_CRITERION' not in str(fake.requests[-1][1])
        updated = client.put(f"/api/lab/tasks/{task['id']}",json={
            'title':task['title'],'prompt':task['prompt'],'context':'Explicitly edited context.',
            'criteria':task['criteria'],'check_mode':'none','reference':'','expected_revision':1}).json()
        result = terminal(run(client,updated))['operation']
        assert result['input_messages'][0]['content'].startswith('Task:\n')
        assert 'Explicitly edited context.' in result['input_messages'][0]['content']
        assert baseline['snapshot']['context'] == ''


def test_migration_four_rolls_back_on_failure(tmp_path):
    path = tmp_path / 'rollback-four.db'
    store = Storage(path)
    lab = LabStorage(store)
    task = lab.save(TASK)
    with store.connect() as db:
        db.execute('DROP TABLE lab_chat_baselines')
        db.execute('ALTER TABLE lab_tasks DROP COLUMN source')
        db.execute('ALTER TABLE lab_operations DROP COLUMN input_messages')
        db.execute('DELETE FROM schema_migrations WHERE version=4')
        db.executescript("""CREATE TRIGGER reject_v4 BEFORE INSERT ON schema_migrations
            WHEN NEW.version=4 BEGIN SELECT RAISE(ABORT,'migration four blocked'); END;""")
    with pytest.raises(sqlite3.IntegrityError,match='migration four blocked'):
        LabStorage(store)
    with store.connect() as db:
        assert 'source' not in {r['name'] for r in db.execute('PRAGMA table_info(lab_tasks)')}
        assert db.execute("SELECT name FROM sqlite_master WHERE name='lab_chat_baselines'").fetchone() is None
        assert db.execute('SELECT prompt FROM lab_tasks WHERE id=?',(task['id'],)).fetchone()[0] == TASK['prompt']
        db.execute('DROP TRIGGER reject_v4')
    assert LabStorage(store).get(task['id'])['prompt'] == TASK['prompt']
