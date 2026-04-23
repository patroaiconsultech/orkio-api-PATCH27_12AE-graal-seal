from __future__ import annotations

import json
from typing import Any, Dict

from app.self_heal.validators import (
    ArtifactSemanticValidator,
    AuthSemanticValidator,
    BillingSemanticValidator,
    RuntimeSemanticValidator,
    SecuritySemanticValidator,
    SemanticValidationContext,
)
from app.self_heal.validators.base import (
    action_name,
    artifact_extension,
    artifact_path,
    mutable_action,
    rollback_material_present,
    target_is_selfheal_branch,
    touched_auth_surface,
    touched_runtime_surface,
    touched_security_surface,
    validation_marker_present,
    validation_markers_summary,
)
from app.self_heal.credential_scope import is_branch_allowed, is_protected_branch


def _as_ctx(ctx: SemanticValidationContext | Dict[str, Any]) -> SemanticValidationContext:
    if isinstance(ctx, dict):
        return SemanticValidationContext(**ctx)
    return ctx


def _reduce_results(results: list[dict[str, Any]], *, signals: Dict[str, Any] | None = None) -> Dict[str, Any]:
    required_review_domains = [item["domain"] for item in results if item.get("required_review")]
    blocked_domains = [item["domain"] for item in results if item.get("blocks_execution")]
    rollback_required_domains = [item["domain"] for item in results if item.get("rollback_required")]
    score_delta = round(sum(float(item.get("score_delta") or 0.0) for item in results), 2)
    severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    max_severity = "low"
    for item in results:
        sev = str(item.get("severity") or "low").lower()
        if severity_order.get(sev, 0) > severity_order.get(max_severity, 0):
            max_severity = sev
    return {
        "ok": len(blocked_domains) == 0,
        "results": results,
        "required_review_domains": required_review_domains,
        "rollback_required_domains": rollback_required_domains,
        "blocked_domains": blocked_domains,
        "score_delta": score_delta,
        "severity": max_severity,
        "blocks_execution": len(blocked_domains) > 0,
        "signals": signals or {},
    }


def _derived_signals(ctx: SemanticValidationContext) -> Dict[str, Any]:
    result = ctx.result or {}
    rollback = ctx.rollback or {}
    validation = ctx.validation or {}
    action = action_name(ctx)
    path = artifact_path(ctx)
    ext = artifact_extension(ctx)
    has_branch_artifact = bool(result.get("branch"))
    has_commit_artifact = bool(result.get("commit"))
    has_pr_artifact = bool(result.get("pr"))
    rollback_present = rollback_material_present(ctx)
    touched_auth = touched_auth_surface(ctx)
    touched_security = touched_security_surface(ctx)
    touched_runtime = touched_runtime_surface(ctx)
    validation_present = validation_marker_present(ctx)
    target_branch = str(ctx.target_branch or "").strip()
    mutable = mutable_action(ctx)

    expected_ext_map = {
        "pr_only": {".md", ".txt", ".json"},
        "propose_schema_patch": {".py", ".sql", ".md"},
        "simulate": {".md", ".json", ".txt"},
    }
    expected_exts = expected_ext_map.get(action, set())
    artifact_action_mismatch = bool(path and expected_exts and ext not in expected_exts)

    protected_runtime_invariant_failed = False
    runtime_reasons: list[str] = []
    if mutable and not target_branch:
        protected_runtime_invariant_failed = True
        runtime_reasons.append("target_branch_missing")
    if target_branch and is_protected_branch(target_branch):
        protected_runtime_invariant_failed = True
        runtime_reasons.append("target_branch_protected")
    if target_branch and not is_branch_allowed(target_branch):
        protected_runtime_invariant_failed = True
        runtime_reasons.append("target_branch_outside_allowlist")
    if mutable and not rollback_present:
        protected_runtime_invariant_failed = True
        runtime_reasons.append("rollback_material_missing")
    if mutable and not validation_present and action in {"propose_schema_patch"}:
        protected_runtime_invariant_failed = True
        runtime_reasons.append("validation_marker_missing")
    if mutable and not has_branch_artifact:
        protected_runtime_invariant_failed = True
        runtime_reasons.append("branch_artifact_missing")
    if mutable and not has_commit_artifact:
        protected_runtime_invariant_failed = True
        runtime_reasons.append("commit_artifact_missing")
    if action == "pr_only" and not has_pr_artifact:
        protected_runtime_invariant_failed = True
        runtime_reasons.append("pr_artifact_missing")
    if mutable and not target_is_selfheal_branch(ctx):
        runtime_reasons.append("target_branch_not_selfheal_family")

    return {
        **validation_markers_summary(ctx),
        "target_branch": target_branch or None,
        "has_branch_artifact": has_branch_artifact,
        "has_commit_artifact": has_commit_artifact,
        "has_pr_artifact": has_pr_artifact,
        "rollback_material_present": rollback_present,
        "validation_marker_present": validation_present,
        "touched_auth_surface": touched_auth,
        "touched_security_surface": touched_security,
        "touched_runtime_surface": touched_runtime,
        "artifact_action_mismatch": artifact_action_mismatch,
        "expected_artifact_extensions": sorted(expected_exts),
        "protected_runtime_invariant_failed": protected_runtime_invariant_failed,
        "runtime_invariant_reasons": runtime_reasons,
    }


def run_semantic_validation(ctx: SemanticValidationContext | Dict[str, Any]) -> Dict[str, Any]:
    ctx = _as_ctx(ctx)
    validators = [
        SecuritySemanticValidator(),
        BillingSemanticValidator(),
        AuthSemanticValidator(),
        RuntimeSemanticValidator(),
        ArtifactSemanticValidator(),
    ]
    results = [validator.validate(ctx).as_dict() for validator in validators]
    return _reduce_results(results, signals=_derived_signals(ctx))


