"""Chat routing configuration and conservative daily cloud reservations."""
import os
from uuid import uuid4

from dotenv import dotenv_values
from pydantic import BaseModel, Field
from typing import Literal
from .credentials import NativeCredentialStore, CredentialError

Mode = Literal['always_local', 'manual_handoff', 'automatic_handoff', 'always_frontier']
# Integer nanodollars per token, standard uncached text rates.
RATES = {
    'gpt-6-luna': (100, 500),
    'gpt-4o-mini': (150, 600),
    'gpt-4o-mini-2024-07-18': (150, 600),
}
MAX_INPUT_BYTES = 8192
MAX_OUTPUT_TOKENS = 256
DEFAULT_CLOUD_MODEL = 'gpt-6-luna'
MODEL_LABELS = {'gpt-6-luna':'GPT-6 Luna', 'gpt-4o-mini':'GPT-4o mini (legacy)',
                'gpt-4o-mini-2024-07-18':'GPT-4o mini · July 2024 (legacy)'}


class SettingsInput(BaseModel):
    mode: Mode
    daily_limit_cents: int = Field(ge=0, le=10000, strict=True)
    acknowledged: bool = False


class Routing:
    def __init__(self, storage, secret_store=None, env_file=None):
        self.storage = storage
        self.secret_store = secret_store if secret_store is not None else NativeCredentialStore()
        self.connection_error = None
        # Read only the explicitly selected file; do not search parent directories
        # or expand variable references inside credentials.
        config = dotenv_values(env_file, interpolate=False) if env_file is not None else {}
        self.key = os.environ.get('OPENAI_API_KEY', '').strip() or (config.get('OPENAI_API_KEY') or '').strip()
        self.model = (os.environ.get('OPENAI_MODEL', '').strip()
                      or (config.get('OPENAI_MODEL') or '').strip()
                      or (DEFAULT_CLOUD_MODEL if self.key else ''))
        with storage.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS routing_settings (
                    id INTEGER PRIMARY KEY CHECK (id=1), mode TEXT NOT NULL,
                    daily_limit_cents INTEGER NOT NULL);
                INSERT OR IGNORE INTO routing_settings VALUES (1,'always_local',0);
                CREATE TABLE IF NOT EXISTS cloud_reservations (
                    request_id TEXT PRIMARY KEY, day TEXT NOT NULL, charge INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS provider_connection (
                    id INTEGER PRIMARY KEY CHECK (id=1), model TEXT NOT NULL,
                    credential_id TEXT NOT NULL);
            """)
            connection = db.execute('SELECT model,credential_id FROM provider_connection WHERE id=1').fetchone()
        if connection and not self.key:
            self.model = connection['model']
            try:
                self.key = self.secret_store.get(connection['credential_id']) or ''
                if not self.key:
                    self.connection_error = 'The saved key is unavailable. Reconnect OpenAI in Settings.'
            except CredentialError as exc:
                self.key = ''
                self.connection_error = str(exc)

    def settings(self):
        with self.storage.connect() as db:
            result = dict(db.execute('SELECT mode,daily_limit_cents FROM routing_settings WHERE id=1').fetchone())
        return dict(result, frontier_model=self.model or None, provider_ready=self.ready)

    @property
    def ready(self):
        return bool(self.key and self.model in RATES)

    def connection(self):
        return {'provider_ready':self.ready, 'model':self.model if self.model in RATES else DEFAULT_CLOUD_MODEL,
                'models':[{'id':model,'label':MODEL_LABELS[model]} for model in RATES],
                'error':self.connection_error}

    def connect(self, model, key):
        """Publish the new credential reference only after secure storage succeeds."""
        credential_id = str(uuid4())
        self.secret_store.set(credential_id, key)
        try:
            with self.storage.connect() as db:
                old = db.execute('SELECT credential_id FROM provider_connection WHERE id=1').fetchone()
                db.execute('''INSERT INTO provider_connection VALUES (1,?,?)
                    ON CONFLICT(id) DO UPDATE SET model=excluded.model,credential_id=excluded.credential_id''',
                           (model, credential_id))
        except Exception:
            self.secret_store.delete(credential_id)
            raise CredentialError('Could not save the connection. Your previous configuration is unchanged.') from None
        self.key, self.model, self.connection_error = key, model, None
        if old:
            self.secret_store.delete(old['credential_id'])

    def save(self, settings):
        with self.storage.connect() as db:
            db.execute('UPDATE routing_settings SET mode=?,daily_limit_cents=? WHERE id=1',
                       (settings.mode, settings.daily_limit_cents))

    def charge(self, input_tokens, output_tokens):
        input_rate, output_rate = RATES[self.model]
        return input_tokens * input_rate + output_tokens * output_rate

    def estimate(self, messages):
        # Each text token consumes at least one byte. Allow extra framing per message.
        return self.charge(128 + sum(len(m['content'].encode()) + 32 for m in messages),
                           MAX_OUTPUT_TOKENS)

    def reserve(self, rid, messages, limit):
        estimate = self.estimate(messages)
        with self.storage.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            spent = db.execute("SELECT COALESCE(SUM(charge),0) FROM cloud_reservations WHERE day=date('now','localtime')").fetchone()[0]
            current_limit = db.execute('SELECT daily_limit_cents FROM routing_settings WHERE id=1').fetchone()[0]
            if spent + estimate > min(limit, current_limit) * 10_000_000:
                return False
            db.execute("INSERT INTO cloud_reservations VALUES (?,date('now','localtime'),?)", (rid, estimate))
        return True

    def daily_usage(self):
        with self.storage.connect() as db:
            result = db.execute("""
                SELECT COALESCE(SUM(r.charge),0) AS guarded,
                       COALESCE(SUM(CASE WHEN a.external_api_cost IS NULL THEN r.charge ELSE 0 END),0) AS pending
                FROM cloud_reservations r LEFT JOIN inference_attempts a ON a.request_id=r.request_id
                WHERE r.day=date('now','localtime')
            """).fetchone()
            limit = db.execute('SELECT daily_limit_cents FROM routing_settings WHERE id=1').fetchone()[0]
        return {'reserved_or_charged': result['guarded'] / 1e9,
                'unresolved_estimate': result['pending'] / 1e9, 'limit': limit / 100}

    def reconcile(self, rid, input_tokens, output_tokens):
        if input_tokens is None or output_tokens is None:
            return None
        charge = self.charge(input_tokens, output_tokens)
        with self.storage.connect() as db:
            db.execute('UPDATE cloud_reservations SET charge=? WHERE request_id=?', (charge, rid))
        return charge / 1_000_000_000


def bounded(messages):
    selected = []
    remaining = MAX_INPUT_BYTES
    for message in reversed(messages):
        content = message['content'].encode()
        if len(content) > remaining and selected:
            break
        selected.append(dict(message, content=content[:remaining].decode(errors='ignore')))
        remaining -= len(content)
    return list(reversed(selected))
