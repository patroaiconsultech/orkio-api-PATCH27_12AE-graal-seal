from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import SessionLocal

router = APIRouter(prefix="/api/internal/db", tags=["db-internal"])


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip().strip('"').strip("'")


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _runtime_enabled() -> bool:
    return _env_flag("DB_RUNTIME_ENABLED", False)


def _require_approval() -> bool:
    return _env_flag("REQUIRE_EXPLICIT_DB_APPROVAL", True)


def _allowed_tables() -> List[str]:
    raw = _env("DB_RUNTIME_ALLOWED_TABLES", "cost_events")
    return [x.strip() for x in raw.split(",") if x.strip()]


def _check_enabled() -> None:
    if not _runtime_enabled():
        raise HTTPException(status_code=403, detail="DB runtime disabled")


SAFE_SCHEMAS: Dict[str, Dict[str, Dict[str, Optional[str]]]] = {
    "cost_events": {
        "id": {"type": "VARCHAR", "default": None},
        "org_slug": {"type": "VARCHAR", "default": None},
        "user_id": {"type": "VARCHAR", "default": None},
        "thread_id": {"type": "VARCHAR", "default": None},
        "message_id": {"type": "VARCHAR", "default": None},
        "agent_id": {"type": "VARCHAR", "default": None},
        "provider": {"type": "VARCHAR", "default": None},
        "model": {"type": "VARCHAR", "default": None},
        "prompt_tokens": {"type": "INTEGER", "default": "0"},
        "completion_tokens": {"type": "INTEGER", "default": "0"},
        "total_tokens": {"type": "INTEGER", "default": "0"},
        "cost_usd": {"type": "NUMERIC(12,6)", "default": "0"},
        "usage_missing": {"type": "BOOLEAN", "default": "FALSE"},
        "metadata": {"type": "TEXT", "default": None},
        "created_at": {"type": "BIGINT", "default": None},
        "input_cost_usd": {"type": "NUMERIC(12,6)", "default": "0"},
        "output_cost_usd": {"type": "NUMERIC(12,6)", "default": "0"},
        "total_cost_usd": {"type": "NUMERIC(12,6)", "default": "0"},
        "pricing_version": {"type": "VARCHAR", "default": "'2026-02-18'"},
        "pricing_snapshot": {"type": "TEXT", "default": None},
    }
}


class DbSchemaFixIn(BaseModel):
    table: str = Field(min_length=1, max_length=120)
    approval: Optional[str] = None


def _normalize_table_name(name: str) -> str:
    return (name or "").strip().lower()


def _assert_table_allowed(table: str) -> str:
    table_name = _normalize_table_name(table)
    if table_name not in _allowed_tables():
        raise HTTPException(status_code=403, detail=f"Table not allowed for DB runtime: {table_name}")
    if table_name not in SAFE_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"No safe schema registered for table: {table_name}")
    return table_name


def _table_exists(db, table: str) -> bool:
    row = db.execute(
        text("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :table_name
            ) AS exists_flag
        """),
        {"table_name": table},
    ).first()
    return bool(row[0]) if row else False


def _existing_columns(db, table: str) -> Dict[str, Dict[str, Any]]:
    rows = db.execute(
        text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table_name
            ORDER BY ordinal_position
        """),
        {"table_name": table},
    ).all()
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        out[str(row[0])] = {
            "data_type": row[1],
            "is_nullable": row[2],
            "column_default": row[3],
        }
    return out


def _create_table_sql(table: str) -> str:
    schema = SAFE_SCHEMAS[table]
    lines: List[str] = []
    for column_name, spec in schema.items():
        col = f"{column_name} {spec['type']}"
        if column_name == "id":
            col += " PRIMARY KEY"
        if spec.get("default") is not None:
            col += f" DEFAULT {spec['default']}"
        lines.append(col)
    inner = ",\n    ".join(lines)
    return f"CREATE TABLE IF NOT EXISTS {table} (\n    {inner}\n)"


def _missing_column_sql(table: str, column_name: str) -> str:
    spec = SAFE_SCHEMAS[table][column_name]
    stmt = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column_name} {spec['type']}"
    if spec.get("default") is not None:
        stmt += f" DEFAULT {spec['default']}"
    return stmt


def build_schema_plan(table: str, db=None) -> Dict[str, Any]:
    table_name = _assert_table_allowed(table)
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        exists = _table_exists(db, table_name)
        expected = SAFE_SCHEMAS[table_name]
        existing = _existing_columns(db, table_name) if exists else {}
        missing_columns = [col for col in expected.keys() if col not in existing]
        statements: List[str] = []
        if not exists:
            statements.append(_create_table_sql(table_name))
        for col in missing_columns:
            if exists:
                statements.append(_missing_column_sql(table_name, col))
        return {
            "ok": True,
            "table": table_name,
            "exists": exists,
            "missing_columns": missing_columns,
            "existing_columns": list(existing.keys()),
            "expected_columns": list(expected.keys()),
            "statements": statements,
            "needs_fix": (not exists) or bool(missing_columns),
        }
    finally:
        if close_db:
            db.close()


def apply_schema_plan(table: str) -> Dict[str, Any]:
    table_name = _assert_table_allowed(table)
    db = SessionLocal()
    try:
        plan = build_schema_plan(table_name, db=db)
        executed: List[str] = []
        if not plan["needs_fix"]:
            return {
                "ok": True,
                "table": table_name,
                "executed": executed,
                "message": "No drift detected",
                "validation": build_schema_plan(table_name, db=db),
            }
        for stmt in plan["statements"]:
            db.execute(text(stmt))
            executed.append(stmt)
        db.commit()
        validation = build_schema_plan(table_name, db=db)
        return {
            "ok": True,
            "table": table_name,
            "executed": executed,
            "validation": validation,
        }
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"DB runtime fix failed: {e}")
    finally:
        db.close()


@router.get("/health")
def db_runtime_health():
    return {
        "ok": True,
        "service": "db_internal",
        "runtime_enabled": _runtime_enabled(),
        "approval_required": _require_approval(),
        "allowed_tables": _allowed_tables(),
    }


@router.get("/schema/check")
def db_schema_check(table: str):
    _check_enabled()
    return build_schema_plan(table)


@router.post("/schema/fix")
def db_schema_fix(payload: DbSchemaFixIn):
    _check_enabled()
    if _require_approval():
        approval = (payload.approval or "").strip().lower()
        if approval not in {"de acordo", "aprovado", "autorizado", "pode seguir", "ok executar", "ok, executar", "liberado"}:
            raise HTTPException(status_code=400, detail="Explicit DB approval required")
    return apply_schema_plan(payload.table)
