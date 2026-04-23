from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, HTTPException, Query, Header, Depends
from pydantic import BaseModel, Field

from app.security import decode_token
from app.self_heal.credential_scope import branch_allowlist, is_branch_allowed, is_protected_branch, resolve_scoped_credentials, control_plane_github_context

router = APIRouter(prefix="/api/internal/git", tags=["git-internal"])


def _master_admin_emails() -> list[str]:
    raw = (
        _env("MASTER_ADMIN_EMAILS", "")
        or _env("SUPER_ADMIN_EMAILS", "")
        or _env("ADMIN_EMAILS", "")
    )
    if not raw:
        return []
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _master_admin_key() -> str:
    return _env("MASTER_ADMIN_KEY", "") or _env("ADMIN_API_KEY", "")


def _require_master_admin_access(
    authorization: Optional[str] = Header(default=None),
    x_admin_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    master_key = _master_admin_key()
    if x_admin_key and master_key and x_admin_key == master_key:
        return {"role": "master_admin", "via": "x_admin_key"}

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Master admin required")

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

    role = str(payload.get("role", "") or "").strip().lower()
    email = str(payload.get("email", "") or "").strip().lower()
    if role not in {"admin", "owner", "superadmin"}:
        raise HTTPException(status_code=403, detail="Master admin role required")
    allowed = set(_master_admin_emails())
    if allowed and email not in allowed:
        raise HTTPException(status_code=403, detail="Master admin email required")
    return {
        "sub": payload.get("sub"),
        "email": email,
        "role": role,
        "via": "bearer",
    }


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip().strip('"').strip("'")


def _bool_env(name: str, default: bool = False) -> bool:
    raw = _env(name, "true" if default else "false").lower()
    return raw in ("1", "true", "yes", "on")


def _write_enabled() -> bool:
    return _bool_env("GITHUB_AUTOMATION_ALLOWED", False) and _bool_env(
        "AUTO_CODE_EMISSION_ENABLED", False
    )


def _pr_enabled() -> bool:
    return _bool_env("GITHUB_PR_RUNTIME_ENABLED", False) and (
        _bool_env("AUTO_PR_BACKEND_ENABLED", False)
        or _bool_env("AUTO_PR_FRONTEND_ENABLED", False)
        or _bool_env("AUTO_PR_WRITE_ENABLED", False)
    )


def _safe_main_write_allowed() -> bool:
    return _bool_env("ALLOW_GITHUB_MAIN_DIRECT", False)


def _ensure_write_enabled() -> None:
    if not _write_enabled():
        raise HTTPException(
            status_code=403,
            detail="GitHub write runtime disabled by environment",
        )


def _repo() -> str:
    ctx = control_plane_github_context(repo=_env("GITHUB_REPO") or None)
    repo = str(ctx.get("repo") or "").strip()
    if not repo:
        raise HTTPException(status_code=500, detail="GITHUB_REPO not configured")
    return repo


def _token() -> str:
    ctx = control_plane_github_context(repo=_env("GITHUB_REPO") or None)
    token = str(ctx.get("token") or "").strip()
    if not token:
        raise HTTPException(status_code=500, detail="control_plane_github_secret_unresolved")
    return token


def _branch(branch: Optional[str]) -> str:
    return (branch or _env("GITHUB_BRANCH", "main") or "main").strip()


def _guard_branch_write(branch: str) -> None:
    resolved = (branch or "").strip()
    default_branch = _env("GITHUB_BRANCH", "main")
    if not resolved:
        raise HTTPException(status_code=422, detail="branch_required")
    if is_protected_branch(resolved):
        raise HTTPException(
            status_code=403,
            detail=f"Protected branch '{resolved}' blocked by safe evolution policy",
        )
    if resolved == default_branch and not _safe_main_write_allowed():
        raise HTTPException(
            status_code=403,
            detail=f"Direct write on '{default_branch}' blocked by safe evolution policy",
        )
    if not is_branch_allowed(resolved):
        raise HTTPException(
            status_code=403,
            detail={"reason": "branch_outside_allowlist", "branch": resolved, "allowlist": branch_allowlist()},
        )


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "orkio-github-bridge/1.0",
    }


