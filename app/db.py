from __future__ import annotations
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase


def _db_url() -> str:
    url = (
        os.getenv("DATABASE_PUBLIC_URL", "").strip().strip('"').strip("'")
        or os.getenv("DATABASE_URL_PUBLIC", "").strip().strip('"').strip("'")
        or os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")
    )
    url = url.replace("Postgres.railway.internal", "postgres.railway.internal")
    if not url:
        return ""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


class Base(DeclarativeBase):
    pass


def make_engine():
    url = _db_url()
    if not url:
        return None
    pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    connect_timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        connect_args={"connect_timeout": connect_timeout},
    )


ENGINE = make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE) if ENGINE else None


def _reconcile_core_auth_schema_boot():
    if ENGINE is None:
        return

    try:
        with ENGINE.begin() as conn:
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR,
                email VARCHAR UNIQUE NOT NULL,
                name VARCHAR,
                role VARCHAR DEFAULT 'user',
                salt VARCHAR,
                pw_hash VARCHAR,
                created_at BIGINT,
                approved_at BIGINT,
                signup_code_label VARCHAR,
                signup_source VARCHAR,
                usage_tier VARCHAR,
                terms_accepted_at BIGINT,
                terms_version VARCHAR,
                marketing_consent BOOLEAN DEFAULT FALSE,
                company VARCHAR,
                profile_role VARCHAR,
                user_type VARCHAR,
                intent VARCHAR,
                notes TEXT,
                country VARCHAR,
                language VARCHAR,
                whatsapp VARCHAR,
                onboarding_completed BOOLEAN DEFAULT FALSE,
                full_name VARCHAR,
                password_hash VARCHAR,
                is_active BOOLEAN DEFAULT TRUE
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS email VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS name VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS role VARCHAR DEFAULT 'user'",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS salt VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS pw_hash VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS approved_at BIGINT",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS signup_code_label VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS signup_source VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS usage_tier VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS terms_accepted_at BIGINT",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS terms_version VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS marketing_consent BOOLEAN DEFAULT FALSE",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS company VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS profile_role VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS user_type VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS intent VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS notes TEXT",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS country VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS language VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS whatsapp VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN DEFAULT FALSE",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS full_name VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS password_hash VARCHAR",
                "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
                "CREATE INDEX IF NOT EXISTS ix_users_org_slug ON users(org_slug)",
                "CREATE INDEX IF NOT EXISTS ix_users_email ON users(email)",
                "CREATE INDEX IF NOT EXISTS ix_users_role ON users(role)",
                "CREATE INDEX IF NOT EXISTS ix_users_created_at ON users(created_at)",
                "CREATE INDEX IF NOT EXISTS ix_users_org_email ON users(org_slug, email)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
            UPDATE users SET pw_hash = password_hash
            WHERE pw_hash IS NULL AND password_hash IS NOT NULL
            """))
            conn.execute(text("""
            UPDATE users SET password_hash = pw_hash
            WHERE password_hash IS NULL AND pw_hash IS NOT NULL
            """))
            conn.execute(text("""
            UPDATE users SET full_name = name
            WHERE full_name IS NULL AND name IS NOT NULL
            """))
            conn.execute(text("""
            UPDATE users SET name = full_name
            WHERE name IS NULL AND full_name IS NOT NULL
            """))
            conn.execute(text("UPDATE users SET role = 'user' WHERE role IS NULL"))
            conn.execute(text("UPDATE users SET is_active = TRUE WHERE is_active IS NULL"))
            conn.execute(text("UPDATE users SET onboarding_completed = FALSE WHERE onboarding_completed IS NULL"))
            conn.execute(text("UPDATE users SET marketing_consent = FALSE WHERE marketing_consent IS NULL"))

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS otp_codes (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR,
                code_hash VARCHAR NOT NULL,
                expires_at BIGINT,
                attempts INTEGER DEFAULT 0,
                verified BOOLEAN DEFAULT FALSE,
                created_at BIGINT
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS otp_codes ADD COLUMN IF NOT EXISTS user_id VARCHAR",
                "ALTER TABLE IF EXISTS otp_codes ADD COLUMN IF NOT EXISTS code_hash VARCHAR",
                "ALTER TABLE IF EXISTS otp_codes ADD COLUMN IF NOT EXISTS expires_at BIGINT",
                "ALTER TABLE IF EXISTS otp_codes ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS otp_codes ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE",
                "ALTER TABLE IF EXISTS otp_codes ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "ALTER TABLE IF EXISTS otp_codes ADD COLUMN IF NOT EXISTS email VARCHAR",
                "ALTER TABLE IF EXISTS otp_codes ADD COLUMN IF NOT EXISTS used BOOLEAN DEFAULT FALSE",
                "CREATE INDEX IF NOT EXISTS ix_otp_codes_user_id ON otp_codes(user_id)",
                "CREATE INDEX IF NOT EXISTS ix_otp_codes_email ON otp_codes(email)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR,
                org_slug VARCHAR,
                login_at BIGINT,
                logout_at BIGINT,
                last_seen_at BIGINT,
                ended_reason VARCHAR,
                duration_seconds INTEGER,
                source_code_label VARCHAR,
                usage_tier VARCHAR,
                ip_address VARCHAR
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS user_sessions ADD COLUMN IF NOT EXISTS user_id VARCHAR",
                "ALTER TABLE IF EXISTS user_sessions ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS user_sessions ADD COLUMN IF NOT EXISTS login_at BIGINT",
                "ALTER TABLE IF EXISTS user_sessions ADD COLUMN IF NOT EXISTS logout_at BIGINT",
                "ALTER TABLE IF EXISTS user_sessions ADD COLUMN IF NOT EXISTS last_seen_at BIGINT",
                "ALTER TABLE IF EXISTS user_sessions ADD COLUMN IF NOT EXISTS ended_reason VARCHAR",
                "ALTER TABLE IF EXISTS user_sessions ADD COLUMN IF NOT EXISTS duration_seconds INTEGER",
                "ALTER TABLE IF EXISTS user_sessions ADD COLUMN IF NOT EXISTS source_code_label VARCHAR",
                "ALTER TABLE IF EXISTS user_sessions ADD COLUMN IF NOT EXISTS usage_tier VARCHAR",
                "ALTER TABLE IF EXISTS user_sessions ADD COLUMN IF NOT EXISTS ip_address VARCHAR",
                "ALTER TABLE IF EXISTS user_sessions ADD COLUMN IF NOT EXISTS session_token VARCHAR",
                "ALTER TABLE IF EXISTS user_sessions ADD COLUMN IF NOT EXISTS expires_at BIGINT",
                "ALTER TABLE IF EXISTS user_sessions ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "CREATE INDEX IF NOT EXISTS ix_user_sessions_user_id ON user_sessions(user_id)",
                "CREATE INDEX IF NOT EXISTS ix_user_sessions_org_slug ON user_sessions(org_slug)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS terms_acceptances (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR NOT NULL,
                terms_version VARCHAR NOT NULL,
                accepted_at BIGINT NOT NULL,
                ip_address VARCHAR,
                user_agent VARCHAR
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS terms_acceptances ADD COLUMN IF NOT EXISTS user_id VARCHAR",
                "ALTER TABLE IF EXISTS terms_acceptances ADD COLUMN IF NOT EXISTS terms_version VARCHAR",
                "ALTER TABLE IF EXISTS terms_acceptances ADD COLUMN IF NOT EXISTS accepted_at BIGINT",
                "ALTER TABLE IF EXISTS terms_acceptances ADD COLUMN IF NOT EXISTS ip_address VARCHAR",
                "ALTER TABLE IF EXISTS terms_acceptances ADD COLUMN IF NOT EXISTS user_agent VARCHAR",
                "CREATE INDEX IF NOT EXISTS ix_terms_acceptances_user_id ON terms_acceptances(user_id)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS marketing_consents (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR,
                contact_id VARCHAR,
                channel VARCHAR NOT NULL,
                opt_in_date BIGINT,
                opt_out_date BIGINT,
                ip VARCHAR,
                source VARCHAR,
                created_at BIGINT NOT NULL
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS marketing_consents ADD COLUMN IF NOT EXISTS user_id VARCHAR",
                "ALTER TABLE IF EXISTS marketing_consents ADD COLUMN IF NOT EXISTS contact_id VARCHAR",
                "ALTER TABLE IF EXISTS marketing_consents ADD COLUMN IF NOT EXISTS channel VARCHAR",
                "ALTER TABLE IF EXISTS marketing_consents ADD COLUMN IF NOT EXISTS opt_in_date BIGINT",
                "ALTER TABLE IF EXISTS marketing_consents ADD COLUMN IF NOT EXISTS opt_out_date BIGINT",
                "ALTER TABLE IF EXISTS marketing_consents ADD COLUMN IF NOT EXISTS ip VARCHAR",
                "ALTER TABLE IF EXISTS marketing_consents ADD COLUMN IF NOT EXISTS source VARCHAR",
                "ALTER TABLE IF EXISTS marketing_consents ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "CREATE INDEX IF NOT EXISTS ix_marketing_consents_user_id ON marketing_consents(user_id)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS threads (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR,
                title VARCHAR,
                created_at BIGINT
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS threads ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS threads ADD COLUMN IF NOT EXISTS title VARCHAR",
                "ALTER TABLE IF EXISTS threads ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "ALTER TABLE IF EXISTS threads ADD COLUMN IF NOT EXISTS created_by VARCHAR",
                "CREATE INDEX IF NOT EXISTS ix_threads_org_slug ON threads(org_slug)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS messages (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR,
                thread_id VARCHAR,
                user_id VARCHAR,
                user_name VARCHAR,
                role VARCHAR,
                content TEXT,
                agent_id VARCHAR,
                agent_name VARCHAR,
                client_message_id VARCHAR,
                created_at BIGINT
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS thread_id VARCHAR",
                "ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS user_id VARCHAR",
                "ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS user_name VARCHAR",
                "ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS role VARCHAR",
                "ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS content TEXT",
                "ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS agent_id VARCHAR",
                "ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS agent_name VARCHAR",
                "ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS client_message_id VARCHAR",
                "ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "CREATE INDEX IF NOT EXISTS ix_messages_thread_id ON messages(thread_id)",
                "CREATE INDEX IF NOT EXISTS ix_messages_org_thread ON messages(org_slug, thread_id)",
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_messages_org_thread_client_msg ON messages(org_slug, thread_id, client_message_id)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

        print("CORE_AUTH_SCHEMA_BOOT_OK")
    except Exception as e:
        print("CORE_AUTH_SCHEMA_BOOT_FAILED", str(e))


def _reconcile_agents_schema_boot():
    if ENGINE is None:
        return

    try:
        with ENGINE.begin() as conn:
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agents (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR NOT NULL,
                name VARCHAR NOT NULL,
                description TEXT,
                system_prompt TEXT NOT NULL DEFAULT '',
                model VARCHAR,
                embedding_model VARCHAR,
                temperature VARCHAR,
                rag_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                rag_top_k INTEGER NOT NULL DEFAULT 6,
                is_default BOOLEAN NOT NULL DEFAULT FALSE,
                voice_id VARCHAR DEFAULT 'nova',
                avatar_url VARCHAR,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS agents ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS agents ADD COLUMN IF NOT EXISTS name VARCHAR",
                "ALTER TABLE IF EXISTS agents ADD COLUMN IF NOT EXISTS description TEXT",
                "ALTER TABLE IF EXISTS agents ADD COLUMN IF NOT EXISTS system_prompt TEXT DEFAULT ''",
                "ALTER TABLE IF EXISTS agents ADD COLUMN IF NOT EXISTS model VARCHAR",
                "ALTER TABLE IF EXISTS agents ADD COLUMN IF NOT EXISTS embedding_model VARCHAR",
                "ALTER TABLE IF EXISTS agents ADD COLUMN IF NOT EXISTS temperature VARCHAR",
                "ALTER TABLE IF EXISTS agents ADD COLUMN IF NOT EXISTS rag_enabled BOOLEAN NOT NULL DEFAULT TRUE",
                "ALTER TABLE IF EXISTS agents ADD COLUMN IF NOT EXISTS rag_top_k INTEGER NOT NULL DEFAULT 6",
                "ALTER TABLE IF EXISTS agents ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE IF EXISTS agents ADD COLUMN IF NOT EXISTS voice_id VARCHAR DEFAULT 'nova'",
                "ALTER TABLE IF EXISTS agents ADD COLUMN IF NOT EXISTS avatar_url VARCHAR",
                "ALTER TABLE IF EXISTS agents ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "ALTER TABLE IF EXISTS agents ADD COLUMN IF NOT EXISTS updated_at BIGINT",
                "CREATE INDEX IF NOT EXISTS ix_agents_org_slug ON agents(org_slug)",
                "CREATE INDEX IF NOT EXISTS ix_agents_updated_at ON agents(updated_at)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("UPDATE agents SET system_prompt = '' WHERE system_prompt IS NULL"))
            conn.execute(text("UPDATE agents SET rag_enabled = TRUE WHERE rag_enabled IS NULL"))
            conn.execute(text("UPDATE agents SET rag_top_k = 6 WHERE rag_top_k IS NULL"))
            conn.execute(text("UPDATE agents SET is_default = FALSE WHERE is_default IS NULL"))
            conn.execute(text("UPDATE agents SET voice_id = 'nova' WHERE voice_id IS NULL"))
            conn.execute(text("UPDATE agents SET updated_at = created_at WHERE updated_at IS NULL AND created_at IS NOT NULL"))

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_knowledge (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR NOT NULL,
                agent_id VARCHAR NOT NULL,
                file_id VARCHAR NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at BIGINT NOT NULL
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS agent_knowledge ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS agent_knowledge ADD COLUMN IF NOT EXISTS agent_id VARCHAR",
                "ALTER TABLE IF EXISTS agent_knowledge ADD COLUMN IF NOT EXISTS file_id VARCHAR",
                "ALTER TABLE IF EXISTS agent_knowledge ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE",
                "ALTER TABLE IF EXISTS agent_knowledge ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "CREATE INDEX IF NOT EXISTS ix_agent_knowledge_org_slug ON agent_knowledge(org_slug)",
                "CREATE INDEX IF NOT EXISTS ix_agent_knowledge_agent_id ON agent_knowledge(agent_id)",
                "CREATE INDEX IF NOT EXISTS ix_agent_knowledge_file_id ON agent_knowledge(file_id)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_links (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR NOT NULL,
                source_agent_id VARCHAR NOT NULL,
                target_agent_id VARCHAR NOT NULL,
                mode VARCHAR NOT NULL DEFAULT 'consult',
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at BIGINT NOT NULL
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS agent_links ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS agent_links ADD COLUMN IF NOT EXISTS source_agent_id VARCHAR",
                "ALTER TABLE IF EXISTS agent_links ADD COLUMN IF NOT EXISTS target_agent_id VARCHAR",
                "ALTER TABLE IF EXISTS agent_links ADD COLUMN IF NOT EXISTS mode VARCHAR NOT NULL DEFAULT 'consult'",
                "ALTER TABLE IF EXISTS agent_links ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE",
                "ALTER TABLE IF EXISTS agent_links ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "CREATE INDEX IF NOT EXISTS ix_agent_links_org_slug ON agent_links(org_slug)",
                "CREATE INDEX IF NOT EXISTS ix_agent_links_source_agent_id ON agent_links(source_agent_id)",
                "CREATE INDEX IF NOT EXISTS ix_agent_links_target_agent_id ON agent_links(target_agent_id)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

        print("AGENTS_SCHEMA_RECONCILE_DB_BOOT_OK")
    except Exception as e:
        print("AGENTS_SCHEMA_RECONCILE_DB_BOOT_FAILED", str(e))


def _reconcile_collab_and_realtime_schema_boot():
    if ENGINE is None:
        return

    try:
        with ENGINE.begin() as conn:
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS thread_members (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR NOT NULL,
                thread_id VARCHAR NOT NULL,
                user_id VARCHAR NOT NULL,
                role VARCHAR NOT NULL,
                created_at BIGINT NOT NULL
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS thread_members ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS thread_members ADD COLUMN IF NOT EXISTS thread_id VARCHAR",
                "ALTER TABLE IF EXISTS thread_members ADD COLUMN IF NOT EXISTS user_id VARCHAR",
                "ALTER TABLE IF EXISTS thread_members ADD COLUMN IF NOT EXISTS role VARCHAR",
                "ALTER TABLE IF EXISTS thread_members ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "CREATE INDEX IF NOT EXISTS ix_thread_members_org_slug ON thread_members(org_slug)",
                "CREATE INDEX IF NOT EXISTS ix_thread_members_thread_id ON thread_members(thread_id)",
                "CREATE INDEX IF NOT EXISTS ix_thread_members_user_id ON thread_members(user_id)",
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_thread_members_thread_user ON thread_members(thread_id, user_id)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
            UPDATE thread_members SET role = 'member'
            WHERE role IS NULL OR role = ''
            """))

            conn.execute(text("""
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
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS realtime_sessions ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS realtime_sessions ADD COLUMN IF NOT EXISTS thread_id VARCHAR",
                "ALTER TABLE IF EXISTS realtime_sessions ADD COLUMN IF NOT EXISTS agent_id VARCHAR",
                "ALTER TABLE IF EXISTS realtime_sessions ADD COLUMN IF NOT EXISTS agent_name VARCHAR",
                "ALTER TABLE IF EXISTS realtime_sessions ADD COLUMN IF NOT EXISTS user_id VARCHAR",
                "ALTER TABLE IF EXISTS realtime_sessions ADD COLUMN IF NOT EXISTS user_name VARCHAR",
                "ALTER TABLE IF EXISTS realtime_sessions ADD COLUMN IF NOT EXISTS model VARCHAR",
                "ALTER TABLE IF EXISTS realtime_sessions ADD COLUMN IF NOT EXISTS voice VARCHAR",
                "ALTER TABLE IF EXISTS realtime_sessions ADD COLUMN IF NOT EXISTS started_at BIGINT",
                "ALTER TABLE IF EXISTS realtime_sessions ADD COLUMN IF NOT EXISTS ended_at BIGINT",
                "ALTER TABLE IF EXISTS realtime_sessions ADD COLUMN IF NOT EXISTS meta TEXT",
                "CREATE INDEX IF NOT EXISTS ix_realtime_sessions_org_slug ON realtime_sessions(org_slug)",
                "CREATE INDEX IF NOT EXISTS ix_realtime_sessions_thread_id ON realtime_sessions(thread_id)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
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
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS realtime_events ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS realtime_events ADD COLUMN IF NOT EXISTS session_id VARCHAR",
                "ALTER TABLE IF EXISTS realtime_events ADD COLUMN IF NOT EXISTS thread_id VARCHAR",
                "ALTER TABLE IF EXISTS realtime_events ADD COLUMN IF NOT EXISTS speaker_type VARCHAR",
                "ALTER TABLE IF EXISTS realtime_events ADD COLUMN IF NOT EXISTS speaker_id VARCHAR",
                "ALTER TABLE IF EXISTS realtime_events ADD COLUMN IF NOT EXISTS agent_id VARCHAR",
                "ALTER TABLE IF EXISTS realtime_events ADD COLUMN IF NOT EXISTS agent_name VARCHAR",
                "ALTER TABLE IF EXISTS realtime_events ADD COLUMN IF NOT EXISTS event_type VARCHAR",
                "ALTER TABLE IF EXISTS realtime_events ADD COLUMN IF NOT EXISTS transcript_raw TEXT",
                "ALTER TABLE IF EXISTS realtime_events ADD COLUMN IF NOT EXISTS transcript_punct TEXT",
                "ALTER TABLE IF EXISTS realtime_events ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "ALTER TABLE IF EXISTS realtime_events ADD COLUMN IF NOT EXISTS client_event_id VARCHAR",
                "ALTER TABLE IF EXISTS realtime_events ADD COLUMN IF NOT EXISTS meta TEXT",
                "CREATE INDEX IF NOT EXISTS ix_realtime_events_org_slug ON realtime_events(org_slug)",
                "CREATE INDEX IF NOT EXISTS ix_realtime_events_session_id ON realtime_events(session_id)",
                "CREATE INDEX IF NOT EXISTS ix_realtime_events_thread_id ON realtime_events(thread_id)",
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_realtime_events_org_sess_client_eid ON realtime_events(org_slug, session_id, client_event_id)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

        print("COLLAB_REALTIME_SCHEMA_BOOT_OK")
    except Exception as e:
        print("COLLAB_REALTIME_SCHEMA_BOOT_FAILED", str(e))


def _reconcile_files_schema_boot():
    if ENGINE is None:
        return

    try:
        with ENGINE.begin() as conn:
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS files (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR,
                thread_id VARCHAR,
                uploader_id VARCHAR,
                uploader_name VARCHAR,
                uploader_email VARCHAR,
                filename VARCHAR,
                original_filename VARCHAR,
                origin VARCHAR,
                scope_thread_id VARCHAR,
                scope_agent_id VARCHAR,
                mime_type VARCHAR,
                size_bytes BIGINT DEFAULT 0,
                content BYTEA,
                extraction_failed BOOLEAN DEFAULT FALSE,
                is_institutional BOOLEAN DEFAULT FALSE,
                created_at BIGINT,
                origin_thread_id VARCHAR,
                name VARCHAR
            )
            """))

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS signup_codes (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR NOT NULL,
                code_hash VARCHAR NOT NULL,
                label VARCHAR NOT NULL,
                source VARCHAR NOT NULL,
                expires_at BIGINT,
                max_uses INTEGER NOT NULL DEFAULT 500,
                used_count INTEGER NOT NULL DEFAULT 0,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at BIGINT NOT NULL,
                created_by VARCHAR
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS thread_id VARCHAR",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS uploader_id VARCHAR",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS uploader_name VARCHAR",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS uploader_email VARCHAR",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS filename VARCHAR",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS original_filename VARCHAR",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS origin VARCHAR",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS scope_thread_id VARCHAR",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS scope_agent_id VARCHAR",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS mime_type VARCHAR",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS size_bytes BIGINT NOT NULL DEFAULT 0",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS content BYTEA",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS extraction_failed BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS is_institutional BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS origin_thread_id VARCHAR",
                "ALTER TABLE IF EXISTS files ADD COLUMN IF NOT EXISTS name VARCHAR",
                "CREATE INDEX IF NOT EXISTS ix_files_thread_id ON files(thread_id)",
                "CREATE INDEX IF NOT EXISTS ix_files_scope_thread_id ON files(scope_thread_id)",
                "CREATE INDEX IF NOT EXISTS ix_files_scope_agent_id ON files(scope_agent_id)",
                "CREATE INDEX IF NOT EXISTS ix_signup_codes_org ON signup_codes(org_slug)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
            UPDATE files SET name = filename
            WHERE name IS NULL AND filename IS NOT NULL
            """))

            try:
                conn.execute(text("ALTER TABLE IF EXISTS files ALTER COLUMN name DROP NOT NULL"))
            except Exception:
                pass

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS file_texts (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR NOT NULL,
                file_id VARCHAR NOT NULL,
                text TEXT NOT NULL,
                extracted_chars INTEGER NOT NULL DEFAULT 0,
                created_at BIGINT NOT NULL
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS file_texts ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS file_texts ADD COLUMN IF NOT EXISTS file_id VARCHAR",
                "ALTER TABLE IF EXISTS file_texts ADD COLUMN IF NOT EXISTS text TEXT",
                "ALTER TABLE IF EXISTS file_texts ADD COLUMN IF NOT EXISTS extracted_chars INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE IF EXISTS file_texts ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "CREATE INDEX IF NOT EXISTS ix_file_texts_org_slug ON file_texts(org_slug)",
                "CREATE INDEX IF NOT EXISTS ix_file_texts_file_id ON file_texts(file_id)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS file_chunks (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR NOT NULL,
                file_id VARCHAR NOT NULL,
                idx INTEGER NOT NULL,
                content TEXT NOT NULL,
                agent_id VARCHAR,
                agent_name VARCHAR,
                created_at BIGINT NOT NULL
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS file_chunks ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS file_chunks ADD COLUMN IF NOT EXISTS file_id VARCHAR",
                "ALTER TABLE IF EXISTS file_chunks ADD COLUMN IF NOT EXISTS idx INTEGER",
                "ALTER TABLE IF EXISTS file_chunks ADD COLUMN IF NOT EXISTS content TEXT",
                "ALTER TABLE IF EXISTS file_chunks ADD COLUMN IF NOT EXISTS agent_id VARCHAR",
                "ALTER TABLE IF EXISTS file_chunks ADD COLUMN IF NOT EXISTS agent_name VARCHAR",
                "ALTER TABLE IF EXISTS file_chunks ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "CREATE INDEX IF NOT EXISTS ix_file_chunks_org_slug ON file_chunks(org_slug)",
                "CREATE INDEX IF NOT EXISTS ix_file_chunks_file_id ON file_chunks(file_id)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR NOT NULL,
                user_id VARCHAR,
                action VARCHAR NOT NULL,
                meta TEXT,
                request_id VARCHAR,
                path VARCHAR,
                status_code INTEGER,
                latency_ms INTEGER,
                created_at BIGINT NOT NULL
            )
            """))

            stmts = [
                "ALTER TABLE IF EXISTS audit_logs ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS audit_logs ADD COLUMN IF NOT EXISTS user_id VARCHAR",
                "ALTER TABLE IF EXISTS audit_logs ADD COLUMN IF NOT EXISTS action VARCHAR",
                "ALTER TABLE IF EXISTS audit_logs ADD COLUMN IF NOT EXISTS meta TEXT",
                "ALTER TABLE IF EXISTS audit_logs ADD COLUMN IF NOT EXISTS request_id VARCHAR",
                "ALTER TABLE IF EXISTS audit_logs ADD COLUMN IF NOT EXISTS path VARCHAR",
                "ALTER TABLE IF EXISTS audit_logs ADD COLUMN IF NOT EXISTS status_code INTEGER",
                "ALTER TABLE IF EXISTS audit_logs ADD COLUMN IF NOT EXISTS latency_ms INTEGER",
                "ALTER TABLE IF EXISTS audit_logs ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "CREATE INDEX IF NOT EXISTS ix_audit_logs_org_slug ON audit_logs(org_slug)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

        print("FILES_SCHEMA_RECONCILE_DB_BOOT_OK")
    except Exception as e:
        print("FILES_SCHEMA_RECONCILE_DB_BOOT_FAILED", str(e))


def _reconcile_evolution_governance_schema_boot():
    if ENGINE is None:
        return

    try:
        with ENGINE.begin() as conn:
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS evolution_proposals (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR NOT NULL DEFAULT 'system',
                fingerprint VARCHAR NOT NULL,
                code VARCHAR NOT NULL,
                severity VARCHAR NOT NULL,
                category VARCHAR NOT NULL,
                source VARCHAR NOT NULL,
                action VARCHAR NOT NULL,
                status VARCHAR NOT NULL DEFAULT 'awaiting_master_approval',
                title VARCHAR,
                summary TEXT,
                finding_json TEXT,
                issue_json TEXT,
                decision_json TEXT,
                approval_note TEXT,
                rejection_note TEXT,
                first_detected_at BIGINT NOT NULL,
                last_detected_at BIGINT NOT NULL,
                detected_count INTEGER NOT NULL DEFAULT 1,
                approved_by VARCHAR,
                approved_at BIGINT,
                rejected_by VARCHAR,
                rejected_at BIGINT,
                last_trace_id VARCHAR,
                last_execution_status VARCHAR,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL
            )
            """))
            stmts = [
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS fingerprint VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS code VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS severity VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS category VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS source VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS action VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS status VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS title VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS summary TEXT",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS finding_json TEXT",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS issue_json TEXT",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS decision_json TEXT",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS approval_note TEXT",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS rejection_note TEXT",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS domain_scope VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS recurrence_window_count INTEGER DEFAULT 1",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS blast_radius_accumulated INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS security_accumulated INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS last_priority_score INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS last_recommendation VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS last_cadence_seconds INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS first_detected_at BIGINT",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS last_detected_at BIGINT",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS detected_count INTEGER DEFAULT 1",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS approved_by VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS approved_at BIGINT",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS rejected_by VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS rejected_at BIGINT",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS last_trace_id VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS last_execution_status VARCHAR",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "ALTER TABLE IF EXISTS evolution_proposals ADD COLUMN IF NOT EXISTS updated_at BIGINT",
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_evolution_proposals_fingerprint ON evolution_proposals(fingerprint)",
                "CREATE INDEX IF NOT EXISTS ix_evolution_proposals_org_status ON evolution_proposals(org_slug, status)",
                "CREATE INDEX IF NOT EXISTS ix_evolution_proposals_status_updated ON evolution_proposals(status, updated_at)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS evolution_executions (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR NOT NULL DEFAULT 'system',
                proposal_id VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                mode VARCHAR NOT NULL DEFAULT 'manual',
                actor_ref VARCHAR,
                trace_id VARCHAR,
                result_json TEXT,
                error_text TEXT,
                started_at BIGINT,
                completed_at BIGINT,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL
            )
            """))
            stmts = [
                "ALTER TABLE IF EXISTS evolution_executions ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS evolution_executions ADD COLUMN IF NOT EXISTS proposal_id VARCHAR",
                "ALTER TABLE IF EXISTS evolution_executions ADD COLUMN IF NOT EXISTS status VARCHAR",
                "ALTER TABLE IF EXISTS evolution_executions ADD COLUMN IF NOT EXISTS mode VARCHAR",
                "ALTER TABLE IF EXISTS evolution_executions ADD COLUMN IF NOT EXISTS actor_ref VARCHAR",
                "ALTER TABLE IF EXISTS evolution_executions ADD COLUMN IF NOT EXISTS trace_id VARCHAR",
                "ALTER TABLE IF EXISTS evolution_executions ADD COLUMN IF NOT EXISTS result_json TEXT",
                "ALTER TABLE IF EXISTS evolution_executions ADD COLUMN IF NOT EXISTS error_text TEXT",
                "ALTER TABLE IF EXISTS evolution_executions ADD COLUMN IF NOT EXISTS started_at BIGINT",
                "ALTER TABLE IF EXISTS evolution_executions ADD COLUMN IF NOT EXISTS completed_at BIGINT",
                "ALTER TABLE IF EXISTS evolution_executions ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "ALTER TABLE IF EXISTS evolution_executions ADD COLUMN IF NOT EXISTS updated_at BIGINT",
                "CREATE INDEX IF NOT EXISTS ix_evolution_executions_proposal_created ON evolution_executions(proposal_id, created_at)",
                "CREATE INDEX IF NOT EXISTS ix_evolution_executions_status_created ON evolution_executions(status, created_at)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS evolution_signal_snapshots (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR NOT NULL DEFAULT 'system',
                proposal_id VARCHAR NOT NULL,
                fingerprint VARCHAR NOT NULL,
                code VARCHAR NOT NULL,
                category VARCHAR NOT NULL,
                domain_scope VARCHAR,
                recurrence_window_count INTEGER NOT NULL DEFAULT 1,
                blast_radius_score INTEGER NOT NULL DEFAULT 0,
                security_score INTEGER NOT NULL DEFAULT 0,
                priority_score INTEGER NOT NULL DEFAULT 0,
                recommendation VARCHAR,
                cadence_seconds INTEGER NOT NULL DEFAULT 0,
                policy_version VARCHAR,
                trace_id VARCHAR,
                payload_json TEXT,
                created_at BIGINT NOT NULL
            )
            """))
            stmts = [
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS proposal_id VARCHAR",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS fingerprint VARCHAR",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS code VARCHAR",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS category VARCHAR",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS domain_scope VARCHAR",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS recurrence_window_count INTEGER DEFAULT 1",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS blast_radius_score INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS security_score INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS priority_score INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS recommendation VARCHAR",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS cadence_seconds INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS policy_version VARCHAR",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS trace_id VARCHAR",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS payload_json TEXT",
                "ALTER TABLE IF EXISTS evolution_signal_snapshots ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "CREATE INDEX IF NOT EXISTS ix_evolution_signal_snapshots_proposal_created ON evolution_signal_snapshots(proposal_id, created_at)",
                "CREATE INDEX IF NOT EXISTS ix_evolution_signal_snapshots_fingerprint_created ON evolution_signal_snapshots(fingerprint, created_at)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS evolution_cycle_logs (
                id VARCHAR PRIMARY KEY,
                org_slug VARCHAR NOT NULL DEFAULT 'system',
                trace_id VARCHAR,
                findings INTEGER NOT NULL DEFAULT 0,
                classified INTEGER NOT NULL DEFAULT 0,
                proposals_touched INTEGER NOT NULL DEFAULT 0,
                proposals_created INTEGER NOT NULL DEFAULT 0,
                proposals_suppressed INTEGER NOT NULL DEFAULT 0,
                max_priority_score INTEGER NOT NULL DEFAULT 0,
                avg_priority_score INTEGER NOT NULL DEFAULT 0,
                next_interval_suggested_seconds INTEGER NOT NULL DEFAULT 0,
                recommendation_buckets_json TEXT,
                domain_buckets_json TEXT,
                top_queue_json TEXT,
                policy_version VARCHAR,
                created_at BIGINT NOT NULL
            )
            """))
            stmts = [
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS org_slug VARCHAR",
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS trace_id VARCHAR",
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS findings INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS classified INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS proposals_touched INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS proposals_created INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS proposals_suppressed INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS max_priority_score INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS avg_priority_score INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS next_interval_suggested_seconds INTEGER DEFAULT 0",
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS recommendation_buckets_json TEXT",
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS domain_buckets_json TEXT",
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS top_queue_json TEXT",
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS policy_version VARCHAR",
                "ALTER TABLE IF EXISTS evolution_cycle_logs ADD COLUMN IF NOT EXISTS created_at BIGINT",
                "CREATE INDEX IF NOT EXISTS ix_evolution_cycle_logs_created ON evolution_cycle_logs(created_at)",
            ]
            for stmt in stmts:
                conn.execute(text(stmt))

        print("EVOLUTION_GOVERNANCE_SCHEMA_RECONCILE_DB_BOOT_OK")
    except Exception as e:
        print("EVOLUTION_GOVERNANCE_SCHEMA_RECONCILE_DB_BOOT_FAILED", str(e))


_reconcile_core_auth_schema_boot()
_reconcile_agents_schema_boot()
_reconcile_collab_and_realtime_schema_boot()
_reconcile_files_schema_boot()
_reconcile_evolution_governance_schema_boot()


def get_db():
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
