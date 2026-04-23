from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from .schema_patch_engine import classify_and_patch

router = APIRouter(prefix="/api/internal/evolution", tags=["evolution-trigger"])


def _clean_env(v: Any, default: str = "") -> str:
    if v is None:
        return default
    s = str(v).strip()
    if not s:
        return default
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        s = s[1:-1].strip()
    return s


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _internal_api_base() -> str:
    return _clean_env(
        os.getenv("INTERNAL_API_BASE", "http://127.0.0.1:8080"),
        "http://127.0.0.1:8080",
    ).rstrip("/")


def _is_schema_error(error_text: str) -> bool:
    s = (error_text or "").lower()
    markers = (
        "undefinedtable",
        "undefinedcolumn",
        'relation "',
        "does not exist",
        "column ",
    )
    return any(m in s for m in markers)


def _apply_sql_patch_direct(sql_patch: str, table_name: str) -> Dict[str, Any]:
    from ...db import ENGINE

    if ENGINE is None:
        return {"ok": False, "reason": "engine_unavailable", "table": table_name}

    try:
        statements = [
            stmt.strip() for stmt in (sql_patch or "").split(";") if stmt.strip()
        ]
        with ENGINE.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
        print(f"AUTO_SCHEMA_HOTFIX_APPLIED table={table_name}")
        return {
            "ok": True,
            "table": table_name,
            "applied_statements": len(statements),
        }
    except Exception as e:
        print(f"AUTO_SCHEMA_HOTFIX_FAILED table={table_name}", str(e))
        return {"ok": False, "table": table_name, "reason": str(e)}


def _best_effort_open_pr(error_text: str, path: str) -> Optional[Dict[str, Any]]:
    if not _env_flag("AUTO_SCHEMA_PATCH_CREATE_PR", False):
        return None

    try:
        resp = requests.post(
            f"{_internal_api_base()}/api/internal/evolution/propose-schema-patch",
            json={
                "error_text": error_text,
                "path": path or "app/db.py",
                "auto_pr": True,
            },
            timeout=30,
        )
        try:
            return {"status_code": resp.status_code, "data": resp.json()}
        except Exception:
            return {"status_code": resp.status_code, "raw": resp.text}
    except Exception as e:
        return {"status_code": 0, "error": str(e)}


def maybe_trigger_schema_patch(
    error_text: str, path: str = "runtime_auto"
) -> Dict[str, Any]:
    raw = (error_text or "").strip()
    if not raw:
        return {"ok": False, "reason": "empty_error"}

    if not _is_schema_error(raw):
        return {"ok": False, "reason": "not_schema_error"}

    classification = classify_and_patch(raw)
    if classification.get("action") != "create_table_patch":
        return {
            "ok": False,
            "reason": "no_supported_patch",
            "classification": classification,
        }

    table_name = classification["table"]
    sql_patch = classification["sql"]

    direct_result = None
    if _env_flag("AUTO_SCHEMA_HOTFIX_DIRECT", True):
        direct_result = _apply_sql_patch_direct(sql_patch, table_name)

    pr_result = _best_effort_open_pr(raw, "app/db.py")

    return {
        "ok": True,
        "classification": classification,
        "direct_hotfix": direct_result,
        "pr_result": pr_result,
        "path": path,
    }


class RuntimeTriggerIn(BaseModel):
    error_text: str = Field(min_length=3, max_length=20000)
    path: str = Field(default="runtime_manual", min_length=1, max_length=300)


@router.get("/trigger-health")
def evolution_trigger_health():
    return {
        "ok": True,
        "service": "evolution_trigger",
        "auto_schema_hotfix_direct": _env_flag("AUTO_SCHEMA_HOTFIX_DIRECT", True),
        "auto_schema_patch_create_pr": _env_flag(
            "AUTO_SCHEMA_PATCH_CREATE_PR", False
        ),
        "internal_api_base": _internal_api_base(),
    }


@router.post("/runtime-trigger")
def evolution_runtime_trigger(payload: RuntimeTriggerIn):
    return maybe_trigger_schema_patch(payload.error_text, path=payload.path)