def _safe_json_text(value: Any) -> str:
    try:
        return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value or "")


def run_post_execution_semantic_integrity(ctx: SemanticValidationContext | Dict[str, Any]) -> Dict[str, Any]:
    ctx = _as_ctx(ctx)
    result = ctx.result or {}
    validation = ctx.validation or {}
    rollback = ctx.rollback or {}
    trust = ctx.trust or {}
    action = action_name(ctx)
    domain = str(ctx.domain_scope or "general").lower()
    signals = _derived_signals(ctx)
    serialized = _safe_json_text(result).lower()

    checks: Dict[str, Dict[str, Any]] = {}
    blocked_domains: list[str] = []
    required_review_domains: list[str] = []

    def register(domain_name: str, ok: bool, severity: str, reasons: list[str], required_review: bool = False) -> None:
        entry = {
            "ok": bool(ok),
            "severity": severity,
            "reasons": [str(r) for r in reasons if str(r)],
            "required_review": bool(required_review),
        }
        checks[domain_name] = entry
        if not ok:
            blocked_domains.append(domain_name)
        elif required_review:
            required_review_domains.append(domain_name)

    # Security / trust integrity
    security_reasons: list[str] = []
    security_ok = True
    if str(trust.get("source_trust_level") or "internal").lower() in {"external", "untrusted"} and bool(trust.get("instruction_authority")):
        security_ok = False
        security_reasons.append("unsafe_instruction_authority_after_execution")
    if float(trust.get("secret_exposure_risk") or 0.0) >= 0.65:
        security_ok = False
        security_reasons.append("secret_exposure_risk_high_after_execution")
    if signals.get("touched_security_surface") and not signals.get("validation_marker_present"):
        security_ok = False
        security_reasons.append("security_surface_without_validation_marker")
    if signals.get("touched_security_surface") and signals.get("mutable_action") and not signals.get("rollback_material_present"):
        security_ok = False
        security_reasons.append("security_surface_without_rollback_material")
    register("security", security_ok, "critical" if not security_ok else ("high" if signals.get("touched_security_surface") else "low"), security_reasons, required_review=(domain in {"security", "auth"} and security_ok))

    # Billing semantic integrity
    billing_reasons: list[str] = []
    billing_required_review = False
    billing_ok = True
    if domain == "billing" or any(token in serialized for token in ["charge", "invoice", "wallet", "payment"]):
        wallet_effect = result.get("wallet_effect")
        if wallet_effect is None:
            billing_required_review = True
            billing_reasons.append("billing_effect_requires_explicit_wallet_effect")
    register("billing", billing_ok, "medium" if billing_required_review else "low", billing_reasons, required_review=billing_required_review)

    # Auth semantic integrity
    auth_reasons: list[str] = []
    auth_required_review = False
    auth_ok = True
    if signals.get("touched_auth_surface"):
        auth_required_review = True
        if not signals.get("validation_marker_present"):
            auth_ok = False
            auth_reasons.append("auth_surface_changed_without_validation_marker")
        if signals.get("mutable_action") and not signals.get("rollback_material_present"):
            auth_ok = False
            auth_reasons.append("auth_surface_changed_without_rollback_material")
    register("auth", auth_ok, "critical" if not auth_ok else ("high" if auth_required_review else "low"), auth_reasons, required_review=auth_required_review and auth_ok)

    # Runtime semantic integrity
    runtime_reasons: list[str] = list(signals.get("runtime_invariant_reasons") or [])
    runtime_ok = not bool(signals.get("protected_runtime_invariant_failed"))
    if action == "propose_schema_patch" and not bool(validation.get("content_match")):
        runtime_ok = False
        runtime_reasons.append("content_match_failed_after_execution")
    if action == "propose_schema_patch" and not bool(validation.get("marker_present", True)):
        runtime_ok = False
        runtime_reasons.append("marker_missing_after_execution")
    if action == "pr_only" and not bool(result.get("pr")):
        runtime_ok = False
        runtime_reasons.append("pull_request_missing_after_execution")
    register("runtime", runtime_ok, "critical" if not runtime_ok else ("high" if signals.get("touched_runtime_surface") else "low"), runtime_reasons, required_review=(signals.get("touched_runtime_surface") and runtime_ok))

    # Artifact semantic integrity
    artifact_reasons: list[str] = []
    artifact_ok = True
    artifact_required_review = False
    artifact_path_value = str(signals.get("artifact_path") or "").strip()
    if action == "pr_only":
        if not artifact_path_value:
            artifact_ok = False
            artifact_reasons.append("artifact_path_missing")
    if action == "propose_schema_patch":
        classification = result.get("classification") or {}
        if not str((classification or {}).get("table") or "").strip():
            artifact_ok = False
            artifact_reasons.append("schema_patch_missing_table_metadata")
    if signals.get("artifact_action_mismatch"):
        artifact_required_review = True
        artifact_reasons.append("artifact_action_mismatch")
    register("artifact", artifact_ok, "high" if not artifact_ok else ("medium" if artifact_required_review else "low"), artifact_reasons, required_review=artifact_required_review)

    severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    overall_severity = "low"
    for entry in checks.values():
        sev = str(entry.get("severity") or "low").lower()
        if severity_order.get(sev, 0) > severity_order.get(overall_severity, 0):
            overall_severity = sev

    return {
        "ok": len(blocked_domains) == 0,
        "phase": "post_execution_semantic_integrity",
        "checks": checks,
        "signals": signals,
        "blocked_domains": blocked_domains,
        "required_review_domains": required_review_domains,
        "severity": overall_severity,
    }
