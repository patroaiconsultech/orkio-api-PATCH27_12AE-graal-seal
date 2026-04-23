
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, HTTPException, Header, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import EvolutionProposal, EvolutionExecution, EvolutionSignalSnapshot, EvolutionCycleLog
from app.security import decode_token

from app.self_heal.governance import EvolutionGovernanceService, run_governed_scan_cycle, detection_touch_cooldown_seconds, recurrence_window_seconds
from app.self_heal.policy import SelfHealPolicy, POLICY_VERSION
from app.self_heal.trust import build_trust_envelope, coerce_trust_envelope, trust_gate_reasons
from app.self_heal.semantic_validation import run_semantic_validation, run_post_execution_semantic_integrity
from app.self_heal.validators.base import SemanticValidationContext
from app.self_heal.credential_scope import is_branch_allowed, is_protected_branch, resolve_scoped_credentials

from .schema_patch_engine import classify_and_patch

router = APIRouter(prefix="/api/internal/evolution", tags=["evolution-internal"])


def _clean_env(name: str, default: str = "") -> str:
    v = os.getenv(name, default) or default
    v = str(v).strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        v = v[1:-1].strip()
    return v


def _base_url() -> str:
    return _clean_env("INTERNAL_API_BASE", "http://127.0.0.1:8080").rstrip("/")


def _default_branch() -> str:
    return _clean_env("GITHUB_BRANCH", "main") or "main"


def _master_admin_emails() -> list[str]:
    raw = (
        _clean_env("MASTER_ADMIN_EMAILS", "")
        or _clean_env("SUPER_ADMIN_EMAILS", "")
        or _clean_env("ADMIN_EMAILS", "")
    )
    if not raw:
        return []
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _master_admin_key() -> str:
    return _clean_env("MASTER_ADMIN_KEY", "") or _clean_env("ADMIN_API_KEY", "")


def _safe_branch_name(table_name: str) -> str:
    stamp = int(time.time())
    safe = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "-"
        for ch in (table_name or "unknown")
    )
    return f"selfheal/schema-{safe}-{stamp}"


def _internal_admin_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {}
    master_key = _master_admin_key()
    if master_key:
        headers["x-admin-key"] = master_key
    return headers


def _request(
    method: str,
    path: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = f"{_base_url()}{path}"
    try:
        resp = requests.request(method, url, json=json_body, headers=_internal_admin_headers(), timeout=30)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"internal request failed: {e}") from e

    try:
        detail: Any = resp.json()
    except Exception:
        detail = {"raw": resp.text}

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=detail)

    if isinstance(detail, dict):
        return detail
    return {"data": detail}


def _json_loads(raw: Optional[str]) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


def _safe_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _proposal_finding(row: EvolutionProposal) -> Dict[str, Any]:
    return _safe_dict(_json_loads(getattr(row, "finding_json", None)))


def _proposal_issue(row: EvolutionProposal) -> Dict[str, Any]:
    return _safe_dict(_json_loads(getattr(row, "issue_json", None)))


def _proposal_trust_envelope(row: EvolutionProposal) -> Dict[str, Any]:
    finding = _proposal_finding(row)
    issue = _proposal_issue(row)
    trust = finding.get("trust") or issue.get("trust")
    return coerce_trust_envelope(
        trust,
        fallback_source_type=getattr(row, "source", None) or issue.get("source") or "proposal",
        fallback_source_origin="evolution_internal",
    )


