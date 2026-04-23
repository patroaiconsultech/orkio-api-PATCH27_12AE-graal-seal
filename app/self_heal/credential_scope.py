from __future__ import annotations

import os
from typing import Any, Dict

from pydantic import BaseModel

from app.self_heal.secret_broker import resolve_github_token, resolve_railway_token


class ScopedCredentialBundle(BaseModel):
    github_token_ref: str | None = None
    github_repo: str | None = None
    github_branch_allowlist: list[str] = []
    railway_token_ref: str | None = None
    ttl_seconds: int | None = None
    control_plane_only: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return self.model_dump()


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip().strip('"').strip("'")


def _split_csv(raw: str) -> list[str]:
    return [part.strip() for part in str(raw or "").split(",") if part.strip()]


def _default_token_ref() -> str:
    return _env("GITHUB_TOKEN_REF") or "mapped:control-plane.github"


def _default_railway_ref() -> str:
    return _env("RAILWAY_TOKEN_REF") or "mapped:control-plane.railway"


def branch_allowlist() -> list[str]:
    raw = _env("EVOLUTION_GIT_BRANCH_ALLOWLIST", "selfheal/,sandbox/,audit/")
    items = _split_csv(raw)
    return items or ["selfheal/"]


def protected_branches() -> set[str]:
    base = {"main", "master", "prod", "production", "release", "deploy"}
    raw = _split_csv(_env("EVOLUTION_GIT_PROTECTED_BRANCHES", ""))
    return {str(x or "").strip().lower() for x in (list(base) + raw) if str(x or "").strip()}


def is_protected_branch(branch: Any) -> bool:
    value = str(branch or "").strip().lower()
    if not value:
        return False
    if value in protected_branches():
        return True
    return value.startswith("prod/") or value.startswith("deploy/") or value.startswith("release/")


def is_branch_allowed(branch: Any, *, allow_protected: bool = False) -> bool:
    value = str(branch or "").strip()
    if not value:
        return False
    if not allow_protected and is_protected_branch(value):
        return False
    lowered = value.lower()
    for rule in branch_allowlist():
        r = str(rule or "").strip()
        if not r:
            continue
        if r.endswith("/") and lowered.startswith(r.lower()):
            return True
        if lowered == r.lower():
            return True
    return False


def assert_branch_allowed(branch: Any, *, allow_protected: bool = False) -> str:
    value = str(branch or "").strip()
    if not is_branch_allowed(value, allow_protected=allow_protected):
        raise ValueError(f"branch_not_allowed:{value or 'empty'}")
    return value


def resolve_scoped_credentials(*, repo: Any = None, branch: Any = None) -> Dict[str, Any]:
    bundle = ScopedCredentialBundle(
        github_token_ref=_default_token_ref(),
        github_repo=str(repo or _env("GITHUB_REPO") or "").strip() or None,
        github_branch_allowlist=branch_allowlist(),
        railway_token_ref=_default_railway_ref(),
        ttl_seconds=int(_env("EVOLUTION_SCOPED_TOKEN_TTL_SECONDS", "900") or "900"),
        control_plane_only=True,
    )
    result = bundle.as_dict()
    result["branch"] = str(branch or "").strip() or None
    result["branch_allowed"] = is_branch_allowed(branch) if branch else None
    result["protected_branch"] = is_protected_branch(branch) if branch else None
    return result


def control_plane_github_context(*, repo: Any = None, branch: Any = None, web: bool = False) -> Dict[str, Any]:
    resolved_repo = str(repo or (_env("GITHUB_REPO_WEB") if web else _env("GITHUB_REPO")) or "").strip()
    bundle = resolve_scoped_credentials(repo=resolved_repo or None, branch=branch)
    token, token_meta = resolve_github_token("control-plane:github", required=False)
    return {
        "bundle": bundle,
        "token": token,
        "token_meta": token_meta.as_dict(),
        "repo": resolved_repo,
        "branch": str(branch or "").strip() or None,
        "token_present": bool(token),
        "control_plane_only": True,
    }


def control_plane_railway_context() -> Dict[str, Any]:
    token, token_meta = resolve_railway_token("control-plane:railway", required=False)
    return {
        "token_present": bool(token),
        "token_meta": token_meta.as_dict(),
        "control_plane_only": True,
    }


def github_runtime_context(*, repo: Any = None, branch: Any = None) -> Dict[str, Any]:
    return {
        "bundle": resolve_scoped_credentials(repo=repo, branch=branch),
        "github_repo": str(repo or _env("GITHUB_REPO") or "").strip(),
        "github_repo_web": _env("GITHUB_REPO_WEB"),
        "github_token_ref": _default_token_ref(),
        "control_plane_only": True,
    }
