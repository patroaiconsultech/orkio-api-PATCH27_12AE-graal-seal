from __future__ import annotations

from .base import BaseSemanticValidator, SemanticValidationContext, SemanticValidationResult


class BillingSemanticValidator(BaseSemanticValidator):
    domain = "billing"

    def validate(self, ctx: SemanticValidationContext) -> SemanticValidationResult:
        reasons: list[str] = []
        required_review = False
        blocks = False
        severity = "low"
        domain = str(ctx.domain_scope or "").lower()
        result = ctx.result or {}
        serialized = str(result).lower()

        if domain == "billing":
            required_review = True
            severity = "high"
            reasons.append("billing_domain_requires_review")

        if any(token in serialized for token in ["charge", "invoice", "wallet", "payment"]):
            required_review = True
            reasons.append("billing_side_effect_detected")

        if required_review and result.get("wallet_effect") is None:
            reasons.append("wallet_effect_missing")
            if severity == "low":
                severity = "medium"

        return SemanticValidationResult(
            domain="billing",
            passed=not blocks,
            severity=severity,
            reasons=reasons,
            required_review=required_review,
            blocks_execution=blocks,
            rollback_required=required_review,
            score_delta=(-8.0 if required_review else 0.0),
        )
