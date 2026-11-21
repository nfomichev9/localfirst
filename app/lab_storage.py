"""Lab artifacts contain user content; they are separate from content-free telemetry."""
import json
from uuid import uuid4


class ChatTurnError(ValueError):
    pass


class LabStorage:
    def __init__(self, storage):
        self.storage = storage
        with storage.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS lab_tasks (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    title TEXT NOT NULL, prompt TEXT NOT NULL, context TEXT NOT NULL,
                    criteria TEXT NOT NULL, check_mode TEXT NOT NULL, reference TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
                CREATE TABLE IF NOT EXISTS lab_operations (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES lab_tasks(id),
                    revision INTEGER NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('prepare','run')),
                    variant TEXT NOT NULL, model TEXT NOT NULL,
                    request_id TEXT NOT NULL UNIQUE REFERENCES inference_attempts(request_id),
                    snapshot TEXT NOT NULL, submitted_prompt TEXT NOT NULL,
                    preparation_id TEXT REFERENCES lab_operations(id),
                    prepared_prompt TEXT NOT NULL, added_context TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('running','success','error','cancelled')),
                    output TEXT NOT NULL DEFAULT '', result TEXT, error TEXT,
                    review TEXT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
                CREATE INDEX IF NOT EXISTS lab_task_operations ON lab_operations(task_id,created_at);
                INSERT OR IGNORE INTO schema_migrations(version) VALUES (3);
            ''')
            versions = {row[0] for row in db.execute('SELECT version FROM schema_migrations')}
            if 4 not in versions:
                db.executescript('''BEGIN IMMEDIATE;
                    ALTER TABLE lab_tasks ADD COLUMN source TEXT;
                    ALTER TABLE lab_operations ADD COLUMN input_messages TEXT;
                    CREATE TABLE lab_chat_baselines (
                        id TEXT PRIMARY KEY, task_id TEXT NOT NULL UNIQUE REFERENCES lab_tasks(id),
                        source_message_id INTEGER NOT NULL UNIQUE REFERENCES messages(id),
                        request_id TEXT REFERENCES inference_attempts(request_id),
                        model TEXT, snapshot TEXT NOT NULL, input_messages TEXT NOT NULL,
                        output TEXT NOT NULL, metrics TEXT, review TEXT,
                        created_at TEXT NOT NULL);
                    INSERT INTO schema_migrations(version) VALUES (4);
                    COMMIT;''')
            db.execute("UPDATE lab_operations SET status='cancelled', error='Application stopped during generation.' WHERE status='running'")

    @staticmethod
    def decode(row):
        if row is None:
            return None
        data = dict(row)
        for key in ('criteria', 'snapshot', 'result', 'review', 'source', 'input_messages', 'metrics'):
            if key in data and data[key] is not None:
                data[key] = json.loads(data[key])
        return data

    def tasks(self):
        with self.storage.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,title,revision,updated_at FROM lab_tasks ORDER BY updated_at DESC,rowid DESC')]

    def get(self, tid):
        with self.storage.connect() as db:
            return self.decode(db.execute('SELECT * FROM lab_tasks WHERE id=?', (tid,)).fetchone())

    def save(self, data, tid=None, revision=None):
        tid = tid or str(uuid4())
        values = (data['title'], data['prompt'], data['context'], json.dumps(data['criteria']), data['check_mode'], data['reference'])
        with self.storage.connect() as db:
            if revision is None:
                db.execute('INSERT INTO lab_tasks(id,revision,title,prompt,context,criteria,check_mode,reference) VALUES (?,1,?,?,?,?,?,?)', (tid, *values))
            else:
                result = db.execute("UPDATE lab_tasks SET title=?,prompt=?,context=?,criteria=?,check_mode=?,reference=?,revision=revision+1,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=? AND revision=?", (*values, tid, revision))
                if not result.rowcount:
                    return None
        return self.get(tid)

    def begin(self, oid, task, kind, variant, model, rid, submitted, preparation_id=None, prepared_prompt='', added_context='', input_messages=None):
        with self.storage.connect() as db:
            db.execute('''INSERT INTO lab_operations
                (id,task_id,revision,kind,variant,model,request_id,snapshot,submitted_prompt,preparation_id,prepared_prompt,added_context,input_messages,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'running')''',
                (oid, task['id'], task['revision'], kind, variant, model, rid, json.dumps(task), submitted, preparation_id, prepared_prompt, added_context, json.dumps(input_messages) if input_messages is not None else None))
        return self.operation(oid)

    def operation(self, oid):
        with self.storage.connect() as db:
            operation = self.decode(db.execute('SELECT * FROM lab_operations WHERE id=?', (oid,)).fetchone())
            if operation:
                row = db.execute('SELECT * FROM inference_attempts WHERE request_id=?', (operation['request_id'],)).fetchone()
                operation['telemetry'] = dict(row) if row else None
                operation['origin'] = 'lab'
                return operation
            baseline = self.decode(db.execute('SELECT * FROM lab_chat_baselines WHERE id=?', (oid,)).fetchone())
            if baseline:
                check = baseline['snapshot']['check_mode']
                reference = baseline['snapshot']['reference']
                result = None if check == 'none' else {'method':check, 'passed':baseline['output'].strip() == reference.strip() if check == 'exact' else reference in baseline['output'], 'scope':'String check only; not a task-success verdict.'}
                row = db.execute('SELECT * FROM inference_attempts WHERE request_id=?', (baseline['request_id'],)).fetchone()
                return {**baseline, 'origin':'chat', 'kind':'run', 'variant':'original', 'status':'success',
                        'revision':baseline['snapshot']['revision'], 'submitted_prompt':json.dumps(baseline['input_messages'], ensure_ascii=False, indent=2),
                        'preparation_id':None, 'prepared_prompt':'', 'added_context':'', 'error':None, 'result':result,
                        'telemetry':dict(row) if row else baseline['metrics']}
            return None

    def operations(self, tid):
        with self.storage.connect() as db:
            ids = [r[0] for r in db.execute('''SELECT id,created_at FROM lab_operations WHERE task_id=?
                UNION ALL SELECT id,created_at FROM lab_chat_baselines WHERE task_id=? ORDER BY created_at DESC,id DESC''', (tid,tid))]
        return [self.operation(oid) for oid in ids]

    def finish(self, oid, status, output, result=None, error=None):
        with self.storage.connect() as db:
            db.execute("UPDATE lab_operations SET status=?,output=?,result=?,error=? WHERE id=? AND status='running'", (status, output, json.dumps(result) if result is not None else None, error, oid))
        return self.operation(oid)

    def review(self, oid, data):
        with self.storage.connect() as db:
            for table in ('lab_operations','lab_chat_baselines'):
                db.execute(f'UPDATE {table} SET review=? WHERE id=?', (json.dumps(data), oid))
        return self.operation(oid)

    def chat_turns(self, limit=50, offset=0):
        with self.storage.connect() as db:
            total = db.execute("SELECT count(*) FROM messages WHERE role='assistant' AND status='complete' AND trim(content)<>''").fetchone()[0]
            rows = db.execute('''SELECT m.id AS message_id,m.conversation_id,m.model,m.created_at,
                c.title,substr(u.content,1,240) AS prompt_preview,b.task_id,
                CASE WHEN i.message_id IS NULL THEN 'reconstructed' ELSE 'recorded' END AS context_source
                FROM messages m JOIN conversations c ON c.id=m.conversation_id
                LEFT JOIN messages u ON u.id=(SELECT max(id) FROM messages WHERE conversation_id=m.conversation_id AND role='user' AND id<m.id)
                LEFT JOIN lab_chat_baselines b ON b.source_message_id=m.id
                LEFT JOIN chat_inputs i ON i.message_id=m.id
                WHERE m.role='assistant' AND m.status='complete' AND trim(m.content)<>''
                ORDER BY m.id DESC LIMIT ? OFFSET ?''', (limit,offset)).fetchall()
            return {'items':[dict(r) for r in rows], 'total':total, 'has_more':offset+len(rows)<total}

    def chat_turn(self, mid):
        with self.storage.connect() as db:
            row = db.execute("SELECT * FROM messages WHERE id=? AND role='assistant' AND status='complete' AND trim(content)<>''", (mid,)).fetchone()
            if row is None:
                return None
            answer = dict(row)
            user = db.execute("SELECT * FROM messages WHERE conversation_id=? AND id<? AND role='user' ORDER BY id DESC LIMIT 1", (answer['conversation_id'],mid)).fetchone()
            if user is None:
                raise ChatTurnError('This reply has no saved user prompt; it cannot be replayed reliably.')
            recorded = db.execute('SELECT * FROM chat_inputs WHERE message_id=?', (mid,)).fetchone()
            if recorded:
                messages = json.loads(recorded['messages'])
                omitted = recorded['omitted_messages']
                context_source = 'recorded'
            else:
                rows = db.execute("SELECT role,content FROM messages WHERE conversation_id=? AND id<? AND status='complete' ORDER BY id", (answer['conversation_id'],user['id'])).fetchall()
                messages = [dict(r) for r in rows[-12:]] + [{'role':'user','content':user['content']}]
                omitted = max(0,len(rows)-12)
                context_source = 'reconstructed'
            history = messages[:-1]
            context = json.dumps(history,ensure_ascii=False,indent=2) if history else ''
            telemetry = db.execute('SELECT * FROM inference_attempts WHERE message_id=?', (mid,)).fetchone()
            metrics = dict(telemetry) if telemetry else dict(model=answer['model'], execution_location='local',
                latency_ms=answer['latency_ms'], input_tokens=answer['prompt_tokens'], output_tokens=answer['output_tokens'],
                tokens_per_second=None, ttft_ms=None, external_api_cost=0)
            conversation = db.execute('SELECT title FROM conversations WHERE id=?', (answer['conversation_id'],)).fetchone()
            existing = db.execute('SELECT task_id FROM lab_chat_baselines WHERE source_message_id=?', (mid,)).fetchone()
            return {'message_id':mid, 'conversation_id':answer['conversation_id'], 'title':conversation['title'],
                    'prompt':messages[-1]['content'], 'context':context, 'output':answer['content'],
                    'model':answer['model'], 'metrics':metrics, 'created_at':answer['created_at'],
                    'input_messages':messages, 'omitted_messages':omitted, 'context_source':context_source,
                    'task_id':existing['task_id'] if existing else None}

    def import_chat_turn(self, mid, criteria, title=None, check_mode='none', reference=''):
        turn = self.chat_turn(mid)
        if turn is None:
            return None
        if turn['task_id']:
            return self.get(turn['task_id'])
        tid = str(uuid4())
        source = {key:turn[key] for key in ('message_id','conversation_id','input_messages','omitted_messages','context_source')}
        source.update(original_prompt=turn['prompt'], original_context=turn['context'], criteria_declared_after_answer=True)
        # Import artifacts atomically. No inference or extra telemetry row is created.
        with self.storage.connect() as db:
            existing = db.execute('SELECT task_id FROM lab_chat_baselines WHERE source_message_id=?', (mid,)).fetchone()
            if existing:
                tid = existing['task_id']
            else:
                db.execute('''INSERT INTO lab_tasks(id,revision,title,prompt,context,criteria,check_mode,reference,source)
                    VALUES (?,1,?,?,?,?,?,?,?)''', (tid,title or turn['title'],turn['prompt'],turn['context'],json.dumps(criteria),check_mode,reference,json.dumps(source)))
                snapshot = self.decode(db.execute('SELECT * FROM lab_tasks WHERE id=?', (tid,)).fetchone())
                db.execute('''INSERT INTO lab_chat_baselines(id,task_id,source_message_id,request_id,model,snapshot,input_messages,output,metrics,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)''', (str(uuid4()),tid,mid,turn['metrics'].get('request_id'),turn['model'],json.dumps(snapshot),json.dumps(turn['input_messages']),turn['output'],json.dumps(turn['metrics']),turn['created_at']))
        return self.get(tid)
