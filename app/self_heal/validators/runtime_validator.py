from __future__ import annotations

from .base import (
    BaseSemanticValidator,
    SemanticValidationContext,
    SemanticValidationResult,
    mutable_action,
    rollback_material_present,
    touched_runtime_surface,
    target_is_selfheal_branch,
    validation_marker_present,
    artifact_path,
)
from app.self_heal.credential_scope import is_branch_allowed, is_protected_branch


class RuntimeSemanticValidator(BaseSemanticValidator):
    domain = "runtime"

    def validate(self, ctx: SemanticValidationContext) -> SemanticValidationResult:
        reasons: list[str] = []
        required_review = False
        blocks = False
        severity = "low"
        action = str(ctx.action or "").lower().strip()
        target = str(ctx.target_branch or "").strip()

        if target and is_protected_branch(target):
            reasons.append("protected_target_branch")
            blocks = True
            severity = "critical"
        elif target and not is_branch_allowed(target):
            reasons.append("target_branch_outside_allowlist")
            blocks = True
            severity = "high"
        elif target and not target_is_selfheal_branch(ctx):
            required_review = True
            reasons.append("target_branch_outside_selfheal_prefixes")
            severity = "medium"

        if mutable_action(ctx) and not rollback_material_present(ctx):
            reasons.append("rollback_material_required_for_mutating_action")
            blocks = True
            severity = "critical"

        if mutable_action(ctx) and not target:
            reasons.append("target_branch_required_for_mutating_action")
            blocks = True
            severity = "high" if severity != "critical" else severity

        if action in {"propose_schema_patch", "pr_only"} and not artifact_path(ctx):
            required_review = True
            reasons.append("artifact_path_missing_for_execution_action")
            if severity == "low":
                severity = "medium"

        if touched_runtime_surface(ctx):
            required_review = True
            reasons.append("runtime_surface_touched")
            if severity == "low":
                severity = "high"

        if action == "propose_schema_patch" and not validation_marker_present(ctx):
            required_review = True
            reasons.append("schema_patch_missing_validation_marker")
            if severity == "low":
                severity = "medium"

        return SemanticValidationResult(
            domain="runtime",
            passed=not blocks,
            severity=severity,
            reasons=reasons,
            required_review=required_review or blocks,
            blocks_execution=blocks,
            rollback_required=mutable_action(ctx) or blocks,
            score_delta=(-18.0 if blocks else (-5.0 if required_review else 0.0)),
        )