def _proposal_semantic_summary(
    *,
    row: EvolutionProposal,
    decision: Optional[Dict[str, Any]] = None,
    payload: Optional[Any] = None,
    result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    trust = _proposal_trust_envelope(row)
    result = _safe_dict(result)
    validation = _safe_dict(result.get("validation"))
    rollback = _safe_dict(result.get("rollback"))
    branch_payload = _safe_dict(result.get("branch"))
    target_branch = str(branch_payload.get("new_branch") or branch_payload.get("branch") or "").strip()
    changed_paths: list[str] = []
    path_candidate = None
    if payload is not None:
        path_candidate = getattr(payload, "path", None)
    if result.get("path"):
        path_candidate = result.get("path")
    if result.get("artifact_path"):
        path_candidate = result.get("artifact_path")
    if path_candidate:
        changed_paths.append(str(path_candidate))
    ctx = SemanticValidationContext(
        action=str(getattr(row, "action", None) or (decision or {}).get("action") or ""),
        domain_scope=str(getattr(row, "domain_scope", None) or "general"),
        proposal_id=str(getattr(row, "id", None) or ""),
        target_branch=target_branch or None,
        source_branch=(getattr(payload, "source_branch", None) if payload is not None else None),
        changed_paths=changed_paths,
        trust=trust,
        validation=validation,
        rollback=rollback,
        result=result,
        proposal={"id": getattr(row, "id", None), "code": getattr(row, "code", None), "status": getattr(row, "status", None)},
    )
    return run_semantic_validation(ctx)


def _new_trace_id() -> str:
    raw = f"evo:{time.time_ns()}"
    return "trace_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _build_db_patch(current_content: str, sql_patch: str, table_name: str) -> str:
    marker = "def _reconcile_self_heal_schema_boot():"
    if marker in current_content:
        return current_content

    bootstrap = f"""

def _reconcile_self_heal_schema_boot():
    if ENGINE is None:
        return
    try:
        with ENGINE.begin() as conn:
            conn.execute(text(\"\"\"
{sql_patch.strip()}
\"\"\"))
        print("SELF_HEAL_SCHEMA_BOOT_OK table={table_name}")
    except Exception as e:
        print("SELF_HEAL_SCHEMA_BOOT_FAILED table={table_name}", str(e))
"""

    call_marker = "_reconcile_files_schema_boot()"
    if call_marker in current_content:
        return current_content.replace(
            call_marker,
            f"_reconcile_self_heal_schema_boot()\\n{call_marker}",
            1,
        ) + bootstrap

    return current_content + bootstrap + "\n\n_reconcile_self_heal_schema_boot()\n"




def _score_band(value: Any) -> str:
    try:
        n = int(value or 0)
    except Exception:
        n = 0
    if n >= 85:
        return "critical"
    if n >= 70:
        return "high"
    if n >= 45:
        return "medium"
    if n > 0:
        return "low"
    return "none"


def _priority_label(value: Any) -> str:
    band = _score_band(value)
    return {
        "critical": "Priority P0",
        "high": "Priority P1",
        "medium": "Priority P2",
        "low": "Priority P3",
        "none": "Priority P4",
    }.get(band, "Priority P4")


def _severity_rank(value: Any) -> int:
    raw = str(value or "").upper()
    return {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
    }.get(raw, 0)


def _proposal_age_seconds(row: EvolutionProposal, *, now_ts: Optional[int] = None) -> int:
    now_ts = int(now_ts or time.time())
    base = int(getattr(row, "updated_at", 0) or getattr(row, "created_at", 0) or now_ts)
    return max(0, now_ts - base)


def _proposal_first_seen_age_seconds(row: EvolutionProposal, *, now_ts: Optional[int] = None) -> int:
    now_ts = int(now_ts or time.time())
    base = int(getattr(row, "first_detected_at", 0) or getattr(row, "created_at", 0) or now_ts)
    return max(0, now_ts - base)


def _sla_target_seconds_for(*, priority_score: int, recommendation: str, status: str, action: str = "") -> int:
    priority_score = int(priority_score or 0)
    recommendation = str(recommendation or "").lower()
    status = str(status or "").lower()
    action = str(action or "").lower()

    if status == "on_hold":
        return 48 * 3600
    if recommendation == "review_now" or priority_score >= 85:
        target = 30 * 60 if priority_score >= 90 else 2 * 3600
    elif recommendation == "review_soon" or priority_score >= 70:
        target = 6 * 3600
    elif recommendation == "observe_with_guard" or priority_score >= 45:
        target = 24 * 3600
    elif action == "ignore":
        target = 72 * 3600
    else:
        target = 48 * 3600

    if status == "approved":
        target = max(20 * 60, round(target * 0.75))
    return int(target)


def _sla_state_for(*, age_seconds: int, target_seconds: int) -> str:
    age_seconds = max(0, int(age_seconds or 0))
    target_seconds = max(1, int(target_seconds or 1))
    if age_seconds >= target_seconds:
        return "breached"
    if age_seconds >= int(target_seconds * 0.75):
        return "due_soon"
    return "on_track"


def _age_band_for(age_seconds: int) -> str:
    age_seconds = max(0, int(age_seconds or 0))
    if age_seconds >= 24 * 3600:
        return "aged_out"
    if age_seconds >= 6 * 3600:
        return "stale"
    if age_seconds >= 3600:
        return "warm"
    return "fresh"


def _queue_pressure_weight(*, priority_score: int, sla_state: str, age_seconds: int, execute_candidate: bool, operator_suggestion: str, status: str) -> int:
    score = max(0, min(100, int(priority_score or 0)))
    status = str(status or "").lower()
    if sla_state == "breached":
        score += 24
    elif sla_state == "due_soon":
        score += 12
    if age_seconds >= 24 * 3600:
        score += 10
    elif age_seconds >= 6 * 3600:
        score += 5
    if execute_candidate:
        score += 8
    if str(operator_suggestion or "").lower() == "approve_and_execute":
        score += 6
    elif str(operator_suggestion or "").lower() == "approve_only":
        score += 3
    if status == "on_hold":
        score = max(0, score - 10)
    return min(100, score)


def _capacity_hint_for(*, sla_state: str, backlog_weight: int, operator_suggestion: str) -> str:
    if sla_state == "breached" or backlog_weight >= 90:
        return "burst_now"
    if sla_state == "due_soon" or backlog_weight >= 70:
        return "clear_next"
    if str(operator_suggestion or "").lower() in {"approve_only", "approve_and_execute"}:
        return "steady_review"
    return "defer_observe"



DOMAIN_SLA_POLICY_SECONDS: Dict[str, Dict[str, int]] = {
    "security": {"critical": 15 * 60, "high": 30 * 60, "medium": 2 * 3600, "low": 6 * 3600},
    "auth": {"critical": 20 * 60, "high": 45 * 60, "medium": 2 * 3600, "low": 8 * 3600},
    "billing": {"critical": 30 * 60, "high": 60 * 60, "medium": 3 * 3600, "low": 8 * 3600},
    "realtime": {"critical": 30 * 60, "high": 90 * 60, "medium": 4 * 3600, "low": 12 * 3600},
    "schema": {"critical": 45 * 60, "high": 2 * 3600, "medium": 6 * 3600, "low": 18 * 3600},
    "runtime": {"critical": 30 * 60, "high": 2 * 3600, "medium": 6 * 3600, "low": 18 * 3600},
    "general": {"critical": 60 * 60, "high": 3 * 3600, "medium": 8 * 3600, "low": 24 * 3600},
}

def _severity_key_from_priority(priority_score: int) -> str:
    n = int(priority_score or 0)
    if n >= 85:
        return "critical"
    if n >= 70:
        return "high"
    if n >= 45:
        return "medium"
    return "low"

def _domain_sla_target_seconds(*, domain_scope: str, priority_score: int) -> int:
    scope = str(domain_scope or "general").lower()
    sev = _severity_key_from_priority(priority_score)
    policy = DOMAIN_SLA_POLICY_SECONDS.get(scope) or DOMAIN_SLA_POLICY_SECONDS.get("general") or {}
    target = int(policy.get(sev) or 24 * 3600)
    return max(10 * 60, target)

def _effective_sla_target_seconds(*, priority_score: int, recommendation: str, status: str, action: str = "", domain_scope: str = "general") -> int:
    base = _sla_target_seconds_for(
        priority_score=priority_score,
        recommendation=recommendation,
        status=status,
        action=action,
    )
    domain_target = _domain_sla_target_seconds(domain_scope=domain_scope, priority_score=priority_score)
    target = min(int(base or 0), int(domain_target or 0)) if base and domain_target else int(base or domain_target or 24 * 3600)
    if str(status or "").lower() == "on_hold":
        target = max(target, 24 * 3600)
    return max(10 * 60, int(target))

def _domain_sla_policy_payload() -> Dict[str, Dict[str, int]]:
    return {k: dict(v) for k, v in DOMAIN_SLA_POLICY_SECONDS.items()}

def _work_window_profile(*, backlog_pressure: str, backlog_pressure_score: int, overdue_count: int, due_soon_count: int, pending_queue_count: int, review_burst_size: int, review_window_seconds: int) -> Dict[str, Any]:
    pressure = str(backlog_pressure or "low").lower()
    window_seconds = int(review_window_seconds or 0)
    burst = int(review_burst_size or 0)
    pending = int(pending_queue_count or 0)
    overdue = int(overdue_count or 0)
    due_soon = int(due_soon_count or 0)
    if pressure == "critical":
        mode = "triage_intensive"
        lane = "protect_core_first"
        summary = "Foco total em triagem crítica, aprovando ou segurando o que ameaça núcleo e domínios sensíveis."
    elif pressure == "high":
        mode = "burst_review"
        lane = "close_overdue_first"
        summary = "Executar burst governado para limpar vencidos e estabilizar a fila antes de novas execuções amplas."
    elif pressure == "medium":
        mode = "steady_window"
        lane = "review_with_capacity"
        summary = "Manter janela contínua de revisão, com prioridade para due soon e execute candidates."
    else:
        mode = "light_observe"
        lane = "observe_and_prepare"
        summary = "Fila sob controle. Revisar por blocos curtos e manter observabilidade ativa."
    operator_slots = max(1, min(8, burst or 1))
    return {
        "mode": mode,
        "lane": lane,
        "summary": summary,
        "window_seconds": window_seconds,
        "window_minutes": round(window_seconds / 60) if window_seconds else 0,
        "review_burst_size": burst,
        "operator_slots": operator_slots,
        "pending_queue_count": pending,
        "overdue_count": overdue,
        "due_soon_count": due_soon,
        "backlog_pressure_score": int(backlog_pressure_score or 0),
        "recommended_start_with": "overdue" if overdue > 0 else ("due_soon" if due_soon > 0 else "execute_candidates"),
    }

def _daily_agenda_payload(*, top_items_serialized: list[Dict[str, Any]], work_window: Dict[str, Any], domain_buckets: Dict[str, int]) -> Dict[str, Any]:
    items = list(top_items_serialized or [])
    focus_items = []
    action_buckets: Dict[str, int] = {"approve_and_execute": 0, "approve_only": 0, "hold": 0, "reject": 0}
    domain_focus: Dict[str, int] = {}
    execute_now = 0
    for item in items[: max(1, int(work_window.get("review_burst_size") or 1))]:
        operator = ((item.get("operator_guidance") or {}).get("suggested_action") or "hold")
        action_buckets[operator] = action_buckets.get(operator, 0) + 1
        domain = item.get("domain_scope") or "general"
        domain_focus[domain] = domain_focus.get(domain, 0) + 1
        if operator == "approve_and_execute":
            execute_now += 1
        focus_items.append({
            "id": item.get("id"),
            "title": item.get("title") or item.get("code") or item.get("id"),
            "domain_scope": domain,
            "priority_score": int((item.get("scores") or {}).get("priority") or 0),
            "suggested_action": operator,
            "sla_state": ((item.get("sla") or {}).get("state") or "on_track"),
            "execute_candidate": bool(item.get("execute_candidate")),
        })
    dominant_domain = None
    if domain_focus:
        dominant_domain = sorted(domain_focus.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)[0][0]
    elif domain_buckets:
        dominant_domain = sorted(domain_buckets.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)[0][0]
    summary = "Agenda leve de observação."
    if execute_now > 0:
        summary = "Há proposals candidatas a approve + execute dentro da janela atual."
    elif action_buckets.get("approve_only", 0) > 0:
        summary = "Priorize aprovações governadas para destravar a fila antes de novas execuções."
    elif action_buckets.get("hold", 0) > 0:
        summary = "A agenda do dia pede contenção e revisão antes de mover a fila."
    return {
        "summary": summary,
        "dominant_domain": dominant_domain or "general",
        "focus_count": len(focus_items),
        "execute_now_count": execute_now,
        "action_buckets": action_buckets,
        "focus_items": focus_items,
    }



def _decision_payload_for_row(row: EvolutionProposal, db: Optional[Session] = None) -> Dict[str, Any]:
    decision = _json_loads(getattr(row, "decision_json", None)) or {}
    if not isinstance(decision, dict):
        decision = {"raw": decision}

    policy = SelfHealPolicy()
    learning = _execution_learning_summary(
        db,
        proposal_id=getattr(row, "id", None),
        action=getattr(row, "action", None),
        domain_scope=getattr(row, "domain_scope", None),
    )
    trust = _proposal_trust_envelope(row)
    semantic_summary = _proposal_semantic_summary(row=row, decision=decision)
    computed = policy.decide(
        severity=getattr(row, "severity", None),
        category=getattr(row, "category", None),
        code=getattr(row, "code", None),
        detected_count=getattr(row, "detected_count", 1),
        domain_scope=getattr(row, "domain_scope", None) or "general",
        recurrence_window_count=int(getattr(row, "recurrence_window_count", 1) or 1),
        blast_radius_accumulated=int(getattr(row, "blast_radius_accumulated", 0) or 0),
        security_accumulated=int(getattr(row, "security_accumulated", 0) or 0),
        trend_state=decision.get("trend_state") or "new",
        trend_delta=int(decision.get("trend_delta") or 0),
        signature_repeat_count=int(decision.get("signature_repeat_count") or getattr(row, "recurrence_window_count", 1) or 1),
        learning_success_rate=learning.get("success_rate"),
        learning_validation_rate=learning.get("validation_rate"),
        recent_failed_executions=int(learning.get("recent_failed_executions") or 0),
        rolled_back_count=int(learning.get("rolled_back_count") or 0),
        learning_confidence_adjustment=learning.get("confidence_adjustment"),
        source_trust_level=trust.get("source_trust_level") or "internal",
        instruction_authority=bool(trust.get("instruction_authority")),
        secret_exposure_risk=trust.get("secret_exposure_risk"),
        semantic_validation_summary=semantic_summary,
        required_review_domains=semantic_summary.get("required_review_domains") or [],
    ).to_dict()

    for field in (
        "reason",
        "action",
        "trend_state",
        "trend_delta",
        "signature_repeat_count",
    ):
        if decision.get(field) is not None:
            computed[field] = decision.get(field)
    computed["trust"] = trust
    computed["semantic_validation"] = semantic_summary
    return computed


def _sort_proposals(rows: list[EvolutionProposal], sort: str, db: Optional[Session] = None) -> list[EvolutionProposal]:
    mode = str(sort or "priority").strip().lower()
    now_ts = int(time.time())

    def _queue_tuple(r: EvolutionProposal) -> tuple[int, int, int, int]:
        decision = _decision_payload_for_row(r, db=db) or {}
        priority = int(decision.get("priority_score") or 0)
        recommendation = decision.get("recommendation") or "observe_with_guard"
        execute_candidate = bool(decision.get("admin_execute_candidate", False))
        operator_suggestion = decision.get("operator_suggestion") or "hold"
        age_seconds = _proposal_age_seconds(r, now_ts=now_ts)
        sla_target = _effective_sla_target_seconds(
            priority_score=priority,
            recommendation=recommendation,
            status=getattr(r, "status", None),
            action=getattr(r, "action", None),
            domain_scope=getattr(r, "domain_scope", None),
        )
        sla_state = _sla_state_for(age_seconds=age_seconds, target_seconds=sla_target)
        backlog_weight = _queue_pressure_weight(
            priority_score=priority,
            sla_state=sla_state,
            age_seconds=age_seconds,
            execute_candidate=execute_candidate,
            operator_suggestion=operator_suggestion,
            status=getattr(r, "status", None),
        )
        return (
            backlog_weight,
            priority,
            _severity_rank(getattr(r, "severity", None)),
            int(getattr(r, "updated_at", 0) or 0),
        )

    if mode == "recent":
        return sorted(rows, key=lambda r: (int(getattr(r, "updated_at", 0) or 0), int(getattr(r, "created_at", 0) or 0)), reverse=True)
    if mode == "severity":
        return sorted(
            rows,
            key=lambda r: (
                _severity_rank(getattr(r, "severity", None)),
                int(getattr(r, "updated_at", 0) or 0),
            ),
            reverse=True,
        )
    if mode == "sla":
        return sorted(
            rows,
            key=lambda r: (
                _queue_tuple(r)[0],
                _queue_tuple(r)[1],
                int(getattr(r, "updated_at", 0) or 0),
            ),
            reverse=True,
        )
    return sorted(rows, key=_queue_tuple, reverse=True)




def _execution_learning_summary(db: Optional[Session], *, proposal_id: Optional[str] = None, action: Optional[str] = None, domain_scope: Optional[str] = None) -> Dict[str, Any]:
    if db is None:
        return {
            "sample_size": 0,
            "success_rate": None,
            "validation_rate": None,
            "recent_failed_executions": 0,
            "rolled_back_count": 0,
            "last_completed_at": None,
            "confidence_adjustment": 0,
        }
    rows = db.execute(select(EvolutionExecution).order_by(EvolutionExecution.created_at.desc())).scalars().all()
    scoped: list[EvolutionExecution] = []
    for ex in rows:
        result = _json_loads(getattr(ex, "result_json", None)) or {}
        meta = result.get("proposal_meta") or {}
        if proposal_id and str(getattr(ex, "proposal_id", "") or "") == str(proposal_id):
            scoped.append(ex)
            continue
        if action and str(meta.get("action") or "").lower() != str(action or "").lower():
            continue
        if domain_scope and str(meta.get("domain_scope") or "general").lower() != str(domain_scope or "general").lower():
            continue
        if action or domain_scope:
            scoped.append(ex)
    if not scoped:
        return {
            "sample_size": 0,
            "success_rate": None,
            "validation_rate": None,
            "recent_failed_executions": 0,
            "rolled_back_count": 0,
            "last_completed_at": None,
            "confidence_adjustment": 0,
        }

    sample_size = len(scoped)
    completed = [r for r in scoped if str(getattr(r, "status", "") or "").lower() == "completed"]
    failed = [r for r in scoped if str(getattr(r, "status", "") or "").lower() == "failed"]
    rolled_back = [r for r in scoped if str(getattr(r, "status", "") or "").lower() in {"rolled_back"}]
    validated = []
    last_completed_at = None
    for r in completed:
        payload = _json_loads(getattr(r, "result_json", None)) or {}
        post = payload.get("post_validation") or {}
        validation = payload.get("validation") or {}
        if bool(post.get("ok")) or bool(validation.get("content_match")):
            validated.append(r)
        comp = getattr(r, "completed_at", None)
        if comp and (last_completed_at is None or int(comp) > int(last_completed_at)):
            last_completed_at = int(comp)
    success_rate = round((len(completed) / sample_size) * 100) if sample_size else None
    validation_rate = round((len(validated) / len(completed)) * 100) if completed else None
    recent_failed_executions = len(failed[:5])
    rolled_back_count = len(rolled_back)
    confidence_adjustment = 0
    if success_rate is not None:
        if success_rate >= 90:
            confidence_adjustment += 6
        elif success_rate >= 75:
            confidence_adjustment += 2
        elif success_rate < 50:
            confidence_adjustment -= 8
    if validation_rate is not None:
        if validation_rate >= 90:
            confidence_adjustment += 4
        elif validation_rate < 60:
            confidence_adjustment -= 6
    if recent_failed_executions >= 2:
        confidence_adjustment -= min(12, recent_failed_executions * 3)
    if rolled_back_count > 0:
        confidence_adjustment -= min(10, rolled_back_count * 2)
    return {
        "sample_size": sample_size,
        "success_rate": success_rate,
        "validation_rate": validation_rate,
        "recent_failed_executions": recent_failed_executions,
        "rolled_back_count": rolled_back_count,
        "last_completed_at": last_completed_at,
        "confidence_adjustment": confidence_adjustment,
    }


def _hard_gate_state_for(*, row: EvolutionProposal, decision: Dict[str, Any], learning: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    domain_scope = str(getattr(row, "domain_scope", None) or "general").lower()
    action = str(getattr(row, "action", None) or "").lower()
    security_score = int(decision.get("security_score") or 0)
    blast_radius_score = int(decision.get("blast_radius_score") or 0)
    priority_score = int(decision.get("priority_score") or 0)
    learning = learning or {}
    reasons: list[str] = []
    if domain_scope in {"security", "billing", "auth"}:
        reasons.append(f"sensitive_domain:{domain_scope}")
    if security_score >= 85:
        reasons.append("security_score_high")
    if blast_radius_score >= 92:
        reasons.append("blast_radius_critical")
    action_meta = SUPPORTED_EVOLUTION_ACTIONS.get(action) or {}
    if not bool(action_meta.get("execution_supported")):
        reasons.append(f"unsupported_action:{action or 'unknown'}")
    trust = _safe_dict(decision.get("trust"))
    reasons.extend(trust_gate_reasons(trust))
    semantic = _safe_dict(decision.get("semantic_validation"))
    if semantic.get("blocks_execution"):
        for domain in semantic.get("blocked_domains") or []:
            reasons.append(f"semantic_blocked:{domain}")
    for domain in semantic.get("required_review_domains") or []:
        reasons.append(f"semantic_review_required:{domain}")
    if int(learning.get("recent_failed_executions") or 0) >= 2:
        reasons.append("recent_failures")
    if int(learning.get("rolled_back_count") or 0) >= 1 and priority_score >= 70:
        reasons.append("rollback_history")
    active = bool(reasons)
    return {
        "active": active,
        "reasons": reasons,
        "override_allowed": active,
        "recommended_mode": "review_only" if active else ("approve_and_execute" if action == "propose_schema_patch" else "approve_only"),
    }


def _serialize_execution(row: EvolutionExecution) -> Dict[str, Any]:
    result = _json_loads(getattr(row, "result_json", None)) or {}
    post = result.get("post_validation") or {}
    validation = result.get("validation") or {}
    rollback = result.get("rollback") or {}
    proposal_meta = result.get("proposal_meta") or {}
    return {
        "id": row.id,
        "proposal_id": row.proposal_id,
        "org_slug": getattr(row, "org_slug", None),
        "status": getattr(row, "status", None),
        "mode": getattr(row, "mode", None),
        "actor_ref": getattr(row, "actor_ref", None),
        "trace_id": getattr(row, "trace_id", None),
        "result": result,
        "error_text": getattr(row, "error_text", None),
        "started_at": getattr(row, "started_at", None),
        "completed_at": getattr(row, "completed_at", None),
        "created_at": getattr(row, "created_at", None),
        "updated_at": getattr(row, "updated_at", None),
        "post_validation": post,
        "validation_summary": {
            "ok": bool(post.get("ok")),
            "branch_created": bool(post.get("branch_created")),
            "commit_created": bool(post.get("commit_created")),
            "pr_created": bool(post.get("pr_created")),
            "content_match": bool(validation.get("content_match")),
        },
        "rollback_supported": bool(rollback.get("supported")),
        "proposal_meta": proposal_meta,
    }


def _serialize_proposal(row: EvolutionProposal, db: Optional[Session] = None) -> Dict[str, Any]:
    decision = _decision_payload_for_row(row, db=db)
    learning = _execution_learning_summary(db, proposal_id=row.id, action=getattr(row, "action", None), domain_scope=getattr(row, "domain_scope", None))
    hard_gate = _hard_gate_state_for(row=row, decision=decision, learning=learning)
    scores = {
        "risk": int(decision.get("risk_score") or 0),
        "impact": int(decision.get("impact_score") or 0),
        "confidence": int(decision.get("confidence_score") or 0),
        "urgency": int(decision.get("urgency_score") or 0),
        "blast_radius": int(decision.get("blast_radius_score") or 0),
        "security": int(decision.get("security_score") or 0),
        "priority": int(decision.get("priority_score") or 0),
    }
    now_ts = int(time.time())
    cooldown_seconds = max(
        detection_touch_cooldown_seconds(),
        int(getattr(row, "last_cadence_seconds", 0) or 0),
    )
    recurrence_seconds = recurrence_window_seconds()
    last_detected_at = int(getattr(row, "last_detected_at", 0) or 0)
    cooldown_remaining = max(0, (last_detected_at + cooldown_seconds) - now_ts) if last_detected_at else 0
    admin_recommendation = decision.get("admin_recommendation") or "review_only"
    trend_state = decision.get("trend_state") or "new"
    trend_delta = int(decision.get("trend_delta") or 0)
    execute_candidate = bool(decision.get("admin_execute_candidate", False))
    operator_suggestion = decision.get("operator_suggestion") or "hold"
    age_seconds = _proposal_age_seconds(row, now_ts=now_ts)
    first_seen_age_seconds = _proposal_first_seen_age_seconds(row, now_ts=now_ts)
    sla_target_seconds = _effective_sla_target_seconds(
        priority_score=scores["priority"],
        recommendation=decision.get("recommendation") or "observe_with_guard",
        status=getattr(row, "status", None),
        action=getattr(row, "action", None),
        domain_scope=getattr(row, "domain_scope", None),
    )
    sla_state = _sla_state_for(age_seconds=age_seconds, target_seconds=sla_target_seconds)
    overdue_seconds = max(0, age_seconds - sla_target_seconds)
    backlog_weight = _queue_pressure_weight(
        priority_score=scores["priority"],
        sla_state=sla_state,
        age_seconds=age_seconds,
        execute_candidate=execute_candidate,
        operator_suggestion=operator_suggestion,
        status=getattr(row, "status", None),
    )
    return {
        "id": row.id,
        "org_slug": row.org_slug,
        "fingerprint": row.fingerprint,
        "code": row.code,
        "severity": row.severity,
        "category": row.category,
        "source": row.source,
        "action": row.action,
        "status": row.status,
        "title": row.title,
        "summary": row.summary,
        "finding": _json_loads(getattr(row, "finding_json", None)),
        "issue": _json_loads(getattr(row, "issue_json", None)),
        "decision": decision,
        "trust": _safe_dict(decision.get("trust")),
        "semantic_validation": _safe_dict(decision.get("semantic_validation")),
        "policy": {
            "version": decision.get("policy_version") or POLICY_VERSION,
            "lane": decision.get("lane"),
            "owner_review_required": bool(decision.get("owner_review_required", row.action != "ignore")),
            "execution_allowed": bool(decision.get("execution_allowed", row.action in {"propose_schema_patch", "pr_only"})),
            "reason": decision.get("reason"),
            "suppression_hint": decision.get("suppression_hint") or "none",
        },
        "scores": scores,
        "priority_label": _priority_label(scores["priority"]),
        "priority_band": _score_band(scores["priority"]),
        "risk_band": _score_band(scores["risk"]),
        "impact_band": _score_band(scores["impact"]),
        "blast_radius_band": _score_band(scores["blast_radius"]),
        "security_band": _score_band(scores["security"]),
        "recommendation": decision.get("recommendation") or "observe_with_guard",
        "admin_recommendation": admin_recommendation,
        "execute_candidate": execute_candidate,
        "operator_guidance": {
            "suggested_action": decision.get("operator_suggestion") or "hold",
            "confidence_score": int(decision.get("operator_confidence_score") or 0),
            "rationale": decision.get("operator_rationale") or decision.get("reason") or "",
        },
        "trend": {
            "state": trend_state,
            "delta": trend_delta,
        },
        "domain_scope": getattr(row, "domain_scope", None),
        "recurrence": {
            "window_seconds": recurrence_seconds,
            "window_count": int(getattr(row, "recurrence_window_count", 1) or 1),
            "signature_repeat_count": int(decision.get("signature_repeat_count") or getattr(row, "recurrence_window_count", 1) or 1),
        },
        "accumulated": {
            "blast_radius": int(getattr(row, "blast_radius_accumulated", 0) or 0),
            "security": int(getattr(row, "security_accumulated", 0) or 0),
        },
        "cadence": {
            "seconds": int(getattr(row, "last_cadence_seconds", 0) or 0),
        },
        "age": {
            "open_seconds": age_seconds,
            "first_seen_seconds": first_seen_age_seconds,
            "band": _age_band_for(age_seconds),
        },
        "sla": {
            "target_seconds": sla_target_seconds,
            "state": sla_state,
            "overdue_seconds": overdue_seconds,
            "due_at": int(getattr(row, "updated_at", 0) or 0) + sla_target_seconds if int(getattr(row, "updated_at", 0) or 0) else None,
            "domain_scope": getattr(row, "domain_scope", None) or "general",
            "domain_target_seconds": _domain_sla_target_seconds(
                domain_scope=getattr(row, "domain_scope", None),
                priority_score=scores["priority"],
            ),
            "policy_rule": _severity_key_from_priority(scores["priority"]),
        },
        "backlog": {
            "weight_score": backlog_weight,
            "capacity_hint": _capacity_hint_for(
                sla_state=sla_state,
                backlog_weight=backlog_weight,
                operator_suggestion=operator_suggestion,
            ),
            "work_window_candidate": "today" if backlog_weight >= 70 or sla_state in {"breached", "due_soon"} else "later",
        },
        "learning": learning,
        "hard_gate": hard_gate,
        "cooldown": {
            "seconds": cooldown_seconds,
            "remaining_seconds": cooldown_remaining,
            "active": bool(cooldown_remaining > 0),
        },
        "approval_note": getattr(row, "approval_note", None),
        "rejection_note": getattr(row, "rejection_note", None),
        "first_detected_at": row.first_detected_at,
        "last_detected_at": row.last_detected_at,
        "detected_count": row.detected_count,
        "approved_by": getattr(row, "approved_by", None),
        "approved_at": getattr(row, "approved_at", None),
        "rejected_by": getattr(row, "rejected_by", None),
        "rejected_at": getattr(row, "rejected_at", None),
        "last_trace_id": getattr(row, "last_trace_id", None),
        "last_execution_status": getattr(row, "last_execution_status", None),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _serialize_signal_snapshot(row: EvolutionSignalSnapshot) -> Dict[str, Any]:
    payload = _json_loads(getattr(row, "payload_json", None)) or {}
    decision = payload.get("decision") if isinstance(payload, dict) else {}
    signature_profile = payload.get("signature_profile") if isinstance(payload, dict) else {}
    return {
        "id": row.id,
        "proposal_id": row.proposal_id,
        "fingerprint": row.fingerprint,
        "code": row.code,
        "category": row.category,
        "domain_scope": getattr(row, "domain_scope", None),
        "recurrence_window_count": int(getattr(row, "recurrence_window_count", 1) or 1),
        "blast_radius_score": int(getattr(row, "blast_radius_score", 0) or 0),
        "security_score": int(getattr(row, "security_score", 0) or 0),
        "priority_score": int(getattr(row, "priority_score", 0) or 0),
        "recommendation": getattr(row, "recommendation", None),
        "admin_recommendation": (decision or {}).get("admin_recommendation"),
        "operator_suggestion": (decision or {}).get("operator_suggestion") or "hold",
        "operator_confidence_score": int((decision or {}).get("operator_confidence_score") or 0),
        "trend_state": (decision or {}).get("trend_state"),
        "trend_delta": int((decision or {}).get("trend_delta") or 0),
        "execute_candidate": bool((decision or {}).get("admin_execute_candidate", False)),
        "signature_profile": signature_profile or {},
        "cadence_seconds": int(getattr(row, "cadence_seconds", 0) or 0),
        "policy_version": getattr(row, "policy_version", None),
        "trace_id": getattr(row, "trace_id", None),
        "payload": payload,
        "created_at": row.created_at,
    }


def _serialize_cycle_log(row: EvolutionCycleLog) -> Dict[str, Any]:
    return {
        "id": row.id,
        "org_slug": row.org_slug,
        "trace_id": getattr(row, "trace_id", None),
        "findings": int(getattr(row, "findings", 0) or 0),
        "classified": int(getattr(row, "classified", 0) or 0),
        "proposals_touched": int(getattr(row, "proposals_touched", 0) or 0),
        "proposals_created": int(getattr(row, "proposals_created", 0) or 0),
        "proposals_suppressed": int(getattr(row, "proposals_suppressed", 0) or 0),
        "max_priority_score": int(getattr(row, "max_priority_score", 0) or 0),
        "avg_priority_score": int(getattr(row, "avg_priority_score", 0) or 0),
        "next_interval_suggested_seconds": int(getattr(row, "next_interval_suggested_seconds", 0) or 0),
        "recommendation_buckets": _json_loads(getattr(row, "recommendation_buckets_json", None)) or {},
        "domain_buckets": _json_loads(getattr(row, "domain_buckets_json", None)) or {},
        "top_queue": _json_loads(getattr(row, "top_queue_json", None)) or [],
        "policy_version": getattr(row, "policy_version", None),
        "created_at": row.created_at,
    }


def _require_master_admin_access(
    authorization: Optional[str] = Header(default=None),
    x_admin_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    master_key = _master_admin_key()
    if x_admin_key and master_key and x_admin_key == master_key:
        return {"role": "master_admin", "via": "x_admin_key"}

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Master admin required")

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

    role = str(payload.get("role", "") or "").strip().lower()
    email = str(payload.get("email", "") or "").strip().lower()
    if role not in {"admin", "owner", "superadmin"}:
        raise HTTPException(status_code=403, detail="Master admin role required")
    allowed = set(_master_admin_emails())
    if allowed and email not in allowed:
        raise HTTPException(status_code=403, detail="Master admin email required")
    return payload


class EvolutionClassifyIn(BaseModel):
    error_text: str = Field(min_length=3, max_length=20000)


class EvolutionProposeIn(BaseModel):
    error_text: str = Field(min_length=3, max_length=20000)
    path: str = Field(default="app/db.py", min_length=1, max_length=300)
    source_branch: Optional[str] = Field(default=None, max_length=120)
    auto_pr: bool = Field(default=True)
    pr_title: Optional[str] = Field(default=None, max_length=200)
    pr_body: Optional[str] = Field(default=None, max_length=20000)


class EvolutionDecisionIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=4000)
    execute_now: bool = Field(default=False)
    source_branch: Optional[str] = Field(default=None, max_length=120)
    auto_pr: bool = Field(default=True)
    path: str = Field(default="app/db.py", min_length=1, max_length=300)
    validate_after_commit: bool = Field(default=True)
    override_hard_gate: bool = Field(default=False)


class EvolutionExecuteIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=4000)
    source_branch: Optional[str] = Field(default=None, max_length=120)
    auto_pr: bool = Field(default=True)
    path: str = Field(default="app/db.py", min_length=1, max_length=300)
    validate_after_commit: bool = Field(default=True)
    override_hard_gate: bool = Field(default=False)


class EvolutionBatchPlanIn(BaseModel):
    limit: int = Field(default=5, ge=1, le=25)
    confidence_min: int = Field(default=75, ge=0, le=100)
    include_statuses: list[str] = Field(default_factory=lambda: ["awaiting_master_approval", "approved"])
    allow_sensitive_domains: bool = Field(default=False)


class EvolutionBatchExecuteIn(EvolutionBatchPlanIn):
    note: Optional[str] = Field(default=None, max_length=4000)
    auto_pr: bool = Field(default=True)
    path: str = Field(default="app/db.py", min_length=1, max_length=300)
    validate_after_commit: bool = Field(default=True)
    override_hard_gate: bool = Field(default=False)




def _schema_error_text_for_proposal(row: EvolutionProposal) -> Optional[str]:
    issue = _json_loads(getattr(row, "issue_json", None)) or {}
    details = issue.get("details") or {}
    code = str(issue.get("code") or row.code or "").upper()
    table = str(details.get("table") or "").strip()
    column = str(details.get("column") or "").strip()

    if code == "SCHEMA_MISSING_TABLE" and table:
        return f'relation "{table}" does not exist'

    if code == "SCHEMA_MISSING_COLUMN" and table and column:
        return f'column "{column}" of relation "{table}" does not exist'

    return None


def _safe_proposal_branch_name(row: EvolutionProposal, suffix: str = "") -> str:
    stamp = int(time.time())
    base = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "-"
        for ch in (suffix or row.code or "proposal").lower()
    ).strip("-") or "proposal"
    return f"selfheal/proposal-{row.id[:10]}-{base}-{stamp}"


def _validate_branch_file(*, branch_name: str, path: str, expected_content: str) -> Dict[str, Any]:
    fetched = _request("GET", f"/api/internal/git/file?path={path}&branch={branch_name}")
    branch_content = fetched.get("content", "")
    if not isinstance(branch_content, str):
        branch_content = ""
    expected_hash = hashlib.sha256(expected_content.encode("utf-8")).hexdigest()
    actual_hash = hashlib.sha256(branch_content.encode("utf-8")).hexdigest()
    return {
        "path": path,
        "branch": branch_name,
        "hash_expected": expected_hash,
        "hash_actual": actual_hash,
        "content_match": expected_hash == actual_hash,
        "marker_present": "_reconcile_self_heal_schema_boot" in branch_content,
    }


SUPPORTED_EVOLUTION_ACTIONS: Dict[str, Dict[str, Any]] = {
    "propose_schema_patch": {
        "approval_required": True,
        "execution_supported": True,
        "execution_mode": "safe_pr",
        "rollback_supported": True,
        "operator_bias": "approve_and_execute",
        "operator_confidence_base": 92,
        "notes": "Generates a guarded branch/commit/PR to reconcile known schema drift.",
    },
    "pr_only": {
        "approval_required": True,
        "execution_supported": True,
        "execution_mode": "safe_pr",
        "rollback_supported": True,
        "operator_bias": "approve_only",
        "operator_confidence_base": 74,
        "notes": "Creates a governed proposal artifact PR for human-reviewed follow-up work.",
    },
    "simulate": {
        "approval_required": True,
        "execution_supported": False,
        "execution_mode": "manual",
        "rollback_supported": False,
        "operator_bias": "hold",
        "operator_confidence_base": 48,
        "notes": "Simulation-only finding; no automatic code execution.",
    },
    "ignore": {
        "approval_required": False,
        "execution_supported": False,
        "execution_mode": "none",
        "rollback_supported": False,
        "operator_bias": "reject",
        "operator_confidence_base": 35,
        "notes": "Informational finding only.",
    },
}


def _request_optional(method: str, path: str, *, json_body: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    url = f"{_base_url()}{path}"
    try:
        resp = requests.request(method, url, json=json_body, headers=_internal_admin_headers(), timeout=30)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"internal request failed: {e}") from e

    if resp.status_code == 404:
        return None

    try:
        detail: Any = resp.json()
    except Exception:
        detail = {"raw": resp.text}

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=detail)

    if isinstance(detail, dict):
        return detail
    return {"data": detail}