def _api_base() -> str:
    return _env("GITHUB_API_BASE", "https://api.github.com").rstrip("/")


def _request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
) -> Any:
    url = f"{_api_base()}{path}"
    try:
        resp = requests.request(
            method,
            url,
            headers=_headers(),
            params=params,
            json=json_body,
            timeout=int(_env("GITHUB_HTTP_TIMEOUT", "30") or "30"),
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"github request failed: {e}") from e

    if resp.status_code >= 400:
        try:
            detail: Any = resp.json()
        except Exception:
            detail = resp.text
        raise HTTPException(
            status_code=resp.status_code,
            detail={"github_error": detail, "path": path},
        )

    if resp.status_code == 204:
        return {}

    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


def _get_ref_sha(branch: str) -> str:
    data = _request("GET", f"/repos/{_repo()}/git/ref/heads/{branch}")
    return data["object"]["sha"]


def _get_file(path: str, branch: str) -> Dict[str, Any]:
    return _request(
        "GET",
        f"/repos/{_repo()}/contents/{path}",
        params={"ref": branch},
    )


class BranchCreateIn(BaseModel):
    branch_name: str = Field(min_length=3, max_length=120)
    source_branch: Optional[str] = Field(default=None, max_length=120)


class CommitFileIn(BaseModel):
    path: str = Field(min_length=1)
    content: str = Field(min_length=0)
    message: str = Field(min_length=3, max_length=300)
    branch: Optional[str] = Field(default=None, max_length=120)


class PullRequestIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(default="", max_length=20000)
    head: str = Field(min_length=1, max_length=120)
    base: Optional[str] = Field(default=None, max_length=120)


@router.get("/health")
def git_health(_admin=Depends(_require_master_admin_access)):
    ctx = control_plane_github_context(repo=_env("GITHUB_REPO") or None)
    return {
        "ok": True,
        "service": "git_internal",
        "repo": _env("GITHUB_REPO"),
        "default_branch": _env("GITHUB_BRANCH", "main"),
        "token_configured": bool(ctx.get("token_present")),
        "secret_provider": ((ctx.get("token_meta") or {}).get("provider")),
        "secret_provider_available": bool((ctx.get("token_meta") or {}).get("provider_available", True)),
    }


@router.get("/capabilities")
def git_capabilities(_admin=Depends(_require_master_admin_access)):
    ctx = control_plane_github_context(repo=_env("GITHUB_REPO") or None)
    token_meta = ctx.get("token_meta") or {}
    return {
        "ok": True,
        "service": "git_internal",
        "repo": _env("GITHUB_REPO"),
        "default_branch": _env("GITHUB_BRANCH", "main"),
        "token_configured": bool(ctx.get("token_present")),
        "secret_provider": token_meta.get("provider"),
        "secret_provider_available": bool(token_meta.get("provider_available", True)),
        "github_token_ref": ((ctx.get("bundle") or {}).get("github_token_ref")),
        "write_enabled": _write_enabled(),
        "pr_enabled": _pr_enabled(),
        "main_direct_write_allowed": _safe_main_write_allowed(),
        "branch_allowlist": branch_allowlist(),
    }


@router.get("/tree")
def git_tree(branch: Optional[str] = Query(default=None), _admin=Depends(_require_master_admin_access)):
    branch_name = _branch(branch)
    commit_sha = _get_ref_sha(branch_name)
    data = _request(
        "GET",
        f"/repos/{_repo()}/git/trees/{commit_sha}",
        params={"recursive": "1"},
    )
    return {
        "repo": _repo(),
        "branch": branch_name,
        "tree": data.get("tree", []),
        "truncated": data.get("truncated", False),
    }


@router.get("/file")
def git_file(path: str = Query(...), branch: Optional[str] = Query(default=None), _admin=Depends(_require_master_admin_access)):
    branch_name = _branch(branch)
    data = _get_file(path, branch_name)

    content_b64 = data.get("content", "")
    encoding = data.get("encoding", "")

    decoded = ""
    if encoding == "base64" and content_b64:
        decoded = base64.b64decode(content_b64).decode("utf-8", errors="replace")

    return {
        "repo": _repo(),
        "branch": branch_name,
        "path": path,
        "sha": data.get("sha"),
        "size": data.get("size"),
        "content": decoded,
    }


