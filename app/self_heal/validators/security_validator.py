from __future__ import annotations

from .base import (
    BaseSemanticValidator,
    SemanticValidationContext,
    SemanticValidationResult,
    mutable_action,
    touched_security_surface,
    validation_marker_present,
    rollback_material_present,
    permission_sensitive_paths,
)
from app.self_heal.credential_scope import is_protected_branch


class SecuritySemanticValidator(BaseSemanticValidator):
    domain = "security"

    def validate(self, ctx: SemanticValidationContext) -> SemanticValidationResult:
        trust = ctx.trust or {}
        reasons: list[str] = []
        required_review = False
        blocks = False
        severity = "low"

        level = str(trust.get("source_trust_level") or "untrusted").lower()
        if level in {"external", "untrusted"} and bool(trust.get("instruction_authority")):
            reasons.append("external_or_untrusted_cannot_hold_instruction_authority")
            blocks = True
            severity = "critical"

        risk = float(trust.get("secret_exposure_risk") or 0.0)
        if risk >= 0.65:
            reasons.append("secret_exposure_risk_high")
            blocks = True
            severity = "critical"
        elif risk >= 0.35:
            reasons.append("secret_exposure_risk_medium")
            required_review = True
            severity = "high"

        if is_protected_branch(ctx.target_branch):
            reasons.append("protected_target_branch")
            blocks = True
            severity = "critical"

        security_surface = touched_security_surface(ctx)
        if security_surface:
            required_review = True
            if severity == "low":
                severity = "high"
            reasons.append("security_surface_touched")

        if security_surface and not validation_marker_present(ctx):
            reasons.append("security_surface_changed_without_validation_marker")
            blocks = True
            severity = "critical"

        if mutable_action(ctx) and security_surface and not rollback_material_present(ctx):
            reasons.append("security_surface_missing_rollback_material")
            blocks = True
            severity = "critical"

        if permission_sensitive_paths(ctx):
            required_review = True
            if "permission_sensitive_paths_touched" not in reasons:
                reasons.append("permission_sensitive_paths_touched")
            if severity == "low":
                severity = "high"

        return SemanticValidationResult(
            domain="security",
            passed=not blocks,
            severity=severity,
            reasons=reasons,
            required_review=required_review or blocks,
            blocks_execution=blocks,
            rollback_required=blocks or (required_review and security_surface),
            score_delta=(-22.0 if blocks else (-8.0 if required_review else 0.0)),
        )
