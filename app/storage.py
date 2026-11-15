"""SQLite persistence. Each operation owns its connection; no chat text is logged."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


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
            result['messages'] = [dict(r) for r in db.execute('SELECT * FROM messages WHERE conversation_id=? ORDER BY id', (cid,))]
            return result

    def add(self, cid, role, content, model=None, status='complete'):
        with self.connect() as db:
            cur = db.execute('INSERT INTO messages(conversation_id,role,content,model,status) VALUES (?,?,?,?,?)', (cid, role, content, model, status))
            if role == 'user':
                db.execute("UPDATE conversations SET title=? WHERE id=? AND title='New conversation'", (' '.join(content.split())[:60], cid))
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