def _proposal_artifact_path(row: EvolutionProposal) -> str:
    return f"docs/evolution/proposals/{row.id}.md"


def _build_proposal_markdown(row: EvolutionProposal) -> str:
    issue = _json_loads(getattr(row, "issue_json", None)) or {}
    decision = _json_loads(getattr(row, "decision_json", None)) or {}
    finding = _json_loads(getattr(row, "finding_json", None)) or {}
    sections = [
        f"# Governed Evolution Proposal `{row.id}`",
        "",
        f"- status: `{row.status}`",
        f"- action: `{row.action}`",
        f"- code: `{row.code}`",
        f"- severity: `{row.severity}`",
        f"- category: `{row.category}`",
        f"- source: `{row.source}`",
        f"- fingerprint: `{row.fingerprint}`",
        f"- detected_count: `{row.detected_count}`",
        f"- first_detected_at: `{row.first_detected_at}`",
        f"- last_detected_at: `{row.last_detected_at}`",
        "",
        "## Summary",
        "",
        row.summary or "_no summary_",
        "",
        "## Issue",
        "",
        "```json",
        json.dumps(issue, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Decision",
        "",
        "```json",
        json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Finding",
        "",
        "```json",
        json.dumps(finding, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "_Generated by governed evolution. Merge still requires explicit review._",
        "",
    ]
    return "\n".join(sections)


def _execute_pr_only_proposal(
    *,
    row: EvolutionProposal,
    payload: EvolutionExecuteIn,
) -> Dict[str, Any]:
    source_branch = payload.source_branch or _default_branch()
    branch_name = _safe_proposal_branch_name(row, suffix="pr-only")
    if is_protected_branch(branch_name) or not is_branch_allowed(branch_name):
        raise HTTPException(status_code=422, detail={"reason": "unsafe_target_branch", "branch": branch_name})
    scoped_credentials = resolve_scoped_credentials(branch=branch_name)
    artifact_path = _proposal_artifact_path(row)
    current_file = _request_optional(
        "GET",
        f"/api/internal/git/file?path={artifact_path}&branch={source_branch}",
    )
    previous_content = ""
    if current_file and isinstance(current_file.get("content"), str):
        previous_content = current_file.get("content", "")

    artifact_content = _build_proposal_markdown(row)

    branch_resp = _request(
        "POST",
        "/api/internal/git/branch",
        json_body={
            "branch_name": branch_name,
            "source_branch": source_branch,
        },
    )
    commit_message = f"docs(self-heal): governed proposal artifact {row.id}"
    commit_resp = _request(
        "POST",
        "/api/internal/git/commit",
        json_body={
            "path": artifact_path,
            "content": artifact_content,
            "message": commit_message,
            "branch": branch_name,
        },
    )

    validation = None
    if payload.validate_after_commit:
        validation = _validate_branch_file(
            branch_name=branch_name,
            path=artifact_path,
            expected_content=artifact_content,
        )

    pr_resp = None
    if payload.auto_pr:
        pr_resp = _request(
            "POST",
            "/api/internal/git/pr",
            json_body={
                "title": f"Governed evolution: review proposal `{row.code}`",
                "body": (
                    f"Governed PR-only execution for approved proposal `{row.id}`.\n\n"
                    f"- action: `{row.action}`\n"
                    f"- code: `{row.code}`\n"
                    f"- severity: `{row.severity}`\n"
                    f"- artifact: `{artifact_path}`\n\n"
                    f"This PR carries the proposal artifact for human-reviewed follow-up work."
                ),
                "head": branch_name,
                "base": source_branch,
            },
        )

    return {
        "ok": True,
        "mode": "safe_pr",
        "proposal_id": row.id,
        "action": "pr_only",
        "branch": branch_resp,
        "commit": commit_resp,
        "pr": pr_resp,
        "validation": validation,
        "artifact_path": artifact_path,
        "source_branch": source_branch,
        "rollback": {
            "supported": True,
            "reason": "artifact_pr_only",
            "path": artifact_path,
            "source_branch": source_branch,
            "original_content": previous_content,
            "previous_content_present": bool(current_file and isinstance(current_file.get("content"), str)),
        },
        "credential_scope": scoped_credentials,
    }


def _execute_rollback_for_execution(
    *,
    row: EvolutionProposal,
    execution: EvolutionExecution,
    payload: EvolutionExecuteIn,
) -> Dict[str, Any]:
    result = _json_loads(getattr(execution, "result_json", None)) or {}
    rollback = result.get("rollback") or {}
    if not rollback or not rollback.get("supported"):
        raise HTTPException(
            status_code=422,
            detail={
                "reason": "rollback_not_supported_for_execution",
                "execution_id": execution.id,
                "proposal_id": row.id,
            },
        )

    path = str(rollback.get("path") or "").strip()
    original_content = rollback.get("original_content")
    source_branch = str(payload.source_branch or rollback.get("source_branch") or _default_branch()).strip() or _default_branch()
    if not path or original_content is None:
        raise HTTPException(status_code=422, detail="rollback_context_incomplete")

    branch_name = _safe_proposal_branch_name(row, suffix="rollback")
    branch_resp = _request(
        "POST",
        "/api/internal/git/branch",
        json_body={
            "branch_name": branch_name,
            "source_branch": source_branch,
        },
    )
    commit_resp = _request(
        "POST",
        "/api/internal/git/commit",
        json_body={
            "path": path,
            "content": str(original_content),
            "message": f"revert(self-heal): rollback proposal {row.id} execution {execution.id}",
            "branch": branch_name,
        },
    )

    validation = None
    if payload.validate_after_commit:
        validation = _validate_branch_file(
            branch_name=branch_name,
            path=path,
            expected_content=str(original_content),
        )

    pr_resp = None
    if payload.auto_pr:
        pr_resp = _request(
            "POST",
            "/api/internal/git/pr",
            json_body={
                "title": f"Governed rollback: proposal `{row.id}`",
                "body": (
                    f"Rollback generated for execution `{execution.id}` of proposal `{row.id}`.\n\n"
                    f"- restored path: `{path}`\n"
                    f"- source branch: `{source_branch}`\n"
                    f"- original execution mode: `{execution.mode}`\n\n"
                    f"Review required before merge."
                ),
                "head": branch_name,
                "base": source_branch,
            },
        )

    return {
        "ok": True,
        "mode": "rollback_safe_pr",
        "proposal_id": row.id,
        "rolled_back_execution_id": execution.id,
        "branch": branch_resp,
        "commit": commit_resp,
        "pr": pr_resp,
        "validation": validation,
        "path": path,
        "source_branch": source_branch,
    }


def _execute_schema_patch_proposal(
    *,
    row: EvolutionProposal,
    payload: EvolutionExecuteIn,
) -> Dict[str, Any]:
    error_text = _schema_error_text_for_proposal(row)
    if not error_text:
        raise HTTPException(status_code=422, detail="proposal_execution_schema_context_missing")

    result = classify_and_patch(error_text)
    if result.get("action") != "create_table_patch":
        raise HTTPException(
            status_code=422,
            detail={
                "reason": "proposal_execution_not_supported",
                "classification": result,
            },
        )

    table_name = result["table"]
    sql_patch = result["sql"]
    source_branch = payload.source_branch or _default_branch()
    branch_name = _safe_proposal_branch_name(row, suffix=table_name)
    if is_protected_branch(branch_name) or not is_branch_allowed(branch_name):
        raise HTTPException(status_code=422, detail={"reason": "unsafe_target_branch", "branch": branch_name})
    scoped_credentials = resolve_scoped_credentials(branch=branch_name)

    current_file = _request(
        "GET",
        f"/api/internal/git/file?path={payload.path}&branch={source_branch}",
    )
    current_content = current_file.get("content", "")
    if not isinstance(current_content, str):
        raise HTTPException(status_code=500, detail="git file content missing")

    patched_content = _build_db_patch(current_content, sql_patch, table_name)
    patch_hash = hashlib.sha256((payload.path + sql_patch + row.id).encode("utf-8")).hexdigest()[:12]

    branch_resp = _request(
        "POST",
        "/api/internal/git/branch",
        json_body={
            "branch_name": branch_name,
            "source_branch": source_branch,
        },
    )

    commit_message = f"fix(self-heal): governed evolution reconcile {table_name} [{patch_hash}]"
    commit_resp = _request(
        "POST",
        "/api/internal/git/commit",
        json_body={
            "path": payload.path,
            "content": patched_content,
            "message": commit_message,
            "branch": branch_name,
        },
    )

    validation = None
    if payload.validate_after_commit:
        validation = _validate_branch_file(
            branch_name=branch_name,
            path=payload.path,
            expected_content=patched_content,
        )

    pr_resp = None
    if payload.auto_pr:
        pr_title = f"Governed evolution: reconcile missing table `{table_name}`"
        pr_body = (
            f"Governed evolution execution for approved proposal `{row.id}`.\n\n"
            f"- action: `create_table_patch`\n"
            f"- table: `{table_name}`\n"
            f"- path: `{payload.path}`\n"
            f"- source branch: `{source_branch}`\n"
            f"- generated from approved proposal\n\n"
            f"Master approval already granted. Merge still requires review."
        )
        pr_resp = _request(
            "POST",
            "/api/internal/git/pr",
            json_body={
                "title": pr_title,
                "body": pr_body,
                "head": branch_name,
                "base": source_branch,
            },
        )

    return {
        "ok": True,
        "mode": "safe_pr",
        "proposal_id": row.id,
        "action": "propose_schema_patch",
        "classification": result,
        "branch": branch_resp,
        "commit": commit_resp,
        "pr": pr_resp,
        "validation": validation,
        "patch_hash": patch_hash,
        "path": payload.path,
        "source_branch": source_branch,
        "rollback": {
            "supported": True,
            "path": payload.path,
            "source_branch": source_branch,
            "original_content": current_content,
            "table": table_name,
        },
    }



def _post_validate_execution_result(*, row: EvolutionProposal, result: Dict[str, Any], payload: EvolutionExecuteIn) -> Dict[str, Any]:
    action = str(result.get("action") or getattr(row, "action", None) or "").lower()
    validation = _safe_dict(result.get("validation"))
    branch = _safe_dict(result.get("branch"))
    commit = _safe_dict(result.get("commit"))
    rollback = _safe_dict(result.get("rollback"))
    pr = result.get("pr") or {}
    target_branch = str(branch.get("new_branch") or branch.get("branch") or "").strip()
    semantic_summary = _proposal_semantic_summary(row=row, payload=payload, result=result)
    semantic_results = semantic_summary.get("results") or []
    rollback_required = bool(any(bool(item.get("rollback_required")) for item in semantic_results))
    rollback_ready = bool(rollback.get("supported"))
    post_ctx = SemanticValidationContext(
        action=action,
        domain_scope=str(getattr(row, "domain_scope", None) or "general"),
        proposal_id=str(getattr(row, "id", None) or ""),
        target_branch=target_branch or None,
        source_branch=(getattr(payload, "source_branch", None) if payload is not None else None),
        changed_paths=[str(x) for x in [result.get("artifact_path"), result.get("path"), getattr(payload, "path", None)] if str(x or "").strip()],
        trust=_proposal_trust_envelope(row),
        validation=validation,
        rollback=rollback,
        result=result,
        proposal={"id": getattr(row, "id", None), "code": getattr(row, "code", None), "status": getattr(row, "status", None)},
    )
    semantic_integrity = run_post_execution_semantic_integrity(post_ctx)
    checks = {
        "branch_created": bool(branch),
        "commit_created": bool(commit),
        "pr_created": (pr is not None) if payload.auto_pr else True,
        "content_match": bool(validation.get("content_match")) if payload.validate_after_commit else True,
        "marker_present": bool(validation.get("marker_present")) if action == "propose_schema_patch" and payload.validate_after_commit else True,
        "target_branch_allowed": bool(is_branch_allowed(target_branch)) if target_branch else True,
        "target_branch_not_protected": (not is_protected_branch(target_branch)) if target_branch else True,
        "rollback_ready": (rollback_ready if rollback_required else True),
        "semantic_integrity_ok": bool(semantic_integrity.get("ok", True)),
    }
    ok = all(bool(v) for v in checks.values()) and bool(semantic_summary.get("ok", True)) and bool(semantic_integrity.get("ok", True))
    return {
        "ok": ok,
        "checks": checks,
        "action": action,
        "validated_at": int(time.time()),
        "semantic_validation": semantic_summary,
        "semantic_integrity": semantic_integrity,
        "target_branch": target_branch or None,
        "credential_scope": resolve_scoped_credentials(branch=target_branch or None),
        "rollback_required": rollback_required,
        "rollback_ready": rollback_ready,
    }


def _finalize_execution_result(*, row: EvolutionProposal, result: Dict[str, Any], payload: EvolutionExecuteIn, db: Optional[Session] = None) -> Dict[str, Any]:
    enriched = dict(result or {})
    enriched["proposal_meta"] = {
        "proposal_id": row.id,
        "action": getattr(row, "action", None),
        "domain_scope": getattr(row, "domain_scope", None) or "general",
        "code": getattr(row, "code", None),
        "trust": _proposal_trust_envelope(row),
    }
    enriched["post_validation"] = _post_validate_execution_result(row=row, result=enriched, payload=payload)
    enriched["learning_after"] = _execution_learning_summary(db, proposal_id=row.id, action=getattr(row, "action", None), domain_scope=getattr(row, "domain_scope", None))
    return enriched


def _assert_execution_allowed(*, row: EvolutionProposal, payload: EvolutionExecuteIn, db: Optional[Session] = None) -> Dict[str, Any]:
    serialized = _serialize_proposal(row, db=db)
    hard_gate = serialized.get("hard_gate") or {}
    if hard_gate.get("active") and not payload.override_hard_gate:
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "hard_gate_requires_master_override",
                "proposal_id": row.id,
                "hard_gate": hard_gate,
            },
        )
    semantic = _safe_dict(serialized.get("semantic_validation") or {})
    semantic_results = semantic.get("results") or []
    rollback_required = bool(any(bool(item.get("rollback_required")) for item in semantic_results))
    rollback_supported = False
    for item in semantic_results:
        reasons = [str(x or "") for x in (item.get("reasons") or [])]
        if "rollback_required_for_execution_action" in reasons:
            rollback_supported = True
            break
    if rollback_required and not rollback_supported:
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "rollback_pair_required_before_execution",
                "proposal_id": row.id,
                "semantic_validation": semantic,
            },
        )
    return serialized


