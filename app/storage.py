"""SQLite persistence. Each operation owns its connection; no chat text is logged."""
import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from .telemetry import initialize
from .documents import metadata as document_metadata


class Storage:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    role TEXT NOT NULL, content TEXT NOT NULL, model TEXT,
                    status TEXT NOT NULL, latency_ms REAL, prompt_tokens INTEGER,
                    output_tokens INTEGER, error TEXT,
                    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
            ''')
            db.execute('''CREATE TABLE IF NOT EXISTS pdf_documents (
                id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
                filename TEXT NOT NULL, page_count INTEGER NOT NULL, pages TEXT NOT NULL,
                unreadable_pages TEXT NOT NULL)''')
            if 'document_id' not in {column['name'] for column in db.execute('PRAGMA table_info(messages)')}:
                db.execute('ALTER TABLE messages ADD COLUMN document_id TEXT REFERENCES pdf_documents(id)')
            db.execute('''CREATE TABLE IF NOT EXISTS chat_inputs (
                message_id INTEGER PRIMARY KEY REFERENCES messages(id),
                model TEXT NOT NULL, messages TEXT NOT NULL, omitted_messages INTEGER NOT NULL,
                retry_of INTEGER REFERENCES messages(id))''')
            if 'retry_of' not in {column['name'] for column in db.execute('PRAGMA table_info(chat_inputs)')}:
                db.execute('ALTER TABLE chat_inputs ADD COLUMN retry_of INTEGER REFERENCES messages(id)')
            columns = {column['name'] for column in db.execute('PRAGMA table_info(chat_inputs)')}
            for column, definition in (
                ('routing_mode', "TEXT NOT NULL DEFAULT 'always_local'"),
                ('handoff_of', 'INTEGER REFERENCES messages(id)'),
                ('route_reason', 'TEXT'),
                ('document_context', 'TEXT'),
                ('web_context', 'TEXT'),
            ):
                if column not in columns:
                    db.execute(f'ALTER TABLE chat_inputs ADD COLUMN {column} {definition}')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS single_handoff ON chat_inputs(handoff_of) WHERE handoff_of IS NOT NULL')
            db.execute("""CREATE TABLE IF NOT EXISTS handoff_previews (
                message_id INTEGER PRIMARY KEY REFERENCES messages(id),
                token TEXT NOT NULL, reason TEXT NOT NULL)""")
            initialize(db)
            # A previous process may have ended mid-response.
            db.execute("UPDATE messages SET status='stopped', error='Application stopped during generation.' WHERE status='streaming'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self):
        cid = str(uuid4())
        with self.connect() as db:
            db.execute('INSERT INTO conversations(id,title) VALUES (?,?)', (cid, 'New conversation'))
        return self.conversation(cid)

    def list(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM conversations ORDER BY updated_at DESC, rowid DESC')]

    def conversation(self, cid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM conversations WHERE id=?', (cid,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            result['messages'] = [dict(r) for r in db.execute('''
                SELECT m.*, i.model AS requested_model, i.omitted_messages, i.retry_of, i.routing_mode, i.handoff_of, i.route_reason,
                    CASE WHEN i.handoff_of IS NOT NULL THEN json_extract(i.messages, '$[0].content') END AS handoff_brief,
                    EXISTS (SELECT 1 FROM chat_inputs h WHERE h.handoff_of=m.id) AS has_handoff,
                    json_array_length(i.messages) AS context_messages, i.document_context, i.web_context
                FROM messages m LEFT JOIN chat_inputs i ON i.message_id=m.id
                WHERE m.conversation_id=? ORDER BY m.id''', (cid,))]
            for message in result['messages']:
                message['document_context'] = json.loads(message['document_context']) if message['document_context'] else None
                message['web_context'] = json.loads(message['web_context']) if message['web_context'] else None
                document = self.document(cid, message['document_id']) if message['document_id'] else None
                message['document'] = document_metadata(document) if document else None
                attempt = db.execute('SELECT * FROM inference_attempts WHERE message_id=?', (message['id'],)).fetchone()
                message['telemetry'] = dict(attempt) if attempt else None
            document = self.document(cid)
            result['document'] = document_metadata(document) if document else None
            return result

    def save_document(self, cid, filename, extracted):
        document = dict(extracted, id=str(uuid4()), filename=filename)
        with self.connect() as db:
            db.execute('INSERT INTO pdf_documents VALUES (?,?,?,?,?,?)',
                       (document['id'], cid, filename, document['page_count'],
                        json.dumps(document['pages']), json.dumps(document['unreadable_pages'])))
        return document_metadata(document)

    def document(self, cid, document_id=None):
        with self.connect() as db:
            if document_id:
                row = db.execute('SELECT * FROM pdf_documents WHERE id=? AND conversation_id=?',
                                 (document_id, cid)).fetchone()
            else:
                row = db.execute('''SELECT d.* FROM pdf_documents d JOIN messages m ON m.document_id=d.id
                    WHERE d.conversation_id=? ORDER BY m.id DESC LIMIT 1''', (cid,)).fetchone()
            if row is None:
                return None
            return dict(row, pages=json.loads(row['pages']), unreadable_pages=json.loads(row['unreadable_pages']))

    def discard_document(self, cid, document_id):
        with self.connect() as db:
            return db.execute('''DELETE FROM pdf_documents WHERE id=? AND conversation_id=?
                AND NOT EXISTS (SELECT 1 FROM messages WHERE document_id=?)''',
                              (document_id, cid, document_id)).rowcount > 0

    def document_coverage(self, mid):
        with self.connect() as db:
            row = db.execute('SELECT document_context FROM chat_inputs WHERE message_id=?', (mid,)).fetchone()
            return json.loads(row[0]) if row and row[0] else None

    def web_coverage(self, mid):
        with self.connect() as db:
            row = db.execute('SELECT web_context FROM chat_inputs WHERE message_id=?', (mid,)).fetchone()
            return json.loads(row[0]) if row and row[0] else None

    def save_web_input(self, mid, messages, omitted, search):
        with self.connect() as db:
            db.execute('UPDATE chat_inputs SET messages=?,omitted_messages=?,web_context=? WHERE message_id=?',
                       (json.dumps(messages), omitted, json.dumps(search), mid))

    def add(self, cid, role, content, model=None, status='complete'):
        with self.connect() as db:
            return self._add(db, cid, role, content, model, status)

    def _add(self, db, cid, role, content, model=None, status='complete'):
        cur = db.execute('INSERT INTO messages(conversation_id,role,content,model,status) VALUES (?,?,?,?,?)',
                         (cid, role, content, model, status))
        if role == 'user':
            db.execute("UPDATE conversations SET title=? WHERE id=? AND title='New conversation'",
                       (' '.join(content.split())[:60], cid))
        db.execute("UPDATE conversations SET updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (cid,))
        return cur.lastrowid

    def finish(self, mid, content, status, model, latency_ms, prompt_tokens=None, output_tokens=None, error=None):
        with self.connect() as db:
            db.execute('UPDATE messages SET content=?,status=?,model=?,latency_ms=?,prompt_tokens=?,output_tokens=?,error=? WHERE id=?',
                       (content, status, model, latency_ms, prompt_tokens, output_tokens, error, mid))

    def context(self, cid):
        with self.connect() as db:
            rows = db.execute("SELECT role,content FROM messages WHERE conversation_id=? AND status='complete' ORDER BY id", (cid,)).fetchall()
            return [dict(r) for r in rows[-12:]], max(0, len(rows)-12)

    def retry_input(self, cid, mid):
        with self.connect() as db:
            latest = db.execute('SELECT id, role, status FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 1',
                                (cid,)).fetchone()
            if not latest or latest['id'] != mid or latest['role'] != 'assistant' or latest['status'] not in ('stopped', 'error'):
                return None
            recorded = db.execute('SELECT messages, omitted_messages, handoff_of FROM chat_inputs WHERE message_id=?', (mid,)).fetchone()
            if recorded and recorded['handoff_of'] is not None:
                return None
            if recorded:
                return json.loads(recorded['messages']), recorded['omitted_messages']
            # Older databases may only have the saved chat messages.
            rows = db.execute("""
                SELECT role, content FROM messages
                WHERE conversation_id=? AND id<? AND status='complete' ORDER BY id""", (cid, mid)).fetchall()
            if not rows or rows[-1]['role'] != 'user':
                return None
            return [dict(row) for row in rows[-13:]], max(0, len(rows)-13)

    def handoff_input(self, cid, mid):
        with self.connect() as db:
            row = db.execute("""
                SELECT m.content, m.model, i.messages FROM messages m JOIN chat_inputs i ON i.message_id=m.id
                WHERE m.id=? AND m.conversation_id=? AND m.status='complete'
                AND i.routing_mode='manual_handoff' AND i.handoff_of IS NULL
                AND NOT EXISTS (SELECT 1 FROM chat_inputs WHERE handoff_of=m.id)
                """, (mid, cid)).fetchone()
            return (json.loads(row['messages']), row['content'], row['model']) if row else None

    def save_preview(self, mid, reason):
        token = str(uuid4())
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO handoff_previews VALUES (?,?,?)', (mid, token, reason))
        return token

    def preview_reason(self, mid, token):
        with self.connect() as db:
            row = db.execute('SELECT reason FROM handoff_previews WHERE message_id=? AND token=?', (mid, token)).fetchone()
        return row['reason'] if row else None

    def begin_chat(self, cid, rid, model, messages, omitted, retry_of=None, *,
                   mode='always_local', handoff_of=None, reason=None, original_content=None,
                   document_id=None, document_context=None, web_context=None):
        with self.connect() as db:
            if retry_of is None and handoff_of is None:
                user_id = self._add(db, cid, 'user', original_content if original_content is not None else messages[-1]['content'])
                if document_id:
                    db.execute('UPDATE messages SET document_id=? WHERE id=?', (document_id, user_id))
            mid = self._add(db, cid, 'assistant', '', model, 'streaming')
            db.execute('''INSERT INTO chat_inputs(message_id,model,messages,omitted_messages,retry_of,routing_mode,handoff_of,route_reason,document_context,web_context)
                          VALUES (?,?,?,?,?,?,?,?,?,?)''',
                       (mid, model, json.dumps(messages), omitted, retry_of, mode, handoff_of, reason,
                        json.dumps(document_context) if document_context else None,
                        json.dumps(web_context) if web_context else None))
            db.execute('UPDATE inference_attempts SET message_id=? WHERE request_id=?', (mid, rid))
            return mid
