from app.storage import Storage


def test_restart_order_and_context(tmp_path):
    path = tmp_path / 'chat.sqlite3'
    store = Storage(path)
    cid = store.create()['id']
    for i in range(15):
        store.add(cid, 'user' if i % 2 == 0 else 'assistant', str(i))
    mid = store.add(cid, 'assistant', 'partial', status='streaming')
    restarted = Storage(path)
    messages = restarted.conversation(cid)['messages']
    assert [m['content'] for m in messages[:15]] == [str(i) for i in range(15)]
    assert messages[-1]['id'] == mid
    assert messages[-1]['status'] == 'stopped'
    context, omitted = restarted.context(cid)
    assert len(context) == 12 and omitted == 3
    assert context[0]['content'] == '3'
    assert restarted.list()[0]['title'] == '0'


def test_failed_output_excluded_and_metrics_preserved(tmp_path):
    store = Storage(tmp_path / 'chat.sqlite3')
    cid = store.create()['id']
    store.add(cid, 'user', 'hello')
    mid = store.add(cid, 'assistant', '', 'llama3.2:3b', 'streaming')
    store.finish(mid, 'partial', 'error', 'llama3.2:3b', 123, error='offline')
    assert store.context(cid) == ([{'role':'user', 'content':'hello'}], 0)
    saved = store.conversation(cid)['messages'][-1]
    assert saved['error'] == 'offline' and saved['latency_ms'] == 123
    assert store.conversation('missing') is None
