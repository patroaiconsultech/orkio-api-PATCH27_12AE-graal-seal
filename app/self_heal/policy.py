from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict


POLICY_VERSION = "2026.04.22-governed-priority-v6"


@dataclass
class PolicyDecision:
    action: str
    reason: str
    risk_score: int
    impact_score: int
    confidence_score: int
    urgency_score: int
    blast_radius_score: int
    security_score: int
    priority_score: int
    owner_review_required: bool
    execution_allowed: bool
    lane: str
    recommendation: str
    trend_state: str = "new"
    trend_delta: int = 0
    signature_repeat_count: int = 1
    admin_recommendation: str = "review_only"
    admin_execute_candidate: bool = False
    suppression_hint: str = "none"
    operator_suggestion: str = "hold"
    operator_confidence_score: int = 0
    operator_rationale: str = ""
    learning_applied: bool = False
    learning_confidence_adjustment: int = 0
    learning_policy_shift: str = "none"
    source_trust_level: str = "internal"
    instruction_authority: bool = False
    secret_exposure_risk: float = 0.0
    semantic_validation_summary: Dict[str, Any] | None = None
    required_review_domains: list[str] | None = None
    policy_version: str = POLICY_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SelfHealPolicy:
    def __init__(self, logger=None):
        self.logger = logger

    def decide(
        self,
        severity: str,
        category: str,
        code: str = "",
        detected_count: int = 1,
        *,
        domain_scope: str = "general",
        recurrence_window_count: int = 1,
        blast_radius_accumulated: int = 0,
        security_accumulated: int = 0,
        trend_state: str = "new",
        trend_delta: int = 0,
        signature_repeat_count: int = 1,
        learning_success_rate: Any = None,
        learning_validation_rate: Any = None,
        recent_failed_executions: int = 0,
        rolled_back_count: int = 0,
        learning_confidence_adjustment: Any = None,
        source_trust_level: str = "internal",
        instruction_authority: bool = False,
        secret_exposure_risk: Any = 0.0,
        semantic_validation_summary: Dict[str, Any] | None = None,
        required_review_domains: list[str] | None = None,
    ) -> PolicyDecision:
        severity = (severity or "LOW").upper()
        category = (category or "runtime").lower()
        code = (code or "").upper()
        domain_scope = (domain_scope or "general").lower()
        detected_count = max(1, int(detected_count or 1))
        recurrence_window_count = max(1, int(recurrence_window_count or 1))
        blast_radius_accumulated = max(0, int(blast_radius_accumulated or 0))
        security_accumulated = max(0, int(security_accumulated or 0))
        trend_state = str(trend_state or "new").lower()
        signature_repeat_count = max(1, int(signature_repeat_count or 1))
        trend_delta = int(trend_delta or 0)
        source_trust_level = str(source_trust_level or "internal").strip().lower() or "internal"
        instruction_authority = bool(instruction_authority) if source_trust_level in {"trusted", "internal"} else False
        try:
            secret_exposure_risk = max(0.0, min(1.0, float(secret_exposure_risk or 0.0)))
        except Exception:
            secret_exposure_risk = 0.0
        semantic_validation_summary = semantic_validation_summary or {}
        required_review_domains = [str(x or "").strip().lower() for x in (required_review_domains or semantic_validation_summary.get("required_review_domains") or []) if str(x or "").strip()]
        semantic_blocked = bool(semantic_validation_summary.get("blocks_execution"))
        semantic_score_delta = 0
        try:
            semantic_score_delta = int(round(float(semantic_validation_summary.get("score_delta") or 0.0)))
        except Exception:
            semantic_score_delta = 0

        action, reason, lane = self._action_for(
            severity=severity,
            category=category,
            code=code,
            domain_scope=domain_scope,
        )
        risk_score = self._risk_score(severity=severity, category=category, code=code, domain_scope=domain_scope)
        impact_score = self._impact_score(action=action, category=category, code=code, domain_scope=domain_scope)
        confidence_score = self._confidence_score(code=code, category=category, domain_scope=domain_scope)
        urgency_score = self._urgency_score(
            severity=severity,
            detected_count=detected_count,
            recurrence_window_count=recurrence_window_count,
            trend_state=trend_state,
            trend_delta=trend_delta,
        )
        blast_radius_score = self._blast_radius_score(
            action=action,
            category=category,
            code=code,
            domain_scope=domain_scope,
            blast_radius_accumulated=blast_radius_accumulated,
        )
        security_score = self._security_score(
            action=action,
            category=category,
            code=code,
            domain_scope=domain_scope,
            security_accumulated=security_accumulated,
        )
        priority_score = min(
            100,
            round(
                (risk_score * 0.24)
                + (impact_score * 0.16)
                + (urgency_score * 0.16)
                + (confidence_score * 0.10)
                + (blast_radius_score * 0.18)
                + (security_score * 0.16)
            ),
        )

        if recurrence_window_count >= 4:
            priority_score = min(100, priority_score + 6)
        if domain_scope in {"security", "auth", "billing"} and priority_score >= 60:
            priority_score = min(100, priority_score + 4)
        if trend_state == "rising":
            priority_score = min(100, priority_score + 8)
        elif trend_state == "cooling":
            priority_score = max(0, priority_score - 4)
        if signature_repeat_count >= 6 and trend_state in {"stable", "cooling"}:
            priority_score = max(0, priority_score - 2)

        learning_delta = self._resolved_learning_adjustment(
            learning_success_rate=learning_success_rate,
            learning_validation_rate=learning_validation_rate,
            recent_failed_executions=recent_failed_executions,
            rolled_back_count=rolled_back_count,
            explicit_adjustment=learning_confidence_adjustment,
        )
        learning_policy_shift = "none"
        learning_applied = learning_delta != 0 or any(
            int(v or 0) > 0 for v in [recent_failed_executions, rolled_back_count]
        ) or learning_success_rate is not None or learning_validation_rate is not None
        if learning_delta:
            confidence_score = max(0, min(100, confidence_score + int(learning_delta)))
            priority_score = max(0, min(100, priority_score + round(int(learning_delta) * 0.45)))
            learning_policy_shift = "promote" if learning_delta > 0 else "degrade"
        if int(recent_failed_executions or 0) >= 2:
            confidence_score = max(0, confidence_score - 8)
            priority_score = min(100, priority_score + 4)
            learning_policy_shift = "degrade"
        if int(rolled_back_count or 0) >= 2:
            confidence_score = max(0, confidence_score - 6)
            learning_policy_shift = "degrade"

        owner_review_required = action != "ignore"
        execution_allowed = action in {"propose_schema_patch", "pr_only"}
        recommendation = self._recommendation_for(
            action=action,
            priority_score=priority_score,
            blast_radius_score=blast_radius_score,
            security_score=security_score,
            recurrence_window_count=recurrence_window_count,
            domain_scope=domain_scope,
            trend_state=trend_state,
        )
        admin_recommendation, admin_execute_candidate = self._admin_recommendation_for(
            action=action,
            execution_allowed=execution_allowed,
            priority_score=priority_score,
            blast_radius_score=blast_radius_score,
            security_score=security_score,
            confidence_score=confidence_score,
            trend_state=trend_state,
            domain_scope=domain_scope,
        )

        if learning_policy_shift == "degrade":
            if admin_execute_candidate:
                admin_execute_candidate = False
            if admin_recommendation == "execute_candidate":
                admin_recommendation = "review_then_execute"
            elif admin_recommendation == "review_then_execute":
                admin_recommendation = "review_only"
            if recommendation == "review_now" and confidence_score < 70:
                recommendation = "review_soon"
            elif recommendation == "review_soon" and confidence_score < 58:
                recommendation = "observe_with_guard"
        elif learning_policy_shift == "promote":
            if recommendation == "review_soon" and confidence_score >= 90 and priority_score >= 78:
                recommendation = "review_now"
            if admin_recommendation == "review_only" and action == "propose_schema_patch" and confidence_score >= 92 and security_score <= 70:
                admin_recommendation = "review_then_execute"

        if source_trust_level in {"external", "untrusted"}:
            confidence_score = max(0, confidence_score - 18)
            priority_score = max(0, priority_score - 6)
            if instruction_authority:
                confidence_score = max(0, confidence_score - 12)
                priority_score = max(0, priority_score - 8)
                admin_execute_candidate = False
                admin_recommendation = "review_only"
        if secret_exposure_risk >= 0.65:
            confidence_score = max(0, confidence_score - 24)
            priority_score = max(0, priority_score - 10)
            admin_execute_candidate = False
            admin_recommendation = "review_only"
            recommendation = "review_now"
        elif secret_exposure_risk >= 0.35:
            confidence_score = max(0, confidence_score - 10)
            priority_score = min(100, priority_score + 4)
            if admin_recommendation == "execute_candidate":
                admin_recommendation = "review_then_execute"
                admin_execute_candidate = False

        if semantic_score_delta:
            confidence_score = max(0, min(100, confidence_score + semantic_score_delta))
            priority_score = max(0, min(100, priority_score + round(semantic_score_delta * 0.35)))
        if semantic_blocked:
            admin_execute_candidate = False
            admin_recommendation = "review_only"
            recommendation = "review_now"
        elif required_review_domains and admin_recommendation == "execute_candidate":
            admin_execute_candidate = False
            admin_recommendation = "review_then_execute"

        operator_suggestion, operator_confidence_score, operator_rationale = self._operator_guidance_for(
            action=action,
            execution_allowed=execution_allowed,
            priority_score=priority_score,
            blast_radius_score=blast_radius_score,
            security_score=security_score,
            confidence_score=confidence_score,
            admin_recommendation=admin_recommendation,
            admin_execute_candidate=admin_execute_candidate,
            trend_state=trend_state,
            domain_scope=domain_scope,
        )
        suppression_hint = self._suppression_hint_for(
            action=action,
            recommendation=recommendation,
            trend_state=trend_state,
            signature_repeat_count=signature_repeat_count,
            priority_score=priority_score,
        )

        return PolicyDecision(
            action=action,
            reason=reason,
            risk_score=risk_score,
            impact_score=impact_score,
            confidence_score=confidence_score,
            urgency_score=urgency_score,
            blast_radius_score=blast_radius_score,
            security_score=security_score,
            priority_score=priority_score,
            owner_review_required=owner_review_required,
            execution_allowed=execution_allowed,
            lane=lane,
            recommendation=recommendation,
            trend_state=trend_state,
            trend_delta=trend_delta,
            signature_repeat_count=signature_repeat_count,
            admin_recommendation=admin_recommendation,
            admin_execute_candidate=admin_execute_candidate,
            suppression_hint=suppression_hint,
            operator_suggestion=operator_suggestion,
            operator_confidence_score=operator_confidence_score,
            operator_rationale=operator_rationale,
            learning_applied=learning_applied,
            learning_confidence_adjustment=int(learning_delta),
            learning_policy_shift=learning_policy_shift,
            source_trust_level=source_trust_level,
            instruction_authority=instruction_authority,
            secret_exposure_risk=float(secret_exposure_risk or 0.0),
            semantic_validation_summary=semantic_validation_summary,
            required_review_domains=required_review_domains,
        )

    def describe(self) -> Dict[str, Any]:
        return {
            "version": POLICY_VERSION,
            "mode": "governed",
            "master_admin_required": True,
            "lanes": [
                {
                    "lane": "autofix_safe",
                    "notes": "Known and constrained changes, still gated by Admin Master before execution.",
                    "actions": ["propose_schema_patch"],
                },
                {
                    "lane": "review_required",
                    "notes": "Human-reviewed engineering work only; opens guarded proposal PRs.",
                    "actions": ["pr_only"],
                },
                {
                    "lane": "observe_only",
                    "notes": "Observation or simulation only, without automatic execution.",
                    "actions": ["simulate", "ignore"],
                },
            ],
            "severity_weights": {
                "LOW": 20,
                "MEDIUM": 50,
                "HIGH": 75,
                "CRITICAL": 95,
            },
            "category_weights": {
                "schema": 18,
                "realtime": 16,
                "runtime": 20,
                "contract": 10,
            },
            "domain_sensitivity": {
                "security": 16,
                "billing": 14,
                "auth": 14,
                "realtime": 10,
                "schema": 12,
            },
            "score_dimensions": [
                "risk_score",
                "impact_score",
                "confidence_score",
                "urgency_score",
                "blast_radius_score",
                "security_score",
                "priority_score",
            ],
            "recommendations": [
                "review_now",
                "review_soon",
                "observe_with_guard",
                "informational_only",
            ],
            "admin_recommendations": [
                "execute_candidate",
                "review_then_execute",
                "review_only",
                "observe_only",
                "blocked_sensitive_domain",
            ],
            "trend_states": ["new", "rising", "stable", "cooling"],
            "learning_effects": [
                "confidence_adjustment",
                "policy_shift",
                "operator_guidance",
                "admin_recommendation",
            ],
        }

    def cadence_for_priority(self, priority_score: int, recommendation: str = "", recurrence_window_count: int = 1) -> int:
        n = max(0, int(priority_score or 0))
        recommendation = (recommendation or "").lower()
        recurrence_window_count = max(1, int(recurrence_window_count or 1))
        if recommendation == "review_now":
            base = 20 if n >= 85 else 30
        elif recommendation == "review_soon":
            base = 45 if n >= 70 else 60
        elif recommendation == "observe_with_guard":
            base = 90
        else:
            base = 120
        if recurrence_window_count >= 5:
            base = max(20, base - 15)
        elif recurrence_window_count >= 3:
            base = max(20, base - 10)
        return base

    def _action_for(self, severity: str, category: str, code: str, domain_scope: str) -> tuple[str, str, str]:
        if code in {"SCHEMA_MISSING_TABLE", "SCHEMA_MISSING_COLUMN"}:
            return (
                "propose_schema_patch",
                "known schema drift should generate a controlled schema patch proposal",
                "autofix_safe",
            )
        if domain_scope in {"security", "billing", "auth"} and severity in {"HIGH", "CRITICAL"}:
            return ("pr_only", "sensitive domain requires human-reviewed promotion", "review_required")
        if code in {"REALTIME_DUPLICATION_RISK", "REALTIME_SCHEMA_INCOMPLETE"}:
            return (
                "simulate",
                "realtime issues remain simulation-only until broader runtime hardening is approved",
                "observe_only",
            )
        if severity == "CRITICAL":
            return ("pr_only", "critical issues require human-reviewed promotion", "review_required")
        if severity == "HIGH":
            return ("pr_only", "high severity uses supervised patch flow only", "review_required")
        if severity == "MEDIUM":
            return ("simulate", "medium severity remains simulation-first", "observe_only")
        return ("ignore", "low severity informational only", "observe_only")

    def _risk_score(self, *, severity: str, category: str, code: str, domain_scope: str) -> int:
        severity_weights = {"LOW": 20, "MEDIUM": 50, "HIGH": 75, "CRITICAL": 95}
        category_weights = {"schema": 18, "realtime": 16, "runtime": 20, "contract": 10}
        domain_weights = {"security": 16, "billing": 14, "auth": 14, "realtime": 10, "schema": 12}
        code_bonus = 0
        if code in {"SCHEMA_MISSING_TABLE", "SCHEMA_MISSING_COLUMN"}:
            code_bonus += 8
        if code in {"REALTIME_SCHEMA_INCOMPLETE"}:
            code_bonus += 6
        return min(100, severity_weights.get(severity, 20) + category_weights.get(category, 8) + domain_weights.get(domain_scope, 0) + code_bonus)

    def _impact_score(self, *, action: str, category: str, code: str, domain_scope: str) -> int:
        base = {"propose_schema_patch": 82, "pr_only": 70, "simulate": 38, "ignore": 10}.get(action, 20)
        if category == "runtime":
            base += 5
        if category == "schema":
            base += 8
        if code == "REALTIME_DUPLICATION_RISK":
            base += 4
        if domain_scope in {"billing", "auth"}:
            base += 6
        if domain_scope == "security":
            base += 8
        return min(100, base)

    def _confidence_score(self, *, code: str, category: str, domain_scope: str) -> int:
        if code in {"SCHEMA_MISSING_TABLE", "SCHEMA_MISSING_COLUMN"}:
            return 94
        if code in {"REALTIME_SCHEMA_INCOMPLETE"}:
            return 82
        if code in {"REALTIME_DUPLICATION_RISK"}:
            return 72
        if category == "contract":
            return 88
        if domain_scope in {"billing", "auth"}:
            return 78
        return 64

    def _urgency_score(self, *, severity: str, detected_count: int, recurrence_window_count: int, trend_state: str = "new", trend_delta: int = 0) -> int:
        severity_floor = {"LOW": 12, "MEDIUM": 40, "HIGH": 68, "CRITICAL": 88}.get(severity, 12)
        repeat_bonus = min(12, max(0, detected_count - 1) * 2)
        recurrence_bonus = min(14, max(0, recurrence_window_count - 1) * 3)
        trend_bonus = 0
        if trend_state == "rising":
            trend_bonus = 8 if int(trend_delta or 0) >= 10 else 5
        elif trend_state == "cooling":
            trend_bonus = -4
        return min(100, max(0, severity_floor + repeat_bonus + recurrence_bonus + trend_bonus))

    def _blast_radius_score(self, *, action: str, category: str, code: str, domain_scope: str, blast_radius_accumulated: int) -> int:
        base = 18
        if action == "propose_schema_patch":
            base = 74
        elif action == "pr_only":
            base = 66
        elif action == "simulate":
            base = 28
        if category == "runtime":
            base += 10
        elif category == "schema":
            base += 14
        elif category == "realtime":
            base += 12
        if domain_scope in {"billing", "auth"}:
            base += 8
        if domain_scope == "security":
            base += 12
        if code in {"SCHEMA_MISSING_TABLE", "SCHEMA_MISSING_COLUMN"}:
            base += 8
        if code in {"REALTIME_DUPLICATION_RISK", "REALTIME_SCHEMA_INCOMPLETE"}:
            base += 5
        accum_bonus = min(14, max(0, blast_radius_accumulated) // 25)
        return min(100, base + accum_bonus)

    def _security_score(self, *, action: str, category: str, code: str, domain_scope: str, security_accumulated: int) -> int:
        base = 10
        if domain_scope == "security":
            base = 78
        elif domain_scope in {"auth", "billing"}:
            base = 62
        elif category == "contract":
            base = 44
        elif category == "runtime":
            base = 28
        if action == "pr_only":
            base += 6
        if code in {"SCHEMA_MISSING_TABLE", "SCHEMA_MISSING_COLUMN"}:
            base += 4
        accum_bonus = min(12, max(0, security_accumulated) // 25)
        return min(100, base + accum_bonus)

    def _resolved_learning_adjustment(
        self,
        *,
        learning_success_rate: Any = None,
        learning_validation_rate: Any = None,
        recent_failed_executions: int = 0,
        rolled_back_count: int = 0,
        explicit_adjustment: Any = None,
    ) -> int:
        if explicit_adjustment is not None:
            try:
                return max(-24, min(18, int(explicit_adjustment or 0)))
            except Exception:
                return 0
        delta = 0
        try:
            sr = None if learning_success_rate is None else float(learning_success_rate)
        except Exception:
            sr = None
        try:
            vr = None if learning_validation_rate is None else float(learning_validation_rate)
        except Exception:
            vr = None
        recent_failed_executions = max(0, int(recent_failed_executions or 0))
        rolled_back_count = max(0, int(rolled_back_count or 0))
        if sr is not None:
            if sr >= 92:
                delta += 4
            elif sr >= 82:
                delta += 2
            elif sr < 55:
                delta -= 6
            elif sr < 70:
                delta -= 3
        if vr is not None:
            if vr >= 95:
                delta += 4
            elif vr >= 85:
                delta += 2
            elif vr < 60:
                delta -= 8
            elif vr < 75:
                delta -= 4
        delta -= min(8, recent_failed_executions * 3)
        delta -= min(6, rolled_back_count * 2)
        return max(-24, min(18, int(delta)))


    def _recommendation_for(
        self,
        *,
        action: str,
        priority_score: int,
        blast_radius_score: int,
        security_score: int,
        recurrence_window_count: int,
        domain_scope: str,
        trend_state: str = "new",
    ) -> str:
        if action == "ignore":
            return "informational_only"
        if trend_state == "rising" and priority_score >= 70:
            return "review_now"
        if domain_scope in {"security", "billing", "auth"} and (security_score >= 65 or recurrence_window_count >= 3):
            return "review_now"
        if priority_score >= 82 or blast_radius_score >= 82:
            return "review_now"
        if priority_score >= 58 or recurrence_window_count >= 2:
            return "review_soon"
        return "observe_with_guard"

    def _admin_recommendation_for(
        self,
        *,
        action: str,
        execution_allowed: bool,
        priority_score: int,
        blast_radius_score: int,
        security_score: int,
        confidence_score: int,
        trend_state: str,
        domain_scope: str,
    ) -> tuple[str, bool]:
        if action == "ignore":
            return "observe_only", False
        if not execution_allowed:
            return ("review_only" if priority_score >= 60 or trend_state == "rising" else "observe_only"), False
        if domain_scope in {"security", "auth"} and security_score >= 70:
            return "blocked_sensitive_domain", False
        if trend_state == "rising" and priority_score >= 78:
            return "review_then_execute", False
        if (
            action == "propose_schema_patch"
            and confidence_score >= 90
            and priority_score >= 80
            and blast_radius_score <= 90
            and security_score <= 70
            and trend_state in {"stable", "cooling", "new"}
        ):
            return "execute_candidate", True
        if priority_score >= 82 and security_score <= 82:
            return "review_then_execute", False
        return "review_only", False

    def _operator_guidance_for(
        self,
        *,
        action: str,
        execution_allowed: bool,
        priority_score: int,
        blast_radius_score: int,
        security_score: int,
        confidence_score: int,
        admin_recommendation: str,
        admin_execute_candidate: bool,
        trend_state: str,
        domain_scope: str,
    ) -> tuple[str, int, str]:
        action = (action or "").lower()
        admin_recommendation = (admin_recommendation or "review_only").lower()
        trend_state = (trend_state or "new").lower()
        base_by_action = {
            "propose_schema_patch": 92,
            "pr_only": 74,
            "simulate": 48,
            "ignore": 35,
        }
        safety_headroom = max(0, 100 - max(blast_radius_score, security_score))
        confidence = round(
            (base_by_action.get(action, 40) * 0.40)
            + (max(0, min(100, confidence_score)) * 0.35)
            + (safety_headroom * 0.15)
            + (max(0, min(100, priority_score)) * 0.10)
        )
        confidence = max(0, min(100, int(confidence)))

        if action == "ignore":
            return "reject", min(90, confidence), "finding informacional sem trilha operacional relevante"
        if action == "simulate":
            if trend_state == "rising" or priority_score >= 72:
                return "hold", max(confidence, 55), "simulação recorrente ou aquecendo; melhor segurar e observar"
            return "hold", confidence, "simulação sem automação; manter em observação governada"
        if admin_execute_candidate and execution_allowed and action == "propose_schema_patch":
            return "approve_and_execute", max(confidence, 86), "patch conhecido e restrito, candidato a execução governada"
        if domain_scope in {"security", "auth"} and security_score >= 70:
            return "hold", max(confidence - 10, 40), "domínio sensível exige análise humana antes de qualquer promoção"
        if admin_recommendation == "blocked_sensitive_domain":
            return "hold", max(confidence - 8, 40), "domínio sensível bloqueado para execução direta"
        if admin_recommendation == "review_then_execute":
            return "approve_only", max(confidence, 68), "aprovar primeiro e executar depois da tua leitura final"
        if admin_recommendation == "review_only":
            return "approve_only", max(confidence, 62), "aprovação recomendada, mas execução separada"
        if priority_score < 30 and confidence_score < 50:
            return "reject", min(confidence, 48), "baixo valor operacional e baixa confiança para ocupar a fila"
        return "hold", confidence, "manter em hold até novo sinal ou decisão manual"

    def _suppression_hint_for(
        self,
        *,
        action: str,
        recommendation: str,
        trend_state: str,
        signature_repeat_count: int,
        priority_score: int,
    ) -> str:
        if action == "ignore":
            return "suppress_low_signal"
        if signature_repeat_count >= 4 and trend_state in {"stable", "cooling"} and recommendation in {"observe_with_guard", "informational_only", "review_soon"} and priority_score < 88:
            return "suppress_recurring_signature"
        return "none"
