from __future__ import annotations

import json
import hashlib
import os
import time
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    EvolutionProposal,
    EvolutionExecution,
    EvolutionSignalSnapshot,
    EvolutionCycleLog,
)
from app.self_heal.detector import SelfHealDetector
from app.self_heal.classifier import SelfHealClassifier, ClassifiedIssue
from app.self_heal.policy import SelfHealPolicy, PolicyDecision, POLICY_VERSION
from app.self_heal.trust import build_trust_envelope, coerce_trust_envelope


def _now_ts() -> int:
    return int(time.time())


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)
    except Exception:
        return "{}"


def _safe_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default)) or str(default)).strip())
    except Exception:
        return int(default)


def _active_statuses() -> set[str]:
    return {"awaiting_master_approval", "approved", "executed", "running"}


def detection_touch_cooldown_seconds() -> int:
    return max(60, _env_int("EVOLUTION_PROPOSAL_TOUCH_COOLDOWN_SECONDS", 900))


def recurrence_window_seconds() -> int:
    return max(3600, _env_int("EVOLUTION_RECURRENCE_WINDOW_SECONDS", 7 * 24 * 3600))


def signature_stability_threshold() -> int:
    return max(3, _env_int("EVOLUTION_SIGNATURE_STABILITY_THRESHOLD", 4))


def _aggregate_learning_summary(db: Session, *, action: str = "", domain_scope: str = "") -> Dict[str, Any]:
    action = str(action or "").strip().lower()
    domain_scope = str(domain_scope or "").strip().lower()
    rows = db.execute(select(EvolutionExecution).order_by(EvolutionExecution.created_at.desc())).scalars().all()
    scoped: list[EvolutionExecution] = []
    for ex in rows:
        result = _safe_dict(_json_loads(getattr(ex, "result_json", None)))
        meta = _safe_dict(result.get("proposal_meta"))
        ex_action = str(meta.get("action") or "").strip().lower()
        ex_domain = str(meta.get("domain_scope") or "").strip().lower()
        if action and ex_action and ex_action != action:
            continue
        if domain_scope and ex_domain and ex_domain != domain_scope:
            continue
        scoped.append(ex)
    sample_size = len(scoped)
    if sample_size == 0:
        return {
            "sample_size": 0,
            "success_rate": None,
            "validation_rate": None,
            "recent_failed_executions": 0,
            "rolled_back_count": 0,
            "confidence_adjustment": 0,
        }

    completed = 0
    validated = 0
    recent_failed = 0
    rolled_back = 0
    for ex in scoped:
        status = str(getattr(ex, "status", "") or "").lower()
        result = _safe_dict(_json_loads(getattr(ex, "result_json", None)))
        post = _safe_dict(result.get("post_validation"))
        if status == "completed":
            completed += 1
        if post.get("ok") is True:
            validated += 1
        if status == "failed":
            recent_failed += 1
        if status == "rolled_back":
            rolled_back += 1
    success_rate = round((completed / sample_size) * 100, 1)
    validation_rate = round((validated / sample_size) * 100, 1)
    confidence_adjustment = 0
    if success_rate >= 90 and validation_rate >= 90 and recent_failed == 0:
        confidence_adjustment = 4
    elif success_rate < 60 or validation_rate < 60:
        confidence_adjustment = -8
    elif recent_failed >= 2 or rolled_back >= 2:
        confidence_adjustment = -6
    return {
        "sample_size": sample_size,
        "success_rate": success_rate,
        "validation_rate": validation_rate,
        "recent_failed_executions": recent_failed,
        "rolled_back_count": rolled_back,
        "confidence_adjustment": confidence_adjustment,
    }


def trend_escalation_delta_threshold() -> int:
    return max(4, _env_int("EVOLUTION_TREND_DELTA_THRESHOLD", 8))


def _avg(values: list[int]) -> int:
    values = [int(v or 0) for v in values]
    if not values:
        return 0
    return round(sum(values) / len(values))


