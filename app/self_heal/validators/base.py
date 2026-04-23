from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SemanticValidationContext(BaseModel):
    action: str = "unknown"
    domain_scope: str = "general"
    proposal_id: str | None = None
    target_branch: str | None = None
    source_branch: str | None = None
    changed_paths: list[str] = Field(default_factory=list)
    trust: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    rollback: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    proposal: dict[str, Any] = Field(default_factory=dict)


class SemanticValidationResult(BaseModel):
    domain: Literal["security", "billing", "auth", "runtime", "artifact"]
    passed: bool
    severity: Literal["low", "medium", "high", "critical"] = "low"
    reasons: list[str] = Field(default_factory=list)
    required_review: bool = False
    blocks_execution: bool = False
    rollback_required: bool = False
    score_delta: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()


AUTH_PATH_HINTS = (
    "/auth", "auth/", "rbac", "permission", "permissions", "identity", "session", "token", "oauth", "security.py"
)
SECURITY_PATH_HINTS = (
    "/security", "security/", "secret", "credential", "policy", "guard", "gate", "headers", "security.py"
)
RUNTIME_PATH_HINTS = (
    "self_heal", "runtime", "executor", "evolution_loop", "git_internal", "github_bridge", "worker", "job"
)
VALIDATION_MARKER_KEYS = ("content_match", "marker_present", "validated_at", "semantic_integrity_ok")
ROLLBACK_MATERIAL_KEYS = ("supported", "bundle_path", "restore_sha", "rollback_branch", "rollback_bundle", "artifact_path")
MUTATING_ACTIONS = {"propose_schema_patch", "pr_only", "simulate"}
SELFHEAL_BRANCH_PREFIXES = ("selfheal/", "sandbox/", "audit/")


class BaseSemanticValidator:
    domain: str = "runtime"

    def validate(self, ctx: SemanticValidationContext) -> SemanticValidationResult:
        raise NotImplementedError


def action_name(ctx: SemanticValidationContext) -> str:
    return str(ctx.action or "unknown").strip().lower()


def domain_name(ctx: SemanticValidationContext) -> str:
    return str(ctx.domain_scope or "general").strip().lower()


def artifact_path(ctx: SemanticValidationContext) -> str:
    result = ctx.result or {}
    candidate = str(result.get("artifact_path") or "").strip()
    if candidate:
        return candidate.replace("\\", "/")
    for item in ctx.changed_paths or []:
        value = str(item or "").strip()
        if value:
            return value.replace("\\", "/")
    return ""


def normalize_paths(ctx: SemanticValidationContext) -> list[str]:
    values: list[str] = []
    for candidate in list(ctx.changed_paths or []):
        value = str(candidate or "").strip()
        if value:
            values.append(value.replace("\\", "/"))
    ap = artifact_path(ctx)
    if ap and ap not in values:
        values.append(ap)
    return values


def path_touches(paths: list[str], hints: tuple[str, ...]) -> bool:
    lowered = " ".join(str(path or "").lower() for path in paths)
    return any(hint in lowered for hint in hints)


def touched_auth_surface(ctx: SemanticValidationContext) -> bool:
    return domain_name(ctx) == "auth" or path_touches(normalize_paths(ctx), AUTH_PATH_HINTS)


def touched_security_surface(ctx: SemanticValidationContext) -> bool:
    return domain_name(ctx) in {"security", "auth"} or path_touches(normalize_paths(ctx), SECURITY_PATH_HINTS)


def touched_runtime_surface(ctx: SemanticValidationContext) -> bool:
    return path_touches(normalize_paths(ctx), RUNTIME_PATH_HINTS)


def validation_marker_present(ctx: SemanticValidationContext) -> bool:
    validation = ctx.validation or {}
    if not validation:
        return False
    if bool(validation.get("content_match")) or bool(validation.get("marker_present")):
        return True
    return any(validation.get(key) not in (None, "", False) for key in VALIDATION_MARKER_KEYS)


def rollback_material_present(ctx: SemanticValidationContext) -> bool:
    rollback = ctx.rollback or {}
    result = ctx.result or {}
    if bool(rollback.get("supported")):
        return True
    if bool(result.get("rollback_bundle")):
        return True
    return any(rollback.get(key) not in (None, "", False) for key in ROLLBACK_MATERIAL_KEYS)


def mutable_action(ctx: SemanticValidationContext) -> bool:
    return action_name(ctx) in MUTATING_ACTIONS


def target_is_selfheal_branch(ctx: SemanticValidationContext) -> bool:
    target = str(ctx.target_branch or "").strip().lower()
    return bool(target) and any(target.startswith(prefix) for prefix in SELFHEAL_BRANCH_PREFIXES)


def permission_sensitive_paths(ctx: SemanticValidationContext) -> bool:
    return touched_auth_surface(ctx) or path_touches(normalize_paths(ctx), ("role", "roles", "acl", "access"))


def artifact_extension(ctx: SemanticValidationContext) -> str:
    path = artifact_path(ctx)
    if "." not in path:
        return ""
    return "." + path.rsplit(".", 1)[-1].lower()


def validation_markers_summary(ctx: SemanticValidationContext) -> dict[str, Any]:
    return {
        "action": action_name(ctx),
        "domain": domain_name(ctx),
        "paths": normalize_paths(ctx),
        "artifact_path": artifact_path(ctx),
        "artifact_extension": artifact_extension(ctx),
        "touched_auth_surface": touched_auth_surface(ctx),
        "touched_security_surface": touched_security_surface(ctx),
        "touched_runtime_surface": touched_runtime_surface(ctx),
        "permission_sensitive_paths": permission_sensitive_paths(ctx),
        "validation_marker_present": validation_marker_present(ctx),
        "rollback_material_present": rollback_material_present(ctx),
        "mutable_action": mutable_action(ctx),
        "target_is_selfheal_branch": target_is_selfheal_branch(ctx),
    }
