from __future__ import annotations

from .base import (
    BaseSemanticValidator,
    SemanticValidationContext,
    SemanticValidationResult,
    touched_auth_surface,
    validation_marker_present,
    rollback_material_present,
    mutable_action,
    permission_sensitive_paths,
)


class AuthSemanticValidator(BaseSemanticValidator):
    domain = "auth"

    def validate(self, ctx: SemanticValidationContext) -> SemanticValidationResult:
        reasons: list[str] = []
        required_review = False
        blocks = False
        severity = "low"

        auth_surface = touched_auth_surface(ctx)
        if auth_surface:
            required_review = True
            severity = "high"
            reasons.append("auth_surface_touched")

        if auth_surface and not validation_marker_present(ctx):
            blocks = True
            severity = "critical"
            reasons.append("auth_surface_changed_without_validation_marker")

        if auth_surface and mutable_action(ctx) and not rollback_material_present(ctx):
            blocks = True
            severity = "critical"
            reasons.append("auth_surface_missing_rollback_material")

        if permission_sensitive_paths(ctx):
            required_review = True
            if "permission_sensitive_paths_touched" not in reasons:
                reasons.append("permission_sensitive_paths_touched")
            if severity == "low":
                severity = "high"

        return SemanticValidationResult(
            domain="auth",
            passed=not blocks,
            severity=severity,
            reasons=reasons,
            required_review=required_review or blocks,
            blocks_execution=blocks,
            rollback_required=required_review or blocks,
            score_delta=(-18.0 if blocks else (-8.0 if required_review else 0.0)),
        )
