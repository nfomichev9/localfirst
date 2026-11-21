import sqlite3

import pytest

from app.storage import Storage
from app.telemetry import Telemetry
from app.ollama_adapter import count_metric, duration_metric
from test_api import client_for, create, send, packets


def test_safe_migration_retains_raw_history(tmp_path):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE conversations(id TEXT PRIMARY KEY,title TEXT,created_at TEXT,updated_at TEXT);
            CREATE TABLE messages(id INTEGER PRIMARY KEY,conversation_id TEXT,role TEXT,content TEXT,model TEXT,status TEXT,latency_ms REAL,prompt_tokens INTEGER,output_tokens INTEGER,error TEXT,created_at TEXT);
            INSERT INTO conversations VALUES ('old','History',NULL,NULL);
            INSERT INTO messages(id,conversation_id,role,content,status) VALUES (1,'old','assistant','# **Raw** `markdown`','complete');''')
    for _ in range(2):
        store = Storage(path)
        message = store.conversation('old')['messages'][0]
        assert message['content'] == '# **Raw** `markdown`'
        assert message['telemetry'] is None
        with store.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0] == 2


def test_persistence_nulls_recovery_and_no_content(tmp_path):
    path = tmp_path / 'test.db'
    store = Storage(path)
    ledger = Telemetry(store)
    cid = store.create()['id']
    rid = ledger.start(cid, 'test')
    mid = store.add(cid, 'assistant', 'sensitive response', status='streaming')
    ledger.attach(rid, mid)
    done = ledger.finish(rid, 'success', 250, ttft_ms=20, input_tokens=10, output_tokens=5, generation_duration_ms=100)
    assert done['tokens_per_second'] == 50
    assert done['external_api_cost'] == 0
    ledger.finish(rid, 'error', 999)  # finalization is idempotent
    assert ledger.get(rid)['status'] == 'success'
    running = ledger.start(cid, 'test')
    restarted = Telemetry(Storage(path))
    assert restarted.get(running)['status'] == 'cancelled'
    assert restarted.get(running)['latency_ms'] is None
    assert restarted.get(running)['output_tokens'] is None
    assert 'sensitive' not in str(restarted.get(rid))
    assert restarted.get(rid)['message_id'] == mid


def test_aggregations_filters_percentiles_and_unknowns(tmp_path):
    store = Storage(tmp_path / 'test.db')
    ledger = Telemetry(store)
    cid = store.create()['id']
    assert ledger.analytics()['overview']['requests'] == 0
    assert ledger.analytics()['overview']['local_percentage'] is None
    for n in range(1, 21):
        rid = ledger.start(cid, 'a')
        ledger.finish(rid, 'success', n*100, input_tokens=2, output_tokens=3, generation_duration_ms=300)
    rid = ledger.start(cid, 'b')
    ledger.finish(rid, 'error', 100)
    rid = ledger.start(cid, 'b')
    ledger.finish(rid, 'cancelled', 200)
    summary = ledger.analytics()['overview']
    assert summary['requests'] == 22
    assert summary['successful_requests'] == 20
    assert summary['input_tokens'] == 40 and summary['output_tokens'] == 60
    assert summary['failure_rate'] == pytest.approx(100/22)
    assert summary['cancellation_rate'] == pytest.approx(100/22)
    assert summary['local_percentage'] == 100 and summary['cloud_percentage'] == 0
    assert summary['external_api_cost'] == 0
    assert summary['estimated_api_savings'] is None
    filtered = ledger.analytics(model='a')['overview']
    assert filtered['average_latency_ms'] == 1050
    assert filtered['median_latency_ms'] == 1050
    assert filtered['p95_latency_ms'] == 1900
    assert filtered['average_tokens_per_second'] == 10
    assert ledger.analytics(model='b')['overview']['p95_latency_ms'] is None
    assert ledger.analytics(model='b')['overview']['input_tokens'] is None
    with store.connect() as db:
        db.execute("UPDATE inference_attempts SET timestamp='2000-01-01T00:00:00.000Z'")
    assert ledger.analytics(days=1)['overview']['requests'] == 0
    assert ledger.analytics(days=0)['overview']['requests'] == 22


@pytest.mark.parametrize('value', [-1, True, '4', None, 1.2])
def test_invalid_token_counts(value):
    assert count_metric(value) is None


@pytest.mark.parametrize('value', [-1, True, '4', None, float('nan'), float('inf')])
def test_invalid_durations(value):
    assert duration_metric(value) is None


def test_usage_api_and_response_feedback(tmp_path):
    with client_for(tmp_path) as (client, fake):
        cid = create(client)
        result = packets(send(client, cid))
        record = result[-1]['telemetry']
        assert record['input_tokens'] == 9 and record['output_tokens'] == 2
        assert record['tokens_per_second'] is None  # fake supplied no eval_duration
        assert 0 <= record['ttft_ms'] <= record['latency_ms']
        rid = record['request_id']
        assert client.put(f'/api/inference/{rid}/feedback', json={'value':1}).status_code == 200
        saved = client.get(f'/api/conversations/{cid}').json()['messages'][-1]['telemetry']
        assert saved['feedback'] == 1
        assert client.put(f'/api/inference/{rid}/feedback', json={'value':None}).status_code == 200
        assert client.put(f'/api/inference/{rid}/feedback', json={'value':0}).status_code == 422
        assert client.put('/api/inference/missing/feedback', json={'value':1}).status_code == 404
        assert client.get('/api/usage?days=-1').status_code == 422
        assert client.get('/api/usage?days=0&model=missing').json()['overview']['requests'] == 0
        assert client.get('/usage').status_code == 200
        data = client.get('/api/usage').json()
        assert data['overview']['requests'] == 1
        assert client.get('/api/usage?model=').json()['overview']['requests'] == 1
        assert data['trends'][0]['local_requests'] == 1
        assert data['by_model'][0]['model'] == 'llama3.2:3b'
        assert 'hello' not in str(data)


@pytest.mark.parametrize('mode,status', [('error','error'), ('empty','error'), ('offline','error')])
def test_failed_attempts_are_recorded(tmp_path, mode, status):
    with client_for(tmp_path, mode) as (client, fake):
        send(client, create(client))
        data = client.get('/api/usage').json()['overview']
        assert data['requests'] == 1 and data['failure_rate'] == 100
        assert data['local_percentage'] is None
        assert data['input_tokens'] is None


def test_future_provider_uses_generic_cost_and_unknowns(tmp_path):
    """Synthetic ledger fixture only; no cloud adapter or network call."""
    store = Storage(tmp_path / 'test.db')
    ledger = Telemetry(store)
    cid = store.create()['id']
    rid = ledger.start(cid, 'future-test-model', provider='test-provider', location='cloud')
    assert ledger.get(rid)['external_api_cost'] is None
    result = ledger.finish(rid, 'success', 250, external_api_cost=.0123)
    assert result['external_api_cost'] == .0123
    assert result['input_tokens'] is None and result['ttft_ms'] is None
    assert ledger.analytics()['overview']['cloud_percentage'] == 100


def test_daily_trends_preserve_gaps_without_filling_unknown_counts(tmp_path):
    store = Storage(tmp_path / 'test.db')
    ledger = Telemetry(store)
    cid = store.create()['id']
    for day in ('2026-01-01', '2026-01-03'):
        rid = ledger.start(cid, 'test')
        ledger.finish(rid, 'error', 10)
        with store.connect() as db:
            db.execute('UPDATE inference_attempts SET timestamp=? WHERE request_id=?', (day+'T00:00:00.000Z', rid))
    trends = ledger.analytics(days=0)['trends']
    assert len(trends) == 3
    assert trends[1]['requests'] == 0 and trends[1]['input_tokens'] == 0
    assert trends[0]['input_tokens'] is None