def _batch_candidates(*, rows: list[EvolutionProposal], db: Optional[Session], limit: int, confidence_min: int, include_statuses: list[str], allow_sensitive_domains: bool) -> list[Dict[str, Any]]:
    allowed_statuses = {str(x or "").lower() for x in include_statuses or []}
    items = []
    for row in rows:
        if allowed_statuses and str(getattr(row, "status", "") or "").lower() not in allowed_statuses:
            continue
        item = _serialize_proposal(row, db=db)
        hard_gate = item.get("hard_gate") or {}
        learning = item.get("learning") or {}
        operator = item.get("operator_guidance") or {}
        domain_scope = str(item.get("domain_scope") or "general").lower()
        action_meta = SUPPORTED_EVOLUTION_ACTIONS.get(str(item.get("action") or "").lower()) or {}
        semantic = _safe_dict(item.get("semantic_validation") or (item.get("decision") or {}).get("semantic_validation"))
        eligible = (
            bool(action_meta.get("execution_supported"))
            and int(operator.get("confidence_score") or 0) >= int(confidence_min or 0)
            and (not hard_gate.get("active"))
            and not bool(semantic.get("blocks_execution"))
        )
        if not allow_sensitive_domains and domain_scope in {"security", "billing", "auth"}:
            eligible = False
        items.append({
            "proposal": item,
            "eligible": bool(eligible),
            "reasons": ([] if eligible else (hard_gate.get("reasons") or ["below_confidence_or_policy_gate"])),
            "learning": learning,
        })
    items.sort(key=lambda x: (
        int(((x.get("proposal") or {}).get("backlog") or {}).get("weight_score") or 0),
        int(((x.get("proposal") or {}).get("scores") or {}).get("priority") or 0),
        int(((x.get("proposal") or {}).get("operator_guidance") or {}).get("confidence_score") or 0),
    ), reverse=True)
    return items[:limit]


