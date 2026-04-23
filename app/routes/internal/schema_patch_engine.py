
# schema_patch_engine.py
# Orkio Evolution Engine v1 — Safe Mode (branch + commit + PR workflow)
# Purpose:
# Detect missing schema objects from PostgreSQL errors and generate idempotent patches.

from __future__ import annotations
import re
from typing import Optional, Dict

SCHEMA_PATCH_TEMPLATES = {
    "thread_members": '''
CREATE TABLE IF NOT EXISTS thread_members (
    id VARCHAR PRIMARY KEY,
    org_slug VARCHAR NOT NULL,
    thread_id VARCHAR NOT NULL,
    user_id VARCHAR NOT NULL,
    role VARCHAR NOT NULL,
    created_at BIGINT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_thread_members_thread_user
ON thread_members(thread_id, user_id);
''',

    "realtime_sessions": '''
CREATE TABLE IF NOT EXISTS realtime_sessions (
    id VARCHAR PRIMARY KEY,
    org_slug VARCHAR NOT NULL,
    thread_id VARCHAR NOT NULL,
    agent_id VARCHAR,
    agent_name VARCHAR,
    user_id VARCHAR,
    user_name VARCHAR,
    model VARCHAR,
    voice VARCHAR,
    started_at BIGINT NOT NULL,
    ended_at BIGINT,
    meta TEXT
);
CREATE INDEX IF NOT EXISTS ix_realtime_sessions_thread
ON realtime_sessions(thread_id);
''',

    "realtime_events": '''
CREATE TABLE IF NOT EXISTS realtime_events (
    id VARCHAR PRIMARY KEY,
    org_slug VARCHAR NOT NULL,
    session_id VARCHAR NOT NULL,
    thread_id VARCHAR NOT NULL,
    speaker_type VARCHAR NOT NULL,
    speaker_id VARCHAR,
    agent_id VARCHAR,
    agent_name VARCHAR,
    event_type VARCHAR NOT NULL,
    transcript_raw TEXT,
    transcript_punct TEXT,
    created_at BIGINT NOT NULL,
    client_event_id VARCHAR,
    meta TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_realtime_events_org_sess_client_eid
ON realtime_events(org_slug, session_id, client_event_id);
'''
}


def detect_missing_table(pg_error: str) -> Optional[str]:
    """Detect missing table from PostgreSQL error string."""
    if not pg_error:
        return None

    match = re.search(r'relation "([^"]+)" does not exist', pg_error)
    if match:
        return match.group(1)

    return None


def generate_schema_patch(table_name: str) -> Optional[str]:
    """Return SQL patch for missing table."""
    return SCHEMA_PATCH_TEMPLATES.get(table_name)


def classify_and_patch(pg_error: str) -> Dict:
    """Main classifier entrypoint."""

    table = detect_missing_table(pg_error)

    if not table:
        return {
            "action": "none",
            "reason": "no_missing_table_detected"
        }

    patch_sql = generate_schema_patch(table)

    if not patch_sql:
        return {
            "action": "none",
            "reason": f"table_not_supported:{table}"
        }

    return {
        "action": "create_table_patch",
        "table": table,
        "sql": patch_sql
    }
