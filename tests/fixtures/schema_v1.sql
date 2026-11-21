-- Schema captured from the committed pre-Lab application.

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
    