def _execute_approved_proposal(
    *,
    row: EvolutionProposal,
    payload: EvolutionExecuteIn,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    _assert_execution_allowed(row=row, payload=payload, db=db)
    action = str(getattr(row, "action", "") or "").strip().lower()
    if action == "propose_schema_patch":
        return _finalize_execution_result(row=row, result=_execute_schema_patch_proposal(row=row, payload=payload), payload=payload, db=db)
    if action == "pr_only":
        return _finalize_execution_result(row=row, result=_execute_pr_only_proposal(row=row, payload=payload), payload=payload, db=db)
    if action == "simulate":
        return _finalize_execution_result(row=row, result=_execute_pr_only_proposal(row=row, payload=payload), payload=payload, db=db)
    raise HTTPException(
        status_code=422,
        detail={
            "reason": "proposal_action_requires_manual_execution",
            "action": action,
            "supported_actions": sorted(k for k, v in SUPPORTED_EVOLUTION_ACTIONS.items() if v.get("execution_supported")),
        },
    )


@router.get("/health")
def evolution_health(_admin=Depends(_require_master_admin_access), db: Session = Depends(get_db)):
    rows = db.execute(select(EvolutionProposal)).scalars().all()
    pending = [r for r in rows if getattr(r, "status", None) == "awaiting_master_approval"]
    approved = [r for r in rows if getattr(r, "status", None) == "approved"]
    on_hold = [r for r in rows if getattr(r, "status", None) == "on_hold"]
    executed = [r for r in rows if getattr(r, "status", None) == "executed"]
    scored = [_serialize_proposal(r, db=db) for r in rows]
    priority_buckets = {"critical": 0, "high": 0, "medium": 0, "low": 0, "none": 0}
    lane_buckets = {}
    action_buckets = {}
    recommendation_buckets = {}
    admin_recommendation_buckets = {}
    operator_suggestion_buckets = {}
    trend_buckets = {}
    domain_buckets = {}
    sla_buckets = {"breached": 0, "due_soon": 0, "on_track": 0}
    age_buckets = {"fresh": 0, "warm": 0, "stale": 0, "aged_out": 0}
    capacity_hint_buckets = {}
    execute_candidates = 0
    avg_priority = 0
    avg_recurrence = 0
    avg_operator_confidence = 0
    avg_backlog_weight = 0

    if scored:
        avg_priority = round(sum(int((item.get("scores") or {}).get("priority") or 0) for item in scored) / len(scored))
        avg_recurrence = round(sum(int((item.get("recurrence") or {}).get("window_count") or 0) for item in scored) / len(scored), 1)
        avg_operator_confidence = round(sum(int((item.get("operator_guidance") or {}).get("confidence_score") or 0) for item in scored) / len(scored))
        avg_backlog_weight = round(sum(int((item.get("backlog") or {}).get("weight_score") or 0) for item in scored) / len(scored))

    for item in scored:
        priority_buckets[item.get("priority_band") or "none"] = priority_buckets.get(item.get("priority_band") or "none", 0) + 1
        lane = ((item.get("policy") or {}).get("lane") or "unknown")
        lane_buckets[lane] = lane_buckets.get(lane, 0) + 1
        action = item.get("action") or "unknown"
        action_buckets[action] = action_buckets.get(action, 0) + 1
        recommendation = item.get("recommendation") or "unknown"
        recommendation_buckets[recommendation] = recommendation_buckets.get(recommendation, 0) + 1
        admin_rec = item.get("admin_recommendation") or "review_only"
        admin_recommendation_buckets[admin_rec] = admin_recommendation_buckets.get(admin_rec, 0) + 1
        operator_suggestion = ((item.get("operator_guidance") or {}).get("suggested_action") or "hold")
        operator_suggestion_buckets[operator_suggestion] = operator_suggestion_buckets.get(operator_suggestion, 0) + 1
        trend_state = ((item.get("trend") or {}).get("state") or "unknown")
        trend_buckets[trend_state] = trend_buckets.get(trend_state, 0) + 1
        domain_scope = item.get("domain_scope") or "general"
        domain_buckets[domain_scope] = domain_buckets.get(domain_scope, 0) + 1
        sla_state = ((item.get("sla") or {}).get("state") or "on_track")
        sla_buckets[sla_state] = sla_buckets.get(sla_state, 0) + 1
        age_band = ((item.get("age") or {}).get("band") or "fresh")
        age_buckets[age_band] = age_buckets.get(age_band, 0) + 1
        capacity_hint = ((item.get("backlog") or {}).get("capacity_hint") or "defer_observe")
        capacity_hint_buckets[capacity_hint] = capacity_hint_buckets.get(capacity_hint, 0) + 1
        if item.get("execute_candidate"):
            execute_candidates += 1

    queue_rows = [r for r in rows if str(getattr(r, "status", "") or "").lower() in {"awaiting_master_approval", "approved"}]
    queue_items = _sort_proposals(queue_rows or rows, "priority", db=db)
    top_items = queue_items[:5]
    top_items_serialized = [_serialize_proposal(r, db=db) for r in top_items]

    overdue_count = sum(1 for item in top_items_serialized if ((item.get("sla") or {}).get("state") == "breached"))
    due_soon_count = sum(1 for item in top_items_serialized if ((item.get("sla") or {}).get("state") == "due_soon"))
    pending_queue_count = len(queue_rows)

    backlog_pressure_score = min(
        100,
        int(
            (avg_backlog_weight * 0.40)
            + (overdue_count * 14)
            + (due_soon_count * 8)
            + (pending_queue_count * 2)
            + (len(on_hold) * 1)
        ),
    )
    if backlog_pressure_score >= 85:
        backlog_pressure = "critical"
        review_burst_size = min(max(4, pending_queue_count), 8)
        review_window_seconds = 15 * 60
    elif backlog_pressure_score >= 65:
        backlog_pressure = "high"
        review_burst_size = min(max(3, pending_queue_count), 6)
        review_window_seconds = 30 * 60
    elif backlog_pressure_score >= 40:
        backlog_pressure = "medium"
        review_burst_size = min(max(2, pending_queue_count), 4)
        review_window_seconds = 60 * 60
    else:
        backlog_pressure = "low"
        review_burst_size = min(max(1, pending_queue_count), 2)
        review_window_seconds = 2 * 3600

    work_window = _work_window_profile(
        backlog_pressure=backlog_pressure,
        backlog_pressure_score=backlog_pressure_score,
        overdue_count=overdue_count,
        due_soon_count=due_soon_count,
        pending_queue_count=pending_queue_count,
        review_burst_size=review_burst_size,
        review_window_seconds=review_window_seconds,
    )
    daily_agenda = _daily_agenda_payload(
        top_items_serialized=top_items_serialized,
        work_window=work_window,
        domain_buckets=domain_buckets,
    )

    if top_items_serialized:
        cadence_floor = min([int((item.get("cadence") or {}).get("seconds") or 120) for item in top_items_serialized] or [120])
    else:
        cadence_floor = 120
    if backlog_pressure == "critical" or overdue_count > 0:
        next_interval_suggested = max(15, min(cadence_floor, 20))
    elif backlog_pressure == "high" or due_soon_count >= 2:
        next_interval_suggested = max(20, min(cadence_floor, 30))
    elif backlog_pressure == "medium":
        next_interval_suggested = max(30, min(cadence_floor, 60))
    else:
        next_interval_suggested = max(60, cadence_floor)

    recent_cycles = db.execute(select(EvolutionCycleLog).order_by(EvolutionCycleLog.created_at.desc())).scalars().all()[:10]
    recent_cycles_serialized = [_serialize_cycle_log(r) for r in recent_cycles]

    return {
        "ok": True,
        "service": "evolution_internal",
        "mode": "governed",
        "git_bridge_base": _base_url(),
        "default_branch": _default_branch(),
        "master_admin_emails_configured": bool(_master_admin_emails()),
        "pending_master_approval": len(pending),
        "approved_pending_execution": len(approved),
        "on_hold": len(on_hold),
        "executed": len(executed),
        "execute_candidates": execute_candidates,
        "supported_actions": len(SUPPORTED_EVOLUTION_ACTIONS),
        "policy_version": POLICY_VERSION,
        "avg_priority": avg_priority,
        "avg_recurrence_window_count": avg_recurrence,
        "avg_operator_confidence": avg_operator_confidence,
        "avg_backlog_weight": avg_backlog_weight,
        "priority_buckets": priority_buckets,
        "lane_buckets": lane_buckets,
        "action_buckets": action_buckets,
        "recommendation_buckets": recommendation_buckets,
        "admin_recommendation_buckets": admin_recommendation_buckets,
        "operator_suggestion_buckets": operator_suggestion_buckets,
        "trend_buckets": trend_buckets,
        "domain_buckets": domain_buckets,
        "sla_buckets": sla_buckets,
        "age_buckets": age_buckets,
        "capacity_hint_buckets": capacity_hint_buckets,
        "backlog_pressure": backlog_pressure,
        "backlog_pressure_score": backlog_pressure_score,
        "overdue_count": overdue_count,
        "due_soon_count": due_soon_count,
        "review_burst_size": review_burst_size,
        "review_window_seconds": review_window_seconds,
        "touch_cooldown_seconds": detection_touch_cooldown_seconds(),
        "recurrence_window_seconds": recurrence_window_seconds(),
        "signature_stability_threshold": max(3, int(os.getenv("EVOLUTION_SIGNATURE_STABILITY_THRESHOLD", "4") or "4")),
        "next_interval_suggested_seconds": next_interval_suggested,
        "domain_sla_policy": _domain_sla_policy_payload(),
        "work_window": work_window,
        "daily_agenda": daily_agenda,
        "today_focus_domain": daily_agenda.get("dominant_domain"),
        "top_queue": top_items_serialized,
        "recent_cycles": recent_cycles_serialized,
    }


@router.get("/actions")
def evolution_actions_catalog(_admin=Depends(_require_master_admin_access)):
    return {
        "ok": True,
        "items": [
            {"action": action, **meta}
            for action, meta in sorted(SUPPORTED_EVOLUTION_ACTIONS.items())
        ],
        "master_admin": (_admin or {}).get("email") or (_admin or {}).get("via"),
    }


@router.get("/policy")
def evolution_policy_overview(_admin=Depends(_require_master_admin_access)):
    policy = SelfHealPolicy()
    return {
        "ok": True,
        "policy": policy.describe(),
        "master_admin": (_admin or {}).get("email") or (_admin or {}).get("via"),
    }


@router.post("/classify")
def evolution_classify(payload: EvolutionClassifyIn, _admin=Depends(_require_master_admin_access)):
    result = classify_and_patch(payload.error_text)
    return {
        "ok": True,
        "classification": result,
    }


@router.post("/scan-now")
async def evolution_scan_now(
    _admin=Depends(_require_master_admin_access),
    db: Session = Depends(get_db),
):
    trace_id = _new_trace_id()
    result = await run_governed_scan_cycle(db, trace_id=trace_id)
    db.commit()
    return {
        **result,
        "mode": "governed_scan",
        "master_admin": (_admin or {}).get("email") or (_admin or {}).get("via"),
    }


@router.get("/proposals")
def evolution_list_proposals(
    status: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=200),
    sort: str = Query(default="priority"),
    limit: int = Query(default=50, ge=1, le=200),
    _admin=Depends(_require_master_admin_access),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(EvolutionProposal)).scalars().all()
    if status:
        rows = [r for r in rows if str(getattr(r, "status", "") or "") == status]
    if action:
        rows = [r for r in rows if str(getattr(r, "action", "") or "") == action]
    if severity:
        rows = [r for r in rows if str(getattr(r, "severity", "") or "").upper() == str(severity).upper()]
    if q:
        needle = str(q or "").strip().lower()
        rows = [
            r for r in rows
            if needle in " ".join(
                [
                    str(getattr(r, "title", "") or ""),
                    str(getattr(r, "summary", "") or ""),
                    str(getattr(r, "code", "") or ""),
                    str(getattr(r, "category", "") or ""),
                    str(getattr(r, "source", "") or ""),
                ]
            ).lower()
        ]
    rows = _sort_proposals(rows, sort, db=db)[:limit]
    return {
        "ok": True,
        "items": [_serialize_proposal(r, db=db) for r in rows],
        "sort": sort,
        "master_admin": (_admin or {}).get("email") or (_admin or {}).get("via"),
    }