@router.get("/search")
def git_search(
    query: str = Query(..., min_length=2),
    branch: Optional[str] = Query(default=None),
    _admin=Depends(_require_master_admin_access),
):
    branch_name = _branch(branch)
    q = f"repo:{_repo()} {query}"
    data = _request("GET", "/search/code", params={"q": q, "per_page": 50})
    items = data.get("items", [])
    return {
        "repo": _repo(),
        "branch": branch_name,
        "query": query,
        "count": len(items),
        "items": [
            {
                "name": item.get("name"),
                "path": item.get("path"),
                "sha": item.get("sha"),
                "url": item.get("html_url"),
            }
            for item in items
        ],
    }


@router.post("/branch")
def git_create_branch(payload: BranchCreateIn, _admin=Depends(_require_master_admin_access)):
    _ensure_write_enabled()
    if is_protected_branch(payload.branch_name) or not is_branch_allowed(payload.branch_name):
        raise HTTPException(status_code=403, detail={"reason": "unsafe_branch_name", "branch": payload.branch_name, "allowlist": branch_allowlist()})
    source_branch = _branch(payload.source_branch)
    base_sha = _get_ref_sha(source_branch)
    ref = f"refs/heads/{payload.branch_name}"

    data = _request(
        "POST",
        f"/repos/{_repo()}/git/refs",
        json_body={
            "ref": ref,
            "sha": base_sha,
        },
    )

    return {
        "ok": True,
        "source_branch": source_branch,
        "new_branch": payload.branch_name,
        "ref": data.get("ref"),
        "sha": data.get("object", {}).get("sha"),
        "credential_scope": resolve_scoped_credentials(branch=payload.branch_name),
    }


@router.post("/commit")
def git_commit_file(payload: CommitFileIn, _admin=Depends(_require_master_admin_access)):
    _ensure_write_enabled()
    branch_name = _branch(payload.branch)
    _guard_branch_write(branch_name)

    existing_sha = None
    file_preexisted = False

    try:
        existing = _get_file(payload.path, branch_name)
        existing_sha = existing.get("sha")
        file_preexisted = True
    except HTTPException as e:
        if e.status_code == 404:
            existing_sha = None
            file_preexisted = False
        else:
            raise

    encoded = base64.b64encode(payload.content.encode("utf-8")).decode("utf-8")

    body: Dict[str, Any] = {
        "message": payload.message,
        "content": encoded,
        "branch": branch_name,
    }
    if existing_sha:
        body["sha"] = existing_sha

    data = _request(
        "PUT",
        f"/repos/{_repo()}/contents/{payload.path}",
        json_body=body,
    )

    commit = data.get("commit", {}) or {}
    content = data.get("content", {}) or {}

    return {
        "ok": True,
        "repo": _repo(),
        "branch": branch_name,
        "path": payload.path,
        "created": not file_preexisted,
        "updated": file_preexisted,
        "content_sha": content.get("sha"),
        "commit_sha": commit.get("sha"),
        "commit_url": commit.get("html_url"),
        "credential_scope": resolve_scoped_credentials(branch=branch_name),
    }


@router.post("/pr")
def git_open_pr(payload: PullRequestIn, _admin=Depends(_require_master_admin_access)):
    if not _pr_enabled():
        raise HTTPException(
            status_code=403,
            detail="GitHub PR runtime disabled by environment",
        )

    _guard_branch_write(payload.head)
    base_branch = _branch(payload.base)
    data = _request(
        "POST",
        f"/repos/{_repo()}/pulls",
        json_body={
            "title": payload.title,
            "body": payload.body,
            "head": payload.head,
            "base": base_branch,
        },
    )
    return {
        "ok": True,
        "number": data.get("number"),
        "state": data.get("state"),
        "url": data.get("html_url"),
        "credential_scope": resolve_scoped_credentials(branch=payload.head),
    }
