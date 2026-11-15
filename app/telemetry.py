"""Content-free inference ledger and provider-independent analytics.

Durations are milliseconds; costs are USD. Unknown values stay NULL. A request
is an admitted generation attempt (including failed model discovery), not an
HTTP validation rejection. No prompts, responses, or provider error text live here.
"""
import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4


def initialize(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
        CREATE TABLE IF NOT EXISTS inference_attempts (
            request_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id),
            message_id INTEGER UNIQUE REFERENCES messages(id),
            timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            provider TEXT NOT NULL, model TEXT NOT NULL,
            execution_location TEXT NOT NULL CHECK(execution_location IN ('local','cloud')),
            routing_mode TEXT NOT NULL DEFAULT 'local_only',
            task_id TEXT, benchmark_run_id TEXT,
            input_tokens INTEGER, output_tokens INTEGER,
            latency_ms REAL, ttft_ms REAL, generation_duration_ms REAL,
            tokens_per_second REAL, external_api_cost REAL,
            status TEXT NOT NULL CHECK(status IN ('running','success','error','cancelled')),
            feedback INTEGER CHECK(feedback IN (-1,1)),
            CHECK(input_tokens IS NULL OR input_tokens >= 0),
            CHECK(output_tokens IS NULL OR output_tokens >= 0));
        CREATE INDEX IF NOT EXISTS inference_time_model ON inference_attempts(timestamp,model);
        INSERT OR IGNORE INTO schema_migrations(version) VALUES (1);
    ''')
    db.execute("UPDATE inference_attempts SET status='cancelled' WHERE status='running'")


class Telemetry:
    def __init__(self, storage):
        self.storage = storage

    def start(self, cid, model, provider='ollama', location='local', cost=None):
        if location == 'local':
            cost = 0
        rid = str(uuid4())
        with self.storage.connect() as db:
            db.execute('''INSERT INTO inference_attempts
                (request_id,conversation_id,model,provider,execution_location,external_api_cost,routing_mode,status)
                VALUES (?,?,?,?,?,?,?,?)''',
                (rid, cid, model, provider, location, cost, 'local_only' if location == 'local' else 'cloud_only', 'running'))
        return rid

    def attach(self, rid, mid):
        with self.storage.connect() as db:
            db.execute('UPDATE inference_attempts SET message_id=? WHERE request_id=?', (mid, rid))

    def finish(self, rid, status, latency_ms, model=None, ttft_ms=None,
               input_tokens=None, output_tokens=None, generation_duration_ms=None, external_api_cost=None):
        speed = output_tokens / (generation_duration_ms / 1000) if output_tokens is not None and generation_duration_ms and generation_duration_ms > 0 else None
        with self.storage.connect() as db:
            db.execute('''UPDATE inference_attempts SET status=?,latency_ms=?,model=COALESCE(?,model),
                ttft_ms=?,input_tokens=?,output_tokens=?,generation_duration_ms=?,tokens_per_second=?,
                external_api_cost=CASE WHEN execution_location='local' THEN 0 ELSE COALESCE(?,external_api_cost) END
                WHERE request_id=? AND status='running' ''',
                (status, latency_ms, model, ttft_ms, input_tokens, output_tokens, generation_duration_ms, speed, external_api_cost, rid))
        return self.get(rid)

    def get(self, rid):
        with self.storage.connect() as db:
            row = db.execute('SELECT * FROM inference_attempts WHERE request_id=?', (rid,)).fetchone()
            return dict(row) if row else None

    def feedback(self, rid, value):
        with self.storage.connect() as db:
            return db.execute("UPDATE inference_attempts SET feedback=? WHERE request_id=? AND message_id IS NOT NULL AND status='success'", (value, rid)).rowcount

    def analytics(self, days=30, model=None):
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec='milliseconds').replace('+00:00', 'Z') if days else '0000'
        with self.storage.connect() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM inference_attempts WHERE timestamp>=? AND (? IS NULL OR model=?) ORDER BY timestamp', (since, model, model))]
            models = [r[0] for r in db.execute('SELECT DISTINCT model FROM inference_attempts ORDER BY model')]
        def aggregate(items):
            n = len(items)
            completed = [r for r in items if r['status'] == 'success']
            latencies = sorted(r['latency_ms'] for r in items if r['status'] != 'running' and r['latency_ms'] is not None)
            speeds = [r['tokens_per_second'] for r in items if r['tokens_per_second'] is not None]
            def total(key):
                values = [r[key] for r in items if r[key] is not None]
                return sum(values) if values else None
            return dict(requests=n, successful_requests=len(completed),
                local_percentage=100*sum(r['execution_location']=='local' for r in completed)/len(completed) if completed else None,
                cloud_percentage=100*sum(r['execution_location']=='cloud' for r in completed)/len(completed) if completed else None,
                external_api_cost=total('external_api_cost') if n else 0,
                cost_samples=sum(r['external_api_cost'] is not None for r in items),
                estimated_cloud_only_cost=None, estimated_api_savings=None,
                average_latency_ms=statistics.mean(latencies) if latencies else None,
                median_latency_ms=statistics.median(latencies) if latencies else None,
                p95_latency_ms=latencies[math.ceil(.95*len(latencies))-1] if len(latencies)>=20 else None,
                latency_samples=len(latencies), average_tokens_per_second=statistics.mean(speeds) if speeds else None,
                generation_speed_samples=len(speeds), input_tokens=total('input_tokens'), output_tokens=total('output_tokens'),
                input_token_samples=sum(r['input_tokens'] is not None for r in items),
                output_token_samples=sum(r['output_tokens'] is not None for r in items),
                failure_rate=100*sum(r['status']=='error' for r in items)/n if n else None,
                cancellation_rate=100*sum(r['status']=='cancelled' for r in items)/n if n else None,
                running_requests=sum(r['status']=='running' for r in items))
        groups, dates = defaultdict(list), defaultdict(list)
        for row in rows:
            groups[row['model']].append(row)
            dates[row['timestamp'][:10]].append(row)
        trends = []
        if dates:
            day = datetime.fromisoformat(min(dates))
            last = datetime.fromisoformat(max(dates))
            while day <= last:
                dates.setdefault(day.date().isoformat(), [])
                day += timedelta(days=1)
        for date, items in sorted(dates.items()):
            daily = aggregate(items)
            if not items:
                daily.update(input_tokens=0, output_tokens=0)
            trends.append(dict(date=date, **daily,
                local_requests=sum(r['execution_location']=='local' for r in items),
                cloud_requests=sum(r['execution_location']=='cloud' for r in items)))
        return dict(overview=aggregate(rows), by_model=[dict(model=k, **aggregate(v)) for k,v in groups.items()],
                    trends=trends, models=models, days=days, model=model)