@router.get("/proposals/{proposal_id}")
def evolution_get_proposal(
    proposal_id: str,
    _admin=Depends(_require_master_admin_access),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(EvolutionProposal).where(EvolutionProposal.id == proposal_id)
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="proposal_not_found")
    executions = db.execute(
        select(EvolutionExecution)
        .where(EvolutionExecution.proposal_id == proposal_id)
        .order_by(EvolutionExecution.created_at.desc())
    ).scalars().all()
    signal_history = db.execute(
        select(EvolutionSignalSnapshot)
        .where(EvolutionSignalSnapshot.proposal_id == proposal_id)
        .order_by(EvolutionSignalSnapshot.created_at.desc())
    ).scalars().all()[:20]
    return {
        "ok": True,
        "item": _serialize_proposal(row, db=db),
        "executions": [_serialize_execution(r) for r in executions],
        "signal_history": [_serialize_signal_snapshot(r) for r in signal_history],
    }


@router.post("/proposals/{proposal_id}/approve")
def evolution_approve_proposal(
    proposal_id: str,
    payload: EvolutionDecisionIn,
    admin=Depends(_require_master_admin_access),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(EvolutionProposal).where(EvolutionProposal.id == proposal_id)
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="proposal_not_found")
    service = EvolutionGovernanceService(db=db)
    service.approve(
        row,
        actor_id=(admin or {}).get("sub"),
        actor_email=(admin or {}).get("email") or (admin or {}).get("via"),
        note=payload.note,
    )
    approval_trace_id = _new_trace_id()
    service.record_execution(
        proposal=row,
        status="approved",
        mode="master_review",
        actor_id=(admin or {}).get("sub"),
        actor_email=(admin or {}).get("email") or (admin or {}).get("via"),
        trace_id=approval_trace_id,
        result={"decision": "approved", "note": payload.note},
    )
    execution_result = None
    if payload.execute_now:
        exec_trace_id = _new_trace_id()
        execution = service.start_execution(
            proposal=row,
            mode="safe_pr",
            actor_id=(admin or {}).get("sub"),
            actor_email=(admin or {}).get("email") or (admin or {}).get("via"),
            trace_id=exec_trace_id,
            result={"decision": "execute_now", "note": payload.note},
        )
        db.commit()
        try:
            execution_result = _execute_approved_proposal(
                row=row,
                db=db,
                payload=EvolutionExecuteIn(
                    note=payload.note,
                    source_branch=payload.source_branch,
                    auto_pr=payload.auto_pr,
                    path=payload.path,
                    validate_after_commit=payload.validate_after_commit,
                    override_hard_gate=payload.override_hard_gate,
                ),
            )
            service.finish_execution(
                execution,
                proposal=row,
                status="completed",
                result=execution_result,
            )
        except HTTPException as exc:
            detail = exc.detail
            service.finish_execution(
                execution,
                proposal=row,
                status="failed",
                result={"http_status": exc.status_code, "detail": detail},
                error_text=str(detail),
            )
            db.commit()
            raise
        except Exception as exc:
            service.finish_execution(
                execution,
                proposal=row,
                status="failed",
                result={"error": repr(exc)},
                error_text=repr(exc),
            )
            db.commit()
            raise
    db.commit()
    db.refresh(row)
    return {"ok": True, "item": _serialize_proposal(row, db=db), "execution": execution_result}