def build_issue_fingerprint(*, code: str, severity: str, category: str, source: str, action: str, details: Optional[Dict[str, Any]] = None) -> str:
    payload = {
        "code": (code or "").upper(),
        "severity": (severity or "").upper(),
        "category": (category or "").lower(),
        "source": (source or "").lower(),
        "action": (action or "").lower(),
        "details": details or {},
    }
    raw = _json_dumps(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _proposal_status_for_action(action: str) -> str:
    action = (action or "").strip().lower()
    if action in {"ignore"}:
        return "observed"
    return "awaiting_master_approval"


def _new_id(prefix: str) -> str:
    payload = f"{prefix}:{time.time_ns()}"
    return f"{prefix}_{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:16]}"


def infer_domain_scope(*, issue: ClassifiedIssue) -> str:
    code = str(issue.code or "").upper()
    category = str(issue.category or "").lower()
    source = str(issue.source or "").lower()
    raw = f"{code}:{category}:{source}".lower()
    if "wallet" in raw or "billing" in raw or "pricing" in raw:
        return "billing"
    if "auth" in raw or "token" in raw or "password" in raw:
        return "auth"
    if "security" in raw or "rbac" in raw or "permission" in raw:
        return "security"
    if "realtime" in raw or "sse" in raw or "stream" in raw:
        return "realtime"
    if "schema" in raw or "table" in raw or "column" in raw:
        return "schema"
    return category or "general"


def cadence_for_recommendation(policy: SelfHealPolicy, *, priority_score: int, recommendation: str, recurrence_window_count: int) -> int:
    return int(policy.cadence_for_priority(
        priority_score=priority_score,
        recommendation=recommendation,
        recurrence_window_count=recurrence_window_count,
    ))


class EvolutionGovernanceService:
    def __init__(self, db: Session, logger=None, org_slug: str = "system") -> None:
        self.db = db
        self.logger = logger
        self.org_slug = org_slug or "system"
        self.touch_cooldown_seconds = detection_touch_cooldown_seconds()
        self.recurrence_window_seconds = recurrence_window_seconds()
        self.signature_stability_threshold = signature_stability_threshold()
        self.trend_delta_threshold = trend_escalation_delta_threshold()

    def recent_recurrence_count(self, *, fingerprint: str, now: Optional[int] = None) -> int:
        now = int(now or _now_ts())
        window_start = now - self.recurrence_window_seconds
        rows = self.db.execute(
            select(EvolutionSignalSnapshot).where(
                EvolutionSignalSnapshot.fingerprint == fingerprint,
                EvolutionSignalSnapshot.created_at >= window_start,
            )
        ).scalars().all()
        return len(rows)

    def recent_signal_snapshots(self, *, fingerprint: str, now: Optional[int] = None, limit: int = 12) -> list[EvolutionSignalSnapshot]:
        now = int(now or _now_ts())
        window_start = now - self.recurrence_window_seconds
        rows = self.db.execute(
            select(EvolutionSignalSnapshot)
            .where(
                EvolutionSignalSnapshot.fingerprint == fingerprint,
                EvolutionSignalSnapshot.created_at >= window_start,
            )
            .order_by(EvolutionSignalSnapshot.created_at.asc())
        ).scalars().all()
        if limit and len(rows) > limit:
            rows = rows[-limit:]
        return rows

    def signature_profile(self, *, fingerprint: str, now: Optional[int] = None) -> Dict[str, Any]:
        rows = self.recent_signal_snapshots(fingerprint=fingerprint, now=now, limit=12)
        priorities = [int(getattr(r, "priority_score", 0) or 0) for r in rows]
        recommendations = [str(getattr(r, "recommendation", "") or "") for r in rows]
        repeat_count = len(rows)
        trend_delta = 0
        if len(priorities) >= 4:
            half = max(1, len(priorities) // 2)
            trend_delta = _avg(priorities[half:]) - _avg(priorities[:half])
        elif len(priorities) >= 2:
            trend_delta = priorities[-1] - priorities[0]
        if repeat_count <= 1:
            trend_state = "new"
        elif trend_delta >= self.trend_delta_threshold:
            trend_state = "rising"
        elif trend_delta <= (-1 * self.trend_delta_threshold):
            trend_state = "cooling"
        else:
            trend_state = "stable"
        tail = recommendations[-min(3, len(recommendations)):] if recommendations else []
        stable_recommendation = bool(tail) and len(set(tail)) == 1
        stable_signature = (
            repeat_count >= self.signature_stability_threshold
            and stable_recommendation
            and trend_state in {"stable", "cooling"}
        )
        return {
            "repeat_count": repeat_count,
            "avg_priority": _avg(priorities),
            "latest_priority": priorities[-1] if priorities else 0,
            "trend_delta": int(trend_delta or 0),
            "trend_state": trend_state,
            "stable_recommendation": stable_recommendation,
            "stable_signature": stable_signature,
            "latest_recommendation": recommendations[-1] if recommendations else "",
        }

    def suppression_meta(
        self,
        *,
        row: EvolutionProposal,
        now: int,
        decision: PolicyDecision,
        cadence_seconds: int,
        signature_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        signature_profile = signature_profile or {}
        status = str(getattr(row, "status", "") or "").lower()
        last_detected_at = int(getattr(row, "last_detected_at", 0) or 0)
        adaptive_cooldown = max(self.touch_cooldown_seconds, int(cadence_seconds or 0))
        repeat_count = int(signature_profile.get("repeat_count") or 0)
        trend_state = str(signature_profile.get("trend_state") or "new").lower()
        if repeat_count >= self.signature_stability_threshold and trend_state in {"stable", "cooling"}:
            adaptive_cooldown = max(
                adaptive_cooldown,
                min(self.recurrence_window_seconds // 8, max(600, int((cadence_seconds or self.touch_cooldown_seconds) * max(2, repeat_count // self.signature_stability_threshold or 1)))),
            )
        within_cooldown = status in _active_statuses() and last_detected_at > 0 and (now - last_detected_at) < adaptive_cooldown
        signature_suppressed = (
            status in _active_statuses()
            and repeat_count >= self.signature_stability_threshold
            and trend_state in {"stable", "cooling"}
            and str(getattr(decision, "suppression_hint", "none") or "none") == "suppress_recurring_signature"
        )
        if within_cooldown:
            return {
                "suppress": True,
                "reason": "cooldown_active",
                "cooldown_seconds": adaptive_cooldown,
                "cooldown_remaining_seconds": max(0, adaptive_cooldown - (now - last_detected_at)),
                "signature_profile": signature_profile,
            }
        if signature_suppressed:
            return {
                "suppress": True,
                "reason": "signature_recurring_suppressed",
                "cooldown_seconds": adaptive_cooldown,
                "cooldown_remaining_seconds": 0,
                "signature_profile": signature_profile,
            }
        return {
            "suppress": False,
            "reason": "touch_allowed",
            "cooldown_seconds": adaptive_cooldown,
            "cooldown_remaining_seconds": 0,
            "signature_profile": signature_profile,
        }

    def upsert_detection(
        self,
        *,
        issue: ClassifiedIssue,
        decision: PolicyDecision,
        finding: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        domain_scope: Optional[str] = None,
        cadence_seconds: Optional[int] = None,
        signature_profile: Optional[Dict[str, Any]] = None,
    ) -> tuple[EvolutionProposal, Dict[str, Any]]:
        finding = _safe_dict(finding)
        domain_scope = (domain_scope or infer_domain_scope(issue=issue)).lower()
        trust = coerce_trust_envelope(
            finding.get("trust"),
            fallback_source_type=issue.source or issue.category or "detector",
            fallback_source_origin="governance_detection",
        )
        finding["trust"] = trust
        fingerprint = build_issue_fingerprint(
            code=issue.code,
            severity=issue.severity,
            category=issue.category,
            source=issue.source,
            action=decision.action,
            details=issue.details,
        )
        now = _now_ts()
        row = self.db.execute(select(EvolutionProposal).where(EvolutionProposal.fingerprint == fingerprint)).scalar_one_or_none()
        decision_payload = decision.to_dict()
        decision_payload["trust"] = trust
        recurrence_count = self.recent_recurrence_count(fingerprint=fingerprint, now=now) + 1
        cadence_seconds = int(cadence_seconds or cadence_for_recommendation(
            SelfHealPolicy(logger=self.logger),
            priority_score=int(decision.priority_score or 0),
            recommendation=decision.recommendation,
            recurrence_window_count=recurrence_count,
        ))
        signature_profile = signature_profile or self.signature_profile(fingerprint=fingerprint, now=now)

        if row:
            row.decision_json = _json_dumps(decision_payload)
            row.finding_json = _json_dumps(finding)
            row.last_trace_id = trace_id or getattr(row, "last_trace_id", None)
            row.domain_scope = domain_scope
            row.recurrence_window_count = recurrence_count
            row.blast_radius_accumulated = int(getattr(row, "blast_radius_accumulated", 0) or 0) + int(decision.blast_radius_score or 0)
            row.security_accumulated = int(getattr(row, "security_accumulated", 0) or 0) + int(decision.security_score or 0)
            row.last_priority_score = int(decision.priority_score or 0)
            row.last_recommendation = decision.recommendation
            row.last_cadence_seconds = cadence_seconds
            if getattr(row, "status", "") in {"resolved", "failed", "rolled_back", "rejected"}:
                row.status = _proposal_status_for_action(decision.action)
            suppression = self.suppression_meta(
                row=row,
                now=now,
                decision=decision,
                cadence_seconds=cadence_seconds,
                signature_profile=signature_profile,
            )
            if suppression.get("suppress"):
                self._record_signal_snapshot(
                    proposal=row,
                    fingerprint=fingerprint,
                    issue=issue,
                    decision=decision,
                    domain_scope=domain_scope,
                    recurrence_window_count=recurrence_count,
                    cadence_seconds=cadence_seconds,
                    trace_id=trace_id,
                    finding=finding,
                    signature_profile=signature_profile,
                )
                return row, {
                    "created": False,
                    "suppressed": True,
                    "reason": suppression.get("reason") or "suppressed",
                    "cooldown_seconds": suppression.get("cooldown_seconds") or self.touch_cooldown_seconds,
                    "cooldown_remaining_seconds": suppression.get("cooldown_remaining_seconds") or 0,
                    "signature_profile": signature_profile,
                }
            row.last_detected_at = now
            row.detected_count = int(getattr(row, "detected_count", 0) or 0) + 1
            row.updated_at = now
            self._record_signal_snapshot(
                proposal=row,
                fingerprint=fingerprint,
                issue=issue,
                decision=decision,
                domain_scope=domain_scope,
                recurrence_window_count=recurrence_count,
                cadence_seconds=cadence_seconds,
                trace_id=trace_id,
                finding=finding,
                signature_profile=signature_profile,
            )
            return row, {
                "created": False,
                "suppressed": False,
                "reason": "existing_updated",
                "cooldown_seconds": suppression.get("cooldown_seconds") or self.touch_cooldown_seconds,
                "signature_profile": signature_profile,
            }

        row = EvolutionProposal(
            id=_new_id("eprop"),
            org_slug=self.org_slug,
            fingerprint=fingerprint,
            code=issue.code,
            severity=issue.severity,
            category=issue.category,
            source=issue.source,
            action=decision.action,
            status=_proposal_status_for_action(decision.action),
            title=self._title_for(issue, decision),
            summary=self._summary_for(issue, decision, domain_scope=domain_scope, recurrence_window_count=recurrence_count),
            finding_json=_json_dumps(finding),
            issue_json=_json_dumps({"code": issue.code, "severity": issue.severity, "category": issue.category, "source": issue.source, "details": issue.details, "trust": trust}),
            decision_json=_json_dumps(decision_payload),
            domain_scope=domain_scope,
            recurrence_window_count=recurrence_count,
            blast_radius_accumulated=int(decision.blast_radius_score or 0),
            security_accumulated=int(decision.security_score or 0),
            last_priority_score=int(decision.priority_score or 0),
            last_recommendation=decision.recommendation,
            last_cadence_seconds=cadence_seconds,
            first_detected_at=now,
            last_detected_at=now,
            detected_count=1,
            last_trace_id=trace_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()
        self._record_signal_snapshot(
            proposal=row,
            fingerprint=fingerprint,
            issue=issue,
            decision=decision,
            domain_scope=domain_scope,
            recurrence_window_count=recurrence_count,
            cadence_seconds=cadence_seconds,
            trace_id=trace_id,
            finding=finding,
            signature_profile=signature_profile,
        )
        return row, {
            "created": True,
            "suppressed": False,
            "reason": "created",
            "cooldown_seconds": self.touch_cooldown_seconds,
            "signature_profile": signature_profile,
        }

    def approve(self, proposal: EvolutionProposal, *, actor_id: Optional[str], actor_email: Optional[str], note: Optional[str] = None) -> EvolutionProposal:
        now = _now_ts()
        proposal.status = "approved"
        proposal.approved_at = now
        proposal.approved_by = actor_id or actor_email
        proposal.approval_note = note
        proposal.updated_at = now
        return proposal

    def reject(self, proposal: EvolutionProposal, *, actor_id: Optional[str], actor_email: Optional[str], note: Optional[str] = None) -> EvolutionProposal:
        now = _now_ts()
        proposal.status = "rejected"
        proposal.rejected_at = now
        proposal.rejected_by = actor_id or actor_email
        proposal.rejection_note = note
        proposal.updated_at = now
        return proposal

    def hold(self, proposal: EvolutionProposal, *, actor_id: Optional[str], actor_email: Optional[str], note: Optional[str] = None) -> EvolutionProposal:
        now = _now_ts()
        proposal.status = "on_hold"
        proposal.approval_note = note
        proposal.updated_at = now
        proposal.approved_by = actor_id or actor_email
        proposal.approved_at = now
        return proposal

    def record_execution(self, *, proposal: EvolutionProposal, status: str, mode: str = "manual", actor_id: Optional[str] = None, actor_email: Optional[str] = None, trace_id: Optional[str] = None, result: Optional[Dict[str, Any]] = None, error_text: Optional[str] = None) -> EvolutionExecution:
        now = _now_ts()
        row = EvolutionExecution(
            id=_new_id("eexec"),
            org_slug=proposal.org_slug,
            proposal_id=proposal.id,
            status=status,
            mode=mode,
            actor_ref=actor_id or actor_email,
            trace_id=trace_id,
            result_json=_json_dumps(result),
            error_text=error_text,
            started_at=now,
            completed_at=now if status in {"completed", "failed", "rejected", "approved", "rolled_back", "held"} else None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        proposal.last_execution_status = status
        proposal.updated_at = now
        return row

    def start_execution(self, *, proposal: EvolutionProposal, mode: str = "manual", actor_id: Optional[str] = None, actor_email: Optional[str] = None, trace_id: Optional[str] = None, result: Optional[Dict[str, Any]] = None) -> EvolutionExecution:
        now = _now_ts()
        row = EvolutionExecution(
            id=_new_id("eexec"),
            org_slug=proposal.org_slug,
            proposal_id=proposal.id,
            status="running",
            mode=mode,
            actor_ref=actor_id or actor_email,
            trace_id=trace_id,
            result_json=_json_dumps(result),
            error_text=None,
            started_at=now,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        proposal.last_execution_status = "running"
        proposal.updated_at = now
        return row

    def finish_execution(self, execution: EvolutionExecution, *, proposal: EvolutionProposal, status: str, result: Optional[Dict[str, Any]] = None, error_text: Optional[str] = None, proposal_status_on_success: Optional[str] = None) -> EvolutionExecution:
        now = _now_ts()
        execution.status = status
        execution.result_json = _json_dumps(result)
        execution.error_text = error_text
        execution.completed_at = now
        execution.updated_at = now
        proposal.last_execution_status = status
        if status == "completed":
            proposal.status = proposal_status_on_success or "executed"
        if status == "rolled_back":
            proposal.status = "rolled_back"
        proposal.updated_at = now
        return execution

    def record_cycle_log(
        self,
        *,
        trace_id: Optional[str],
        findings: int,
        classified: int,
        proposals_touched: int,
        proposals_created: int,
        proposals_suppressed: int,
        max_priority_score: int,
        avg_priority_score: int,
        next_interval_suggested_seconds: int,
        recommendation_buckets: Dict[str, int],
        domain_buckets: Dict[str, int],
        top_queue: list[dict[str, Any]],
    ) -> EvolutionCycleLog:
        row = EvolutionCycleLog(
            id=_new_id("ecycle"),
            org_slug=self.org_slug,
            trace_id=trace_id,
            findings=int(findings or 0),
            classified=int(classified or 0),
            proposals_touched=int(proposals_touched or 0),
            proposals_created=int(proposals_created or 0),
            proposals_suppressed=int(proposals_suppressed or 0),
            max_priority_score=int(max_priority_score or 0),
            avg_priority_score=int(avg_priority_score or 0),
            next_interval_suggested_seconds=int(next_interval_suggested_seconds or 0),
            recommendation_buckets_json=_json_dumps(recommendation_buckets),
            domain_buckets_json=_json_dumps(domain_buckets),
            top_queue_json=_json_dumps(top_queue[:10]),
            policy_version=POLICY_VERSION,
            created_at=_now_ts(),
        )
        self.db.add(row)
        return row

    def _record_signal_snapshot(
        self,
        *,
        proposal: EvolutionProposal,
        fingerprint: str,
        issue: ClassifiedIssue,
        decision: PolicyDecision,
        domain_scope: str,
        recurrence_window_count: int,
        cadence_seconds: int,
        trace_id: Optional[str],
        finding: Optional[Dict[str, Any]],
        signature_profile: Optional[Dict[str, Any]] = None,
    ) -> EvolutionSignalSnapshot:
        row = EvolutionSignalSnapshot(
            id=_new_id("esig"),
            org_slug=proposal.org_slug,
            proposal_id=proposal.id,
            fingerprint=fingerprint,
            code=issue.code,
            category=issue.category,
            domain_scope=domain_scope,
            recurrence_window_count=int(recurrence_window_count or 1),
            blast_radius_score=int(decision.blast_radius_score or 0),
            security_score=int(decision.security_score or 0),
            priority_score=int(decision.priority_score or 0),
            recommendation=decision.recommendation,
            cadence_seconds=int(cadence_seconds or 0),
            policy_version=decision.policy_version,
            trace_id=trace_id,
            payload_json=_json_dumps({
                "finding": finding or {},
                "issue": {
                    "code": issue.code,
                    "severity": issue.severity,
                    "category": issue.category,
                    "source": issue.source,
                    "details": issue.details,
                },
                "decision": decision.to_dict(),
                "signature_profile": signature_profile or {},
            }),
            created_at=_now_ts(),
        )
        self.db.add(row)
        return row

    def _title_for(self, issue: ClassifiedIssue, decision: PolicyDecision) -> str:
        return f"{issue.code} → {decision.action}"

    def _summary_for(self, issue: ClassifiedIssue, decision: PolicyDecision, *, domain_scope: str, recurrence_window_count: int) -> str:
        details = issue.details or {}
        fragments = [f"severity={issue.severity}", f"category={issue.category}", f"source={issue.source}", f"domain={domain_scope}"]
        if recurrence_window_count > 1:
            fragments.append(f"recurrence_window={recurrence_window_count}")
        if getattr(decision, "trend_state", "new") not in {"", "new"}:
            fragments.append(f"trend={decision.trend_state}")
        if getattr(decision, "admin_recommendation", None):
            fragments.append(f"admin={decision.admin_recommendation}")
        if details.get("table"):
            fragments.append(f"table={details['table']}")
        if details.get("column"):
            fragments.append(f"column={details['column']}")
        return f"{decision.reason}; " + ", ".join(fragments)


async def run_governed_scan_cycle(db: Session, logger=None, trace_id: Optional[str] = None) -> Dict[str, Any]:
    detector = SelfHealDetector(db=db, logger=logger)
    classifier = SelfHealClassifier(logger=logger)
    policy = SelfHealPolicy(logger=logger)
    governance = EvolutionGovernanceService(db=db, logger=logger)

    findings = await detector.scan()
    findings_payload = detector.serialize(findings)
    issues = classifier.classify(findings_payload)

    created = 0
    touched = 0
    suppressed = 0
    max_priority = 0
    priority_total = 0
    touched_ids: list[str] = []
    recommendation_buckets: dict[str, int] = {}
    admin_recommendation_buckets: dict[str, int] = {}
    trend_buckets: dict[str, int] = {}
    domain_buckets: dict[str, int] = {}

    for issue, finding in zip(issues, findings_payload):
        domain_scope = infer_domain_scope(issue=issue)
        baseline_policy = policy.decide(
            severity=issue.severity,
            category=issue.category,
            code=issue.code,
            detected_count=1,
            domain_scope=domain_scope,
            recurrence_window_count=1,
        )
        fingerprint = build_issue_fingerprint(
            code=issue.code,
            severity=issue.severity,
            category=issue.category,
            source=issue.source,
            action=baseline_policy.action,
            details=issue.details,
        )
        existing = db.execute(
            select(EvolutionProposal).where(EvolutionProposal.fingerprint == fingerprint)
        ).scalar_one_or_none()
        signature_profile = governance.signature_profile(fingerprint=fingerprint)
        detected_count = int(getattr(existing, "detected_count", 0) or 0) + 1 if existing else 1
        recent_count = max(1, int(signature_profile.get("repeat_count") or 0)) + 1
        blast_accum = int(getattr(existing, "blast_radius_accumulated", 0) or 0)
        security_accum = int(getattr(existing, "security_accumulated", 0) or 0)
        learning = _aggregate_learning_summary(
            db,
            action=baseline_policy.action,
            domain_scope=domain_scope,
        )
        trust = build_trust_envelope(
            source_type=issue.source or issue.category or "detector",
            source_origin="governance_detection",
            source_ref=trace_id,
            content={"details": issue.details, "finding": finding},
            explicit_level="internal",
            instruction_authority=False,
        )
        decision = policy.decide(
            severity=issue.severity,
            category=issue.category,
            code=issue.code,
            detected_count=detected_count,
            domain_scope=domain_scope,
            recurrence_window_count=recent_count,
            blast_radius_accumulated=blast_accum,
            security_accumulated=security_accum,
            trend_state=signature_profile.get("trend_state") or "new",
            trend_delta=int(signature_profile.get("trend_delta") or 0),
            signature_repeat_count=recent_count,
            learning_success_rate=learning.get("success_rate"),
            learning_validation_rate=learning.get("validation_rate"),
            recent_failed_executions=int(learning.get("recent_failed_executions") or 0),
            rolled_back_count=int(learning.get("rolled_back_count") or 0),
            learning_confidence_adjustment=learning.get("confidence_adjustment"),
            source_trust_level=trust.get("source_trust_level") or "internal",
            instruction_authority=bool(trust.get("instruction_authority")),
            secret_exposure_risk=trust.get("secret_exposure_risk"),
        )
        cadence_seconds = cadence_for_recommendation(
            policy,
            priority_score=int(decision.priority_score or 0),
            recommendation=decision.recommendation,
            recurrence_window_count=recent_count,
        )
        if str(getattr(decision, "trend_state", "new") or "new").lower() == "rising":
            cadence_seconds = max(20, cadence_seconds - 10)
        row, meta = governance.upsert_detection(
            issue=issue,
            decision=decision,
            finding=finding,
            trace_id=trace_id,
            domain_scope=domain_scope,
            cadence_seconds=cadence_seconds,
            signature_profile=signature_profile,
        )
        max_priority = max(max_priority, int(decision.priority_score or 0))
        priority_total += int(decision.priority_score or 0)
        recommendation_buckets[decision.recommendation] = recommendation_buckets.get(decision.recommendation, 0) + 1
        admin_recommendation_buckets[decision.admin_recommendation] = admin_recommendation_buckets.get(decision.admin_recommendation, 0) + 1
        trend_buckets[decision.trend_state] = trend_buckets.get(decision.trend_state, 0) + 1
        domain_buckets[domain_scope] = domain_buckets.get(domain_scope, 0) + 1
        if meta.get("created"):
            created += 1
            touched += 1
        elif meta.get("suppressed"):
            suppressed += 1
        else:
            touched += 1
        if row and getattr(row, "id", None):
            touched_ids.append(str(row.id))

    rows = db.execute(select(EvolutionProposal)).scalars().all()
    queue_rows = [r for r in rows if str(getattr(r, "status", "") or "").lower() in {"awaiting_master_approval", "approved"}]

    def _priority_for_row(r: EvolutionProposal) -> int:
        try:
            return int(getattr(r, "last_priority_score", 0) or 0)
        except Exception:
            return 0

    def _decision_for_row(r: EvolutionProposal) -> Dict[str, Any]:
        raw = getattr(r, "decision_json", None)
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    top_rows = sorted(queue_rows or rows, key=lambda r: (_priority_for_row(r), int(getattr(r, "updated_at", 0) or 0)), reverse=True)[:5]
    top_queue = [
        {
            "id": r.id,
            "code": r.code,
            "title": r.title,
            "status": r.status,
            "domain_scope": getattr(r, "domain_scope", None),
            "priority": int(getattr(r, "last_priority_score", 0) or 0),
            "recommendation": getattr(r, "last_recommendation", None),
            "admin_recommendation": (_decision_for_row(r) or {}).get("admin_recommendation"),
            "trend_state": (_decision_for_row(r) or {}).get("trend_state"),
            "cadence_seconds": int(getattr(r, "last_cadence_seconds", 0) or 0),
        }
        for r in top_rows
    ]
    avg_priority = round(priority_total / len(issues)) if issues else 0
    next_interval_suggested = 120
    if top_queue:
        next_interval_suggested = min(int(item.get("cadence_seconds") or 120) for item in top_queue)
    governance.record_cycle_log(
        trace_id=trace_id,
        findings=len(findings_payload),
        classified=len(issues),
        proposals_touched=touched,
        proposals_created=created,
        proposals_suppressed=suppressed,
        max_priority_score=max_priority,
        avg_priority_score=avg_priority,
        next_interval_suggested_seconds=next_interval_suggested,
        recommendation_buckets={
            **recommendation_buckets,
            **{f"admin::{k}": v for k, v in admin_recommendation_buckets.items()},
            **{f"trend::{k}": v for k, v in trend_buckets.items()},
        },
        domain_buckets=domain_buckets,
        top_queue=top_queue,
    )

    return {
        "ok": True,
        "findings": len(findings_payload),
        "classified": len(issues),
        "proposals_touched": touched,
        "proposals_created": created,
        "proposals_suppressed": suppressed,
        "touch_cooldown_seconds": governance.touch_cooldown_seconds,
        "recurrence_window_seconds": governance.recurrence_window_seconds,
        "signature_stability_threshold": governance.signature_stability_threshold,
        "max_priority_score": max_priority,
        "avg_priority_score": avg_priority,
        "next_interval_suggested_seconds": next_interval_suggested,
        "recommendation_buckets": recommendation_buckets,
        "admin_recommendation_buckets": admin_recommendation_buckets,
        "trend_buckets": trend_buckets,
        "domain_buckets": domain_buckets,
        "touched_ids": touched_ids[:25],
        "trace_id": trace_id,
        "top_queue": top_queue,
    }
