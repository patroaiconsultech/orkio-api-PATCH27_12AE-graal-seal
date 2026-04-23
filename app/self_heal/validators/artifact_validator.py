from __future__ import annotations

from .base import (
    BaseSemanticValidator,
    SemanticValidationContext,
    SemanticValidationResult,
    artifact_extension,
    artifact_path,
    target_is_selfheal_branch,
)


class ArtifactSemanticValidator(BaseSemanticValidator):
    domain = "artifact"

    def validate(self, ctx: SemanticValidationContext) -> SemanticValidationResult:
        reasons: list[str] = []
        required_review = False
        blocks = False
        severity = "low"
        target = str(ctx.target_branch or "").strip()
        action = str(ctx.action or "").lower().strip()
        path = artifact_path(ctx)
        ext = artifact_extension(ctx)

        if target and not target_is_selfheal_branch(ctx):
            required_review = True
            reasons.append("non_selfheal_target_branch")
            severity = "medium"

        if action == "propose_schema_patch" and not (ctx.validation or {}).get("marker_present", True):
            reasons.append("schema_marker_missing")
            blocks = True
            severity = "high"

        if action == "pr_only" and path and ext not in {".md", ".txt", ".json"}:
            required_review = True
            reasons.append("artifact_extension_unexpected_for_pr_only")
            if severity == "low":
                severity = "medium"

        return SemanticValidationResult(
            domain="artifact",
            passed=not blocks,
            severity=severity,
            reasons=reasons,
            required_review=required_review or blocks,
            blocks_execution=blocks,
            rollback_required=blocks,
            score_delta=(-10.0 if blocks else (-2.0 if required_review else 0.0)),
        )