@router.post("/proposals/{proposal_id}/reject")
def evolution_reject_proposal(
    proposal_id: str,
    payload: EvolutionDecisionIn,
    admin=Depends(_require_master_admin_access),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(EvolutionProposal).where(EvolutionProposal.id == proposal_id)
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="proposal_not_found")
    service = EvolutionGovernanceService(db=db)
    service.reject(
        row,
        actor_id=(admin or {}).get("sub"),
        actor_email=(admin or {}).get("email") or (admin or {}).get("via"),
        note=payload.note,
    )
    service.record_execution(
        proposal=row,
        status="rejected",
        mode="master_review",
        actor_id=(admin or {}).get("sub"),
        actor_email=(admin or {}).get("email") or (admin or {}).get("via"),
        trace_id=_new_trace_id(),
        result={"decision": "rejected", "note": payload.note},
    )
    db.commit()
    db.refresh(row)
    return {"ok": True, "item": _serialize_proposal(row, db=db)}




@router.post("/proposals/{proposal_id}/hold")
def evolution_hold_proposal(
    proposal_id: str,
    payload: EvolutionDecisionIn,
    admin=Depends(_require_master_admin_access),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(EvolutionProposal).where(EvolutionProposal.id == proposal_id)
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="proposal_not_found")
    if str(getattr(row, "status", "") or "").lower() in {"executed", "rolled_back"}:
        raise HTTPException(status_code=409, detail="proposal_already_finalized")
    service = EvolutionGovernanceService(db)
    service.hold(
        row,
        actor_id=(admin or {}).get("sub"),
        actor_email=(admin or {}).get("email") or (admin or {}).get("via"),
        note=payload.note,
    )
    service.record_execution(
        proposal=row,
        status="held",
        mode="manual",
        actor_id=(admin or {}).get("sub"),
        actor_email=(admin or {}).get("email") or (admin or {}).get("via"),
        trace_id=_new_trace_id(),
        result={
            "action": "hold",
            "note": payload.note,
            "operator_guidance": (_serialize_proposal(row, db=db) or {}).get("operator_guidance"),
        },
    )
    db.commit()
    return {
        "ok": True,
        "item": _serialize_proposal(row, db=db),
        "master_admin": (admin or {}).get("email") or (admin or {}).get("via"),
    }


@router.post("/proposals/{proposal_id}/execute")
def evolution_execute_proposal(
    proposal_id: str,
    payload: EvolutionExecuteIn,
    admin=Depends(_require_master_admin_access),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(EvolutionProposal).where(EvolutionProposal.id == proposal_id)
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="proposal_not_found")
    if str(getattr(row, "status", "") or "").lower() not in {"approved", "executed"}:
        raise HTTPException(status_code=409, detail="proposal_not_approved_for_execution")

    service = EvolutionGovernanceService(db=db)
    trace_id = _new_trace_id()
    execution = service.start_execution(
        proposal=row,
        mode="safe_pr",
        actor_id=(admin or {}).get("sub"),
        actor_email=(admin or {}).get("email") or (admin or {}).get("via"),
        trace_id=trace_id,
        result={"decision": "execute", "note": payload.note},
    )
    db.commit()

    try:
        result = _execute_approved_proposal(row=row, payload=payload, db=db)
        service.finish_execution(
            execution,
            proposal=row,
            status="completed",
            result=result,
        )
        db.commit()
        db.refresh(row)
        db.refresh(execution)
        return {
            "ok": True,
            "item": _serialize_proposal(row, db=db),
            "execution": _serialize_execution(execution),
            "result": result,
        }
    except HTTPException as exc:
        detail = exc.detail
        service.finish_execution(
            execution,
            proposal=row,
            status="failed",
            result={"http_status": exc.status_code, "detail": detail},
            error_text=str(detail),
        )
        db.commit()
        raise
    except Exception as exc:
        service.finish_execution(
            execution,
            proposal=row,
            status="failed",
            result={"error": repr(exc)},
            error_text=repr(exc),
        )
        db.commit()
        raise HTTPException(status_code=500, detail=f"proposal_execution_failed: {exc}") from exc


@router.post("/proposals/{proposal_id}/retry")
def evolution_retry_proposal_execution(
    proposal_id: str,
    payload: EvolutionExecuteIn,
    admin=Depends(_require_master_admin_access),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(EvolutionProposal).where(EvolutionProposal.id == proposal_id)
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="proposal_not_found")

    last_execution = db.execute(
        select(EvolutionExecution)
        .where(EvolutionExecution.proposal_id == proposal_id)
        .order_by(EvolutionExecution.created_at.desc())
    ).scalars().first()
    if not last_execution or str(getattr(last_execution, "status", "") or "").lower() != "failed":
        raise HTTPException(status_code=409, detail="proposal_retry_requires_failed_execution")

    service = EvolutionGovernanceService(db=db)
    trace_id = _new_trace_id()
    execution = service.start_execution(
        proposal=row,
        mode="retry_safe_pr",
        actor_id=(admin or {}).get("sub"),
        actor_email=(admin or {}).get("email") or (admin or {}).get("via"),
        trace_id=trace_id,
        result={"decision": "retry", "note": payload.note, "retried_execution_id": last_execution.id},
    )
    db.commit()
    try:
        result = _execute_approved_proposal(row=row, payload=payload, db=db)
        service.finish_execution(execution, proposal=row, status="completed", result=result)
        db.commit()
        db.refresh(row)
        db.refresh(execution)
        return {"ok": True, "item": _serialize_proposal(row, db=db), "execution": _serialize_execution(execution), "result": result}
    except HTTPException as exc:
        detail = exc.detail
        service.finish_execution(
            execution,
            proposal=row,
            status="failed",
            result={"http_status": exc.status_code, "detail": detail},
            error_text=str(detail),
        )
        db.commit()
        raise
    except Exception as exc:
        service.finish_execution(
            execution,
            proposal=row,
            status="failed",
            result={"error": repr(exc)},
            error_text=repr(exc),
        )
        db.commit()
        raise HTTPException(status_code=500, detail=f"proposal_retry_failed: {exc}") from exc


@router.post("/executions/{execution_id}/rollback")
def evolution_rollback_execution(
    execution_id: str,
    payload: EvolutionExecuteIn,
    admin=Depends(_require_master_admin_access),
    db: Session = Depends(get_db),
):
    execution_row = db.execute(
        select(EvolutionExecution).where(EvolutionExecution.id == execution_id)
    ).scalar_one_or_none()
    if not execution_row:
        raise HTTPException(status_code=404, detail="execution_not_found")
    if str(getattr(execution_row, "status", "") or "").lower() != "completed":
        raise HTTPException(status_code=409, detail="rollback_requires_completed_execution")

    proposal = db.execute(
        select(EvolutionProposal).where(EvolutionProposal.id == execution_row.proposal_id)
    ).scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="proposal_not_found")

    service = EvolutionGovernanceService(db=db)
    trace_id = _new_trace_id()
    rollback_exec = service.start_execution(
        proposal=proposal,
        mode="rollback_safe_pr",
        actor_id=(admin or {}).get("sub"),
        actor_email=(admin or {}).get("email") or (admin or {}).get("via"),
        trace_id=trace_id,
        result={"decision": "rollback", "target_execution_id": execution_id, "note": payload.note},
    )
    db.commit()
    try:
        result = _execute_rollback_for_execution(row=proposal, execution=execution_row, payload=payload)
        service.finish_execution(
            rollback_exec,
            proposal=proposal,
            status="completed",
            result=result,
            proposal_status_on_success="rolled_back",
        )
        db.commit()
        db.refresh(proposal)
        db.refresh(rollback_exec)
        return {"ok": True, "item": _serialize_proposal(proposal, db=db), "execution": _serialize_execution(rollback_exec), "result": result}
    except HTTPException as exc:
        detail = exc.detail
        service.finish_execution(
            rollback_exec,
            proposal=proposal,
            status="failed",
            result={"http_status": exc.status_code, "detail": detail},
            error_text=str(detail),
        )
        db.commit()
        raise
    except Exception as exc:
        service.finish_execution(
            rollback_exec,
            proposal=proposal,
            status="failed",
            result={"error": repr(exc)},
            error_text=repr(exc),
        )
        db.commit()
        raise HTTPException(status_code=500, detail=f"proposal_rollback_failed: {exc}") from exc


@router.post("/propose-schema-patch")
def evolution_propose_schema_patch(payload: EvolutionProposeIn, _admin=Depends(_require_master_admin_access)):
    result = classify_and_patch(payload.error_text)

    if result.get("action") != "create_table_patch":
        return {
            "ok": False,
            "classification": result,
            "reason": "no_supported_patch_generated",
        }

    table_name = result["table"]
    sql_patch = result["sql"]
    branch_name = _safe_branch_name(table_name)
    if is_protected_branch(branch_name) or not is_branch_allowed(branch_name):
        raise HTTPException(status_code=422, detail={"reason": "unsafe_target_branch", "branch": branch_name})
    source_branch = payload.source_branch or _default_branch()

    current_file = _request(
        "GET",
        f"/api/internal/git/file?path={payload.path}&branch={source_branch}",
    )
    current_content = current_file.get("content", "")
    if not isinstance(current_content, str):
        raise HTTPException(status_code=500, detail="git file content missing")

    patched_content = _build_db_patch(current_content, sql_patch, table_name)
    patch_hash = hashlib.sha256((payload.path + sql_patch).encode("utf-8")).hexdigest()[:12]

    branch_resp = _request(
        "POST",
        "/api/internal/git/branch",
        json_body={
            "branch_name": branch_name,
            "source_branch": source_branch,
        },
    )

    commit_message = f"fix(self-heal): reconcile missing table {table_name} [{patch_hash}]"
    commit_resp = _request(
        "POST",
        "/api/internal/git/commit",
        json_body={
            "path": payload.path,
            "content": patched_content,
            "message": commit_message,
            "branch": branch_name,
        },
    )

    pr_resp = None
    if payload.auto_pr:
        pr_title = payload.pr_title or f"Self-heal: reconcile missing table `{table_name}`"
        pr_body = payload.pr_body or (
            f"Automated safe-mode schema patch.\n\n"
            f"- detected table: `{table_name}`\n"
            f"- action: `{result['action']}`\n"
            f"- path: `{payload.path}`\n"
            f"- source branch: `{source_branch}`\n"
            f"- generated by: `evolution_internal`\n\n"
            f"Review required before merge."
        )
        pr_resp = _request(
            "POST",
            "/api/internal/git/pr",
            json_body={
                "title": pr_title,
                "body": pr_body,
                "head": branch_name,
                "base": source_branch,
            },
        )

    return {
        "ok": True,
        "mode": "safe_pr",
        "classification": result,
        "branch": branch_resp,
        "commit": commit_resp,
        "pr": pr_resp,
    }


@router.post("/batch/plan")
def evolution_batch_plan(
    payload: EvolutionBatchPlanIn,
    _admin=Depends(_require_master_admin_access),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(EvolutionProposal)).scalars().all()
    planned = _batch_candidates(
        rows=rows,
        db=db,
        limit=payload.limit,
        confidence_min=payload.confidence_min,
        include_statuses=payload.include_statuses,
        allow_sensitive_domains=payload.allow_sensitive_domains,
    )
    executable = [item for item in planned if item.get("eligible")]
    blocked = [item for item in planned if not item.get("eligible")]
    return {
        "ok": True,
        "items": planned,
        "eligible_count": len(executable),
        "blocked_count": len(blocked),
    }


@router.post("/batch/execute")
def evolution_batch_execute(
    payload: EvolutionBatchExecuteIn,
    admin=Depends(_require_master_admin_access),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(EvolutionProposal)).scalars().all()
    planned = _batch_candidates(
        rows=rows,
        db=db,
        limit=payload.limit,
        confidence_min=payload.confidence_min,
        include_statuses=payload.include_statuses,
        allow_sensitive_domains=payload.allow_sensitive_domains,
    )
    executed = []
    skipped = []
    service = EvolutionGovernanceService(db=db)
    for item in planned:
        proposal_item = item.get("proposal") or {}
        if not item.get("eligible"):
            skipped.append({"proposal_id": proposal_item.get("id"), "reason": item.get("reasons")})
            continue
        row = db.execute(select(EvolutionProposal).where(EvolutionProposal.id == proposal_item.get("id"))).scalar_one_or_none()
        if not row:
            skipped.append({"proposal_id": proposal_item.get("id"), "reason": ["proposal_not_found"]})
            continue
        if str(getattr(row, "status", "") or "").lower() == "awaiting_master_approval":
            service.approve(
                row,
                actor_id=(admin or {}).get("sub"),
                actor_email=(admin or {}).get("email") or (admin or {}).get("via"),
                note=payload.note or "batch_approve_execute",
            )
        trace_id = _new_trace_id()
        execution = service.start_execution(
            proposal=row,
            mode="batch_safe_pr",
            actor_id=(admin or {}).get("sub"),
            actor_email=(admin or {}).get("email") or (admin or {}).get("via"),
            trace_id=trace_id,
            result={"decision": "batch_execute", "note": payload.note},
        )
        db.commit()
        try:
            result = _execute_approved_proposal(
                row=row,
                db=db,
                payload=EvolutionExecuteIn(
                    note=payload.note,
                    source_branch=None,
                    auto_pr=payload.auto_pr,
                    path=payload.path,
                    validate_after_commit=payload.validate_after_commit,
                    override_hard_gate=payload.override_hard_gate,
                ),
            )
            service.finish_execution(execution, proposal=row, status="completed", result=result)
            db.commit()
            db.refresh(row)
            db.refresh(execution)
            executed.append({"proposal": _serialize_proposal(row, db=db), "execution": _serialize_execution(execution)})
        except HTTPException as exc:
            detail = exc.detail
            service.finish_execution(execution, proposal=row, status="failed", result={"http_status": exc.status_code, "detail": detail}, error_text=str(detail))
            db.commit()
            skipped.append({"proposal_id": row.id, "reason": detail})
        except Exception as exc:
            service.finish_execution(execution, proposal=row, status="failed", result={"error": repr(exc)}, error_text=repr(exc))
            db.commit()
            skipped.append({"proposal_id": row.id, "reason": repr(exc)})
    return {"ok": True, "executed": executed, "skipped": skipped, "attempted": len(planned)}
