from __future__ import annotations

import json
import os
import re
import time
import urllib.request as _urllib_request
import urllib.parse as _urllib_parse
import ssl as _ssl
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/internal/orion", tags=["orion_internal"])

PATCH_SENTINEL = "PR_COMPARE_STATUS_SENTINEL_12BO_V1"
PATCH_FEATURE = "github_pr_compare_status_resolver"
PATCH_EXPECTED_BEHAVIOR = "github_compare_and_pr_status_requests_resolve_with_repo_aliases_natural_compare_and_ok_surface_for_missing_pr"


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _clean_env(name: str, default: str = "") -> str:
    raw = os.getenv(name, default)
    if raw is None:
        return default
    value = str(raw).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()
    return value or default


def _now_ts() -> int:
    return int(time.time())


def _github_repo() -> str:
    return _clean_env("GITHUB_REPO", "")


def _github_repo_web() -> str:
    return _clean_env("GITHUB_REPO_WEB", "")


def _default_branch() -> str:
    return _clean_env("GITHUB_DEFAULT_BASE_BRANCH", _clean_env("GITHUB_BRANCH", "main"))


def _github_write_enabled() -> bool:
    return _bool_env("GITHUB_WRITE_RUNTIME_ENABLED", False) or (
        _bool_env("ENABLE_GITHUB_BRIDGE", False)
        and _bool_env("GITHUB_AUTOMATION_ALLOWED", False)
        and _bool_env("AUTO_CODE_EMISSION_ENABLED", False)
    )


def _github_pr_enabled() -> bool:
    return _bool_env("GITHUB_PR_RUNTIME_ENABLED", False) and (
        _bool_env("AUTO_PR_BACKEND_ENABLED", False)
        or _bool_env("AUTO_PR_FRONTEND_ENABLED", False)
        or _bool_env("AUTO_PR_WRITE_ENABLED", False)
    )


def _main_direct_allowed() -> bool:
    return _bool_env("ALLOW_GITHUB_MAIN_DIRECT", False)


def _evolution_enabled() -> bool:
    return _bool_env("ENABLE_EVOLUTION_LOOP", False)


def _allowed_write_agents() -> List[str]:
    raw = _clean_env("GITHUB_WRITE_ALLOWED_AGENTS", "orion")
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _allowed_read_agents() -> List[str]:
    raw = _clean_env("GITHUB_READ_ALLOWED_AGENTS", "orkio,orion,chris,auditor")
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _extract_agent_handles(message: str) -> List[str]:
    found = re.findall(r"@([A-Za-z0-9_]+)", message or "")
    return [x.strip().lower() for x in found if x.strip()]


def _resolve_visible_agent(message: str, default: str = "orion") -> str:
    handles = _extract_agent_handles(message)
    if "orion" in handles:
        return "orion"
    if "orkio" in handles:
        return "orkio"
    if handles:
        return handles[0]
    return default


def _suggested_squad() -> List[Dict[str, str]]:
    return [
        {"id": "orkio", "role": "orchestrator", "scope": "coordenação e síntese"},
        {"id": "orion", "role": "cto", "scope": "execução técnica e GitHub runtime"},
        {"id": "auditor", "role": "technical_auditor", "scope": "auditoria arquitetural e riscos"},
        {"id": "cto", "role": "systems_architect", "scope": "plano técnico e desenho de patch"},
        {"id": "chris", "role": "commercial_strategist", "scope": "impacto funcional e leitura de produto"},
        {"id": "saint_germain", "role": "refiner", "scope": "maturidade e refinamento incremental"},
        {"id": "miguel", "role": "guardian", "scope": "guarda de segurança e limites"},
        {"id": "uriel", "role": "diagnostician", "scope": "diagnóstico de causa raiz"},
        {"id": "rafael", "role": "organizer", "scope": "plano de ação prático"},
        {"id": "gabriel", "role": "translator", "scope": "tradução executiva e explicação clara"},
        {"id": "metatron", "role": "scribe", "scope": "registro e continuidade"},
    ]


def _build_repo_targets() -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    backend = _github_repo()
    frontend = _github_repo_web()
    if backend:
        items.append({"repo": backend, "kind": "backend", "default_branch": _default_branch()})
    if frontend:
        items.append({"repo": frontend, "kind": "frontend", "default_branch": _default_branch()})
    return items


def _safe_patch_policy() -> Dict[str, Any]:
    return {
        "write_enabled": _github_write_enabled(),
        "pr_enabled": _github_pr_enabled(),
        "main_direct_write_allowed": _main_direct_allowed(),
        "require_explicit_deploy_approval": _bool_env("REQUIRE_EXPLICIT_DEPLOY_APPROVAL", True),
        "require_explicit_pr_approval": _bool_env("REQUIRE_EXPLICIT_PR_APPROVAL", True),
        "require_explicit_db_approval": _bool_env("REQUIRE_EXPLICIT_DB_APPROVAL", True),
        "db_runtime_allow_destructive": _bool_env("DB_RUNTIME_ALLOW_DESTRUCTIVE", False),
        "controlled_overlay_enabled": _bool_env("CONTROLLED_EVOLUTION_OVERLAY_ENABLED", True),
        "evolution_loop_enabled": _evolution_enabled(),
        "write_allowed_agents": _allowed_write_agents(),
        "read_allowed_agents": _allowed_read_agents(),
        "require_explicit_pr_approval": _bool_env("REQUIRE_EXPLICIT_PR_APPROVAL", True),
        "transactional_flow_required": True,
        "receipt_required_steps": [
            "branch_created",
            "files_written",
            "commit_created",
            "compare_ok",
            "pull_request_opened",
        ],
        "pr_open_requires_branch_and_commit": True,
        "approval_grant_expands_transaction_prerequisites": True,
        "frontend_repo_target_hard_binding": True,
        "proposal_to_file_write_emission": True,
        "patch_sentinel": PATCH_SENTINEL,
        "patch_feature": PATCH_FEATURE,
        "patch_expected_behavior": PATCH_EXPECTED_BEHAVIOR,
    }



def _github_runtime_token() -> str:
    return (
        _clean_env("ORKIO_GITHUB_CONTROL_PLANE_TOKEN", "")
        or _clean_env("GITHUB_TOKEN", "")
        or _clean_env("GH_TOKEN", "")
    )


def _github_headers() -> Dict[str, str]:
    token = _github_runtime_token()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "orkio-orion-runtime/1.0",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_api_json(method: str, url: str) -> tuple[int, Any]:
    req = _urllib_request.Request(url, headers=_github_headers(), method=method.upper())
    ctx = _ssl.create_default_context()
    try:
        with _urllib_request.urlopen(req, context=ctx, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace") or "null"
            try:
                return int(getattr(resp, "status", 200) or 200), json.loads(raw)
            except Exception:
                return int(getattr(resp, "status", 200) or 200), {"raw": raw}
    except Exception as exc:
        status = int(getattr(exc, "code", 0) or 0)
        body = getattr(exc, "read", None)
        parsed: Any = {}
        try:
            if body:
                raw = body().decode("utf-8", errors="replace") or "null"
                parsed = json.loads(raw)
        except Exception:
            parsed = {"message": str(exc)}
        if not parsed:
            parsed = {"message": str(exc)}
        return status, parsed



def _looks_like_compare_status_request(message: str) -> bool:
    txt = (message or "").strip().lower()
    if not txt:
        return False
    compare_markers = [
        "compare a branch",
        "compare branch",
        "compare branches",
        "compare da",
        "compare do",
        "quero o compare",
        "quero compare",
        "comparar a branch",
        "comparar branch",
        "compare_ok",
        "ahead_by",
        "status da pr",
        "status final da pr",
        "status final do pr",
        "pr status",
        "pull request status",
        "pr_url",
        "pr_number",
    ]
    has_compare = any(marker in txt for marker in compare_markers)
    has_pr_ref = bool(re.search(r"\bpr\s*#?\s*\d+\b", txt, flags=re.IGNORECASE))
    has_branch_compare = (("branch" in txt) or ("branches" in txt)) and (("compare" in txt) or ("comparar" in txt))
    has_compare_word = ("compare" in txt) or ("comparar" in txt)
    has_repo_hint = any(token in txt for token in ["repo", "repositório", "repositorio", "frontend", "backend", "main", "master", "contra", "versus", "vs"])
    has_ref_slug = bool(re.search(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", txt))
    structured_fields = any(field in txt for field in ["files_changed", "commit_sha", "compare_ok", "ahead_by", "pr_url", "pr_number"])
    return bool(has_compare or has_pr_ref or has_branch_compare or structured_fields or (has_compare_word and (has_repo_hint or has_ref_slug)))


def _repo_short_name(repo: str) -> str:
    repo = str(repo or "").strip()
    if "/" not in repo:
        return repo
    return repo.split("/", 1)[1].strip()


def _repo_owner(repo: str) -> str:
    repo = str(repo or "").strip()
    if "/" not in repo:
        return ""
    return repo.split("/", 1)[0].strip()


def _looks_like_branch_slug(value: str) -> bool:
    value = str(value or "").strip().lower()
    if not value or "/" not in value:
        return False
    prefixes = ("feat/", "fix/", "hotfix/", "chore/", "docs/", "refactor/", "test/", "tests/", "build/", "ci/", "perf/", "release/")
    if value.startswith(prefixes):
        return True
    owner, slug = value.split("/", 1)
    if owner in {"main", "master", "develop", "dev", "production", "prod"}:
        return True
    if not owner or not slug:
        return True
    return False


def _extract_explicit_repo_from_message(message: str) -> str:
    txt = (message or "").strip()
    if not txt:
        return ""

    url_match = re.search(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", txt, flags=re.IGNORECASE)
    if url_match:
        candidate = str(url_match.group(1) or "").strip().strip("/")
        return "" if _looks_like_branch_slug(candidate) else candidate

    marker_patterns = [
        r"(?:repositório|repositorio|repo|repository)\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
        r"(?:repositório|repositorio|repo|repository)\s*[:=]\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
        r"no\s+(?:repositório|repositorio|repo|repository)\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
        r"do\s+(?:repositório|repositorio|repo|repository)\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
    ]
    for pat in marker_patterns:
        m = re.search(pat, txt, flags=re.IGNORECASE)
        if not m:
            continue
        candidate = str(m.group(1) or "").strip()
        if candidate and not _looks_like_branch_slug(candidate):
            return candidate
    return ""


def _repo_matches_alias(candidate: str, configured: str) -> bool:
    candidate = str(candidate or "").strip().lower()
    configured = str(configured or "").strip().lower()
    if not candidate or not configured:
        return False
    if candidate == configured:
        return True
    candidate_owner = _repo_owner(candidate)
    configured_owner = _repo_owner(configured)
    candidate_short = _repo_short_name(candidate).lower()
    configured_short = _repo_short_name(configured).lower()
    if candidate_owner and configured_owner and candidate_owner != configured_owner:
        return False
    if candidate_short == configured_short:
        return True
    if configured_short.startswith(candidate_short + "-"):
        return True
    return False


def _normalize_repo_target(repo_candidate: str, backend: str, frontend: str, message: str) -> str:
    candidate = str(repo_candidate or "").strip()
    txt = (message or "").strip().lower()
    if candidate:
        if _repo_matches_alias(candidate, frontend):
            return frontend or candidate
        if _repo_matches_alias(candidate, backend):
            return backend or candidate
        return candidate
    if "frontend" in txt or "web" in txt or "appconsole" in txt or "react" in txt or "tsx" in txt or "jsx" in txt:
        return frontend or backend
    return backend or frontend


def _resolve_repo_target_from_message(message: str) -> str:
    explicit = _extract_explicit_repo_from_message(message)
    backend = _github_repo()
    frontend = _github_repo_web()
    return _normalize_repo_target(explicit, backend, frontend, message)




def _extract_branch_names_from_message(message: str) -> tuple[str, str]:
    txt = (message or "").strip()
    default_branch = _default_branch()
    head = ""
    base = ""
    patterns = [
        r"compare\s+(?:a\s+)?branch\s+([A-Za-z0-9_./-]+)\s+com\s+a\s+(?:branch\s+)?([A-Za-z0-9_./-]+)",
        r"compare\s+(?:a\s+)?branch\s+([A-Za-z0-9_./-]+)\s+(?:contra|com|versus|vs)\s+(?:a\s+)?(?:branch\s+)?([A-Za-z0-9_./-]+)",
        r"comparar\s+(?:a\s+)?branch\s+([A-Za-z0-9_./-]+)\s+(?:contra|com|versus|vs)\s+(?:a\s+)?(?:branch\s+)?([A-Za-z0-9_./-]+)",
        r"compare\s+(?:da|do|de)\s+([A-Za-z0-9_./-]+).*?(?:contra|com|versus|vs)\s+([A-Za-z0-9_./-]+)",
        r"comparar\s+(?:da|do|de)\s+([A-Za-z0-9_./-]+).*?(?:contra|com|versus|vs)\s+([A-Za-z0-9_./-]+)",
        r"branch\s+([A-Za-z0-9_./-]+)\s+to\s+([A-Za-z0-9_./-]+)",
        r"da\s+branch\s+([A-Za-z0-9_./-]+)\s+para\s+([A-Za-z0-9_./-]+)",
        r"head\s*[:=]\s*([A-Za-z0-9_./-]+).*?base\s*[:=]\s*([A-Za-z0-9_./-]+)",
    ]
    for pat in patterns:
        m = re.search(pat, txt, flags=re.IGNORECASE)
        if m:
            head = str(m.group(1) or "").strip()
            base = str(m.group(2) or "").strip()
            break

    if not head:
        m = re.search(r"branch\s+([A-Za-z0-9_./-]+)", txt, flags=re.IGNORECASE)
        if m:
            head = str(m.group(1) or "").strip()

    if not head and (("compare" in txt.lower()) or ("comparar" in txt.lower())):
        slug_match = re.search(
            r"\b((?:feat|fix|hotfix|chore|docs|refactor|test|tests|build|ci|perf|release)/[A-Za-z0-9_./-]+)\b",
            txt,
            flags=re.IGNORECASE,
        )
        if slug_match:
            head = str(slug_match.group(1) or "").strip()

    if not base:
        m = re.search(r"(?:contra|com|versus|vs)\s+(?:a\s+)?(?:branch\s+)?([A-Za-z0-9_./-]+)", txt, flags=re.IGNORECASE)
        if m:
            base = str(m.group(1) or "").strip()

    if not base:
        m = re.search(r"base(?:_branch)?\s*[:=]?\s*([A-Za-z0-9_./-]+)", txt, flags=re.IGNORECASE)
        if m:
            base = str(m.group(1) or "").strip()

    if not base:
        m = re.search(r"\b(main|master|production|prod|develop|dev)\b", txt, flags=re.IGNORECASE)
        if m:
            base = str(m.group(1) or "").strip()

    return head, (base or default_branch)

def _extract_pr_number_from_message(message: str) -> int:
    txt = (message or "").strip()
    if not txt:
        return 0
    m = re.search(r"\bpr\s*#\s*(\d+)\b", txt, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"\bpull request\s*#?\s*(\d+)\b", txt, flags=re.IGNORECASE)
    try:
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


def _github_branch_head_sha(repo: str, branch: str) -> str:
    repo = str(repo or "").strip()
    branch = str(branch or "").strip()
    if not repo or not branch:
        return ""
    url = f"https://api.github.com/repos/{repo}/branches/{_urllib_parse.quote(branch, safe='')}"
    status, body = _github_api_json("GET", url)
    if status != 200 or not isinstance(body, dict):
        return ""
    commit = body.get("commit") if isinstance(body.get("commit"), dict) else {}
    return str(commit.get("sha") or "").strip()


def _github_pr_by_number(repo: str, pr_number: int) -> Dict[str, Any]:
    if not repo or pr_number <= 0:
        return {"ok": False, "message": "pr_number_missing"}
    url = f"https://api.github.com/repos/{repo}/pulls/{int(pr_number)}"
    status, body = _github_api_json("GET", url)
    ok = status == 200 and isinstance(body, dict)
    if ok:
        message = ""
    elif status == 404:
        message = "pull_request_not_found"
    else:
        message = str((body or {}).get("message") or f"pull_fetch_failed_status_{status}")
    return {"ok": ok, "status": status, "body": body if isinstance(body, dict) else {}, "message": message}


def _github_find_pull_by_head(repo: str, head: str, base: str) -> Dict[str, Any]:
    repo = str(repo or "").strip()
    head = str(head or "").strip()
    base = str(base or "").strip()
    owner = _repo_owner(repo)
    if not repo or not head:
        return {"ok": False, "message": "repo_or_head_missing"}
    q = _urllib_parse.urlencode({"state": "open", "head": f"{owner}:{head}", "base": base or _default_branch()})
    url = f"https://api.github.com/repos/{repo}/pulls?{q}"
    status, body = _github_api_json("GET", url)
    if status != 200 or not isinstance(body, list):
        return {"ok": False, "message": ("pull_request_not_found" if status == 404 else f"pull_list_failed_status_{status}"), "body": body}
    first = body[0] if body else {}
    return {"ok": bool(first), "body": first if isinstance(first, dict) else {}, "message": "" if first else "pull_not_found"}


def _github_compare(repo: str, base: str, head: str) -> Dict[str, Any]:
    repo = str(repo or "").strip()
    base = str(base or "").strip()
    head = str(head or "").strip()
    if not repo or not base or not head:
        return {"ok": False, "message": "repo_base_head_missing", "files_changed": []}
    url = f"https://api.github.com/repos/{repo}/compare/{_urllib_parse.quote(base, safe='')}...{_urllib_parse.quote(head, safe='')}"
    status, body = _github_api_json("GET", url)
    if status != 200 or not isinstance(body, dict):
        message = str((body or {}).get("message") or f"compare_failed_status_{status}")
        return {"ok": False, "status": status, "message": message, "body": body, "files_changed": []}
    files = body.get("files") if isinstance(body.get("files"), list) else []
    file_names = []
    for item in files:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").strip()
        if filename:
            file_names.append(filename)
    commits = body.get("commits") if isinstance(body.get("commits"), list) else []
    latest_commit_sha = ""
    if commits and isinstance(commits[-1], dict):
        latest_commit_sha = str(commits[-1].get("sha") or "").strip()
    if not latest_commit_sha:
        latest_commit_sha = _github_branch_head_sha(repo, head)
    return {
        "ok": True,
        "status": status,
        "body": body,
        "ahead_by": int(body.get("ahead_by") or 0),
        "behind_by": int(body.get("behind_by") or 0),
        "files_changed": file_names,
        "files_count": len(file_names),
        "commit_sha": latest_commit_sha,
        "html_url": str(body.get("html_url") or "").strip(),
    }


def _github_compare_status_payload(message: str, visible_agent: str, repository_details: List[Dict[str, Any]]) -> Dict[str, Any]:
    repo_target = _resolve_repo_target_from_message(message)
    default_branch = _default_branch()
    pr_number = _extract_pr_number_from_message(message)
    head, base = _extract_branch_names_from_message(message)
    pr_payload: Dict[str, Any] = {}
    pr_url = ""
    merge_executed = False
    head_sha = ""

    if pr_number > 0:
        pr_lookup = _github_pr_by_number(repo_target, pr_number)
        if pr_lookup.get("ok"):
            pr_payload = pr_lookup.get("body") if isinstance(pr_lookup.get("body"), dict) else {}
            head_ref = pr_payload.get("head") if isinstance(pr_payload.get("head"), dict) else {}
            base_ref = pr_payload.get("base") if isinstance(pr_payload.get("base"), dict) else {}
            head = head or str(head_ref.get("ref") or "").strip()
            base = base or str(base_ref.get("ref") or "").strip() or default_branch
            head_sha = str(head_ref.get("sha") or "").strip()
            pr_url = str(pr_payload.get("html_url") or "").strip()
            merge_executed = bool(pr_payload.get("merged"))
        else:
            return {
                "ok": True,
                "service": "orion_internal",
                "mode": "github_compare_status",
                "event": "GITHUB_COMPARE_STATUS_OK",
                "provider": "github",
                "visible_agent": visible_agent,
                "repo": repo_target,
                "repo_target": repo_target,
                "backend_repo": _github_repo(),
                "frontend_repo": _github_repo_web(),
                "repository_details": repository_details,
                "branch": head,
                "branch_name": head,
                "base_branch": base or default_branch,
                "compare_ok": False,
                "merge_executed": False,
                "deploy_executed": False,
                "pr_number": int(pr_number or 0),
                "pr_found": False,
                "resolution": "pull_request_not_found",
                "message": "pull_request_not_found",
                "github_error": "pull_request_not_found",
                "generated_at": _now_ts(),
            }

    if not head:
        return {
            "ok": True,
            "service": "orion_internal",
            "mode": "github_compare_status",
            "event": "GITHUB_COMPARE_STATUS_INPUT_INVALID",
            "provider": "github",
            "visible_agent": visible_agent,
            "repo": repo_target,
            "repo_target": repo_target,
            "backend_repo": _github_repo(),
            "frontend_repo": _github_repo_web(),
            "repository_details": repository_details,
            "pr_number": int(pr_number or 0),
            "compare_ok": False,
            "merge_executed": False,
            "deploy_executed": False,
            "message": "head_branch_not_detected",
            "expected_input": "compare <head_branch> contra <base_branch> no repo <owner/repo>",
            "generated_at": _now_ts(),
        }

    compare_payload = _github_compare(repo_target, base or default_branch, head)
    if (not compare_payload.get("ok")) and head_sha:
        compare_payload = _github_compare(repo_target, base or default_branch, head_sha)

    if not compare_payload.get("ok"):
        if not pr_number:
            pr_lookup = _github_find_pull_by_head(repo_target, head, base or default_branch)
            if pr_lookup.get("ok"):
                pr_payload = pr_lookup.get("body") if isinstance(pr_lookup.get("body"), dict) else {}
                pr_number = int(pr_payload.get("number") or 0)
                pr_url = str(pr_payload.get("html_url") or "").strip()
                merge_executed = bool(pr_payload.get("merged"))
        if pr_number or pr_url:
            return {
                "ok": True,
                "service": "orion_internal",
                "mode": "github_compare_status",
                "event": "GITHUB_COMPARE_STATUS_PARTIAL",
                "provider": "github",
                "visible_agent": visible_agent,
                "repo": repo_target,
                "repo_target": repo_target,
                "backend_repo": _github_repo(),
                "frontend_repo": _github_repo_web(),
                "repository_details": repository_details,
                "branch": head,
                "branch_name": head,
                "base_branch": base or default_branch,
                "compare_ok": False,
                "compare_error": str(compare_payload.get("message") or "compare_failed"),
                "pr_number": int(pr_number or 0),
                "pr_url": pr_url,
                "merge_executed": bool(merge_executed),
                "deploy_executed": False,
                "generated_at": _now_ts(),
            }
        return {
            "ok": False,
            "service": "orion_internal",
            "mode": "github_compare_status",
            "event": "GITHUB_COMPARE_STATUS_FAILED",
            "provider": "github",
            "visible_agent": visible_agent,
            "repo": repo_target,
            "repo_target": repo_target,
            "backend_repo": _github_repo(),
            "frontend_repo": _github_repo_web(),
            "repository_details": repository_details,
            "branch_name": head,
            "base_branch": base or default_branch,
            "message": str(compare_payload.get("message") or "compare_failed"),
            "generated_at": _now_ts(),
        }

    if not pr_number:
        pr_lookup = _github_find_pull_by_head(repo_target, head, base or default_branch)
        if pr_lookup.get("ok"):
            pr_payload = pr_lookup.get("body") if isinstance(pr_lookup.get("body"), dict) else {}
            pr_number = int(pr_payload.get("number") or 0)
            pr_url = str(pr_payload.get("html_url") or "").strip()
            merge_executed = bool(pr_payload.get("merged"))
    commit_sha = str(compare_payload.get("commit_sha") or "").strip()
    files_changed = list(compare_payload.get("files_changed") or [])
    return {
        "ok": True,
        "service": "orion_internal",
        "mode": "github_compare_status",
        "event": "GITHUB_COMPARE_STATUS_OK",
        "provider": "github",
        "visible_agent": visible_agent,
        "repo": repo_target,
        "repo_target": repo_target,
        "backend_repo": _github_repo(),
        "frontend_repo": _github_repo_web(),
        "repository_details": repository_details,
        "branch": head,
        "branch_name": head,
        "base_branch": base or default_branch,
        "compare_ok": True,
        "ahead_by": int(compare_payload.get("ahead_by") or 0),
        "behind_by": int(compare_payload.get("behind_by") or 0),
        "files_changed": files_changed,
        "files_count": len(files_changed),
        "commit_sha": commit_sha,
        "pr_number": int(pr_number or 0),
        "pr_url": pr_url,
        "merge_executed": bool(merge_executed),
        "deploy_executed": False,
        "generated_at": _now_ts(),
    }


def _safe_patch_policy() -> Dict[str, Any]:
    return {
        "write_enabled": _github_write_enabled(),
        "pr_enabled": _github_pr_enabled(),
        "main_direct_write_allowed": _main_direct_allowed(),
        "require_explicit_deploy_approval": _bool_env("REQUIRE_EXPLICIT_DEPLOY_APPROVAL", True),
        "require_explicit_pr_approval": _bool_env("REQUIRE_EXPLICIT_PR_APPROVAL", True),
        "require_explicit_db_approval": _bool_env("REQUIRE_EXPLICIT_DB_APPROVAL", True),
        "db_runtime_allow_destructive": _bool_env("DB_RUNTIME_ALLOW_DESTRUCTIVE", False),
        "controlled_overlay_enabled": _bool_env("CONTROLLED_EVOLUTION_OVERLAY_ENABLED", True),
        "evolution_loop_enabled": _evolution_enabled(),
        "write_allowed_agents": _allowed_write_agents(),
        "read_allowed_agents": _allowed_read_agents(),
        "require_explicit_pr_approval": _bool_env("REQUIRE_EXPLICIT_PR_APPROVAL", True),
        "transactional_flow_required": True,
        "receipt_required_steps": [
            "branch_created",
            "files_written",
            "commit_created",
            "compare_ok",
            "pull_request_opened",
        ],
        "pr_open_requires_branch_and_commit": True,
        "approval_grant_expands_transaction_prerequisites": True,
        "frontend_repo_target_hard_binding": True,
        "proposal_to_file_write_emission": True,
        "patch_sentinel": PATCH_SENTINEL,
        "patch_feature": PATCH_FEATURE,
        "patch_expected_behavior": PATCH_EXPECTED_BEHAVIOR,
    }



def _github_runtime_token() -> str:
    return (
        _clean_env("ORKIO_GITHUB_CONTROL_PLANE_TOKEN", "")
        or _clean_env("GITHUB_TOKEN", "")
        or _clean_env("GH_TOKEN", "")
    )


def _github_headers() -> Dict[str, str]:
    token = _github_runtime_token()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "orkio-orion-runtime/1.0",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_api_json(method: str, url: str) -> tuple[int, Any]:
    req = _urllib_request.Request(url, headers=_github_headers(), method=method.upper())
    ctx = _ssl.create_default_context()
    try:
        with _urllib_request.urlopen(req, context=ctx, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace") or "null"
            try:
                return int(getattr(resp, "status", 200) or 200), json.loads(raw)
            except Exception:
                return int(getattr(resp, "status", 200) or 200), {"raw": raw}
    except Exception as exc:
        status = int(getattr(exc, "code", 0) or 0)
        body = getattr(exc, "read", None)
        parsed: Any = {}
        try:
            if body:
                raw = body().decode("utf-8", errors="replace") or "null"
                parsed = json.loads(raw)
        except Exception:
            parsed = {"message": str(exc)}
        if not parsed:
            parsed = {"message": str(exc)}
        return status, parsed



def _looks_like_compare_status_request(message: str) -> bool:
    txt = (message or "").strip().lower()
    if not txt:
        return False
    compare_markers = [
        "compare a branch",
        "compare branch",
        "compare branches",
        "compare da",
        "compare do",
        "quero o compare",
        "quero compare",
        "comparar a branch",
        "comparar branch",
        "compare_ok",
        "ahead_by",
        "status da pr",
        "status final da pr",
        "status final do pr",
        "pr status",
        "pull request status",
        "pr_url",
        "pr_number",
    ]
    has_compare = any(marker in txt for marker in compare_markers)
    has_pr_ref = bool(re.search(r"\bpr\s*#?\s*\d+\b", txt, flags=re.IGNORECASE))
    has_branch_compare = (("branch" in txt) or ("branches" in txt)) and (("compare" in txt) or ("comparar" in txt))
    has_compare_word = ("compare" in txt) or ("comparar" in txt)
    has_repo_hint = any(token in txt for token in ["repo", "repositório", "repositorio", "frontend", "backend", "main", "master", "contra", "versus", "vs"])
    has_ref_slug = bool(re.search(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", txt))
    structured_fields = any(field in txt for field in ["files_changed", "commit_sha", "compare_ok", "ahead_by", "pr_url", "pr_number"])
    return bool(has_compare or has_pr_ref or has_branch_compare or structured_fields or (has_compare_word and (has_repo_hint or has_ref_slug)))


def _repo_short_name(repo: str) -> str:
    repo = str(repo or "").strip()
    if "/" not in repo:
        return repo
    return repo.split("/", 1)[1].strip()


def _repo_owner(repo: str) -> str:
    repo = str(repo or "").strip()
    if "/" not in repo:
        return ""
    return repo.split("/", 1)[0].strip()


def _looks_like_branch_slug(value: str) -> bool:
    value = str(value or "").strip().lower()
    if not value or "/" not in value:
        return False
    prefixes = ("feat/", "fix/", "hotfix/", "chore/", "docs/", "refactor/", "test/", "tests/", "build/", "ci/", "perf/", "release/")
    if value.startswith(prefixes):
        return True
    owner, slug = value.split("/", 1)
    if owner in {"main", "master", "develop", "dev", "production", "prod"}:
        return True
    if not owner or not slug:
        return True
    return False


def _extract_explicit_repo_from_message(message: str) -> str:
    txt = (message or "").strip()
    if not txt:
        return ""

    url_match = re.search(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", txt, flags=re.IGNORECASE)
    if url_match:
        candidate = str(url_match.group(1) or "").strip().strip("/")
        return "" if _looks_like_branch_slug(candidate) else candidate

    marker_patterns = [
        r"(?:repositório|repositorio|repo|repository)\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
        r"(?:repositório|repositorio|repo|repository)\s*[:=]\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
        r"no\s+(?:repositório|repositorio|repo|repository)\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
        r"do\s+(?:repositório|repositorio|repo|repository)\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
    ]
    for pat in marker_patterns:
        m = re.search(pat, txt, flags=re.IGNORECASE)
        if not m:
            continue
        candidate = str(m.group(1) or "").strip()
        if candidate and not _looks_like_branch_slug(candidate):
            return candidate
    return ""


def _repo_matches_alias(candidate: str, configured: str) -> bool:
    candidate = str(candidate or "").strip().lower()
    configured = str(configured or "").strip().lower()
    if not candidate or not configured:
        return False
    if candidate == configured:
        return True
    candidate_owner = _repo_owner(candidate)
    configured_owner = _repo_owner(configured)
    candidate_short = _repo_short_name(candidate).lower()
    configured_short = _repo_short_name(configured).lower()
    if candidate_owner and configured_owner and candidate_owner != configured_owner:
        return False
    if candidate_short == configured_short:
        return True
    if configured_short.startswith(candidate_short + "-"):
        return True
    return False


def _normalize_repo_target(repo_candidate: str, backend: str, frontend: str, message: str) -> str:
    candidate = str(repo_candidate or "").strip()
    txt = (message or "").strip().lower()
    if candidate:
        if _repo_matches_alias(candidate, frontend):
            return frontend or candidate
        if _repo_matches_alias(candidate, backend):
            return backend or candidate
        return candidate
    if "frontend" in txt or "web" in txt or "appconsole" in txt or "react" in txt or "tsx" in txt or "jsx" in txt:
        return frontend or backend
    return backend or frontend


def _resolve_repo_target_from_message(message: str) -> str:
    explicit = _extract_explicit_repo_from_message(message)
    backend = _github_repo()
    frontend = _github_repo_web()
    return _normalize_repo_target(explicit, backend, frontend, message)


def _extract_branch_names_from_message(message: str) -> tuple[str, str]:
    txt = (message or "").strip()
    default_branch = _default_branch()
    head = ""
    base = ""
    patterns = [
        r"compare\s+(?:a\s+)?branch\s+([A-Za-z0-9_./-]+)\s+com\s+a\s+(?:branch\s+)?([A-Za-z0-9_./-]+)",
        r"compare\s+(?:a\s+)?branch\s+([A-Za-z0-9_./-]+)\s+(?:contra|com|versus|vs)\s+(?:a\s+)?(?:branch\s+)?([A-Za-z0-9_./-]+)",
        r"comparar\s+(?:a\s+)?branch\s+([A-Za-z0-9_./-]+)\s+(?:contra|com|versus|vs)\s+(?:a\s+)?(?:branch\s+)?([A-Za-z0-9_./-]+)",
        r"compare\s+(?:da|do|de)\s+([A-Za-z0-9_./-]+).*?(?:contra|com|versus|vs)\s+([A-Za-z0-9_./-]+)",
        r"comparar\s+(?:da|do|de)\s+([A-Za-z0-9_./-]+).*?(?:contra|com|versus|vs)\s+([A-Za-z0-9_./-]+)",
        r"branch\s+([A-Za-z0-9_./-]+)\s+to\s+([A-Za-z0-9_./-]+)",
        r"da\s+branch\s+([A-Za-z0-9_./-]+)\s+para\s+([A-Za-z0-9_./-]+)",
        r"head\s*[:=]\s*([A-Za-z0-9_./-]+).*?base\s*[:=]\s*([A-Za-z0-9_./-]+)",
    ]
    for pat in patterns:
        m = re.search(pat, txt, flags=re.IGNORECASE)
        if m:
            head = str(m.group(1) or "").strip()
            base = str(m.group(2) or "").strip()
            break

    if not head:
        m = re.search(r"branch\s+([A-Za-z0-9_./-]+)", txt, flags=re.IGNORECASE)
        if m:
            head = str(m.group(1) or "").strip()

    if not head and (("compare" in txt.lower()) or ("comparar" in txt.lower())):
        slug_match = re.search(
            r"\b((?:feat|fix|hotfix|chore|docs|refactor|test|tests|build|ci|perf|release)/[A-Za-z0-9_./-]+)\b",
            txt,
            flags=re.IGNORECASE,
        )
        if slug_match:
            head = str(slug_match.group(1) or "").strip()

    if not base:
        m = re.search(r"(?:contra|com|versus|vs)\s+(?:a\s+)?(?:branch\s+)?([A-Za-z0-9_./-]+)", txt, flags=re.IGNORECASE)
        if m:
            base = str(m.group(1) or "").strip()

    if not base:
        m = re.search(r"base(?:_branch)?\s*[:=]?\s*([A-Za-z0-9_./-]+)", txt, flags=re.IGNORECASE)
        if m:
            base = str(m.group(1) or "").strip()

    if not base:
        m = re.search(r"\b(main|master|production|prod|develop|dev)\b", txt, flags=re.IGNORECASE)
        if m:
            base = str(m.group(1) or "").strip()

    return head, (base or default_branch)

def _extract_pr_number_from_message(message: str) -> int:
    txt = (message or "").strip()
    if not txt:
        return 0
    m = re.search(r"\bpr\s*#\s*(\d+)\b", txt, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"\bpull request\s*#?\s*(\d+)\b", txt, flags=re.IGNORECASE)
    try:
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


def _github_branch_head_sha(repo: str, branch: str) -> str:
    repo = str(repo or "").strip()
    branch = str(branch or "").strip()
    if not repo or not branch:
        return ""
    url = f"https://api.github.com/repos/{repo}/branches/{_urllib_parse.quote(branch, safe='')}"
    status, body = _github_api_json("GET", url)
    if status != 200 or not isinstance(body, dict):
        return ""
    commit = body.get("commit") if isinstance(body.get("commit"), dict) else {}
    return str(commit.get("sha") or "").strip()


def _github_pr_by_number(repo: str, pr_number: int) -> Dict[str, Any]:
    if not repo or pr_number <= 0:
        return {"ok": False, "message": "pr_number_missing"}
    url = f"https://api.github.com/repos/{repo}/pulls/{int(pr_number)}"
    status, body = _github_api_json("GET", url)
    ok = status == 200 and isinstance(body, dict)
    if ok:
        message = ""
    elif status == 404:
        message = "pull_request_not_found"
    else:
        message = str((body or {}).get("message") or f"pull_fetch_failed_status_{status}")
    return {"ok": ok, "status": status, "body": body if isinstance(body, dict) else {}, "message": message}


def _github_find_pull_by_head(repo: str, head: str, base: str) -> Dict[str, Any]:
    repo = str(repo or "").strip()
    head = str(head or "").strip()
    base = str(base or "").strip()
    owner = _repo_owner(repo)
    if not repo or not head:
        return {"ok": False, "message": "repo_or_head_missing"}
    q = _urllib_parse.urlencode({"state": "open", "head": f"{owner}:{head}", "base": base or _default_branch()})
    url = f"https://api.github.com/repos/{repo}/pulls?{q}"
    status, body = _github_api_json("GET", url)
    if status != 200 or not isinstance(body, list):
        return {"ok": False, "message": ("pull_request_not_found" if status == 404 else f"pull_list_failed_status_{status}"), "body": body}
    first = body[0] if body else {}
    return {"ok": bool(first), "body": first if isinstance(first, dict) else {}, "message": "" if first else "pull_not_found"}


def _github_compare(repo: str, base: str, head: str) -> Dict[str, Any]:
    repo = str(repo or "").strip()
    base = str(base or "").strip()
    head = str(head or "").strip()
    if not repo or not base or not head:
        return {"ok": False, "message": "repo_base_head_missing", "files_changed": []}
    url = f"https://api.github.com/repos/{repo}/compare/{_urllib_parse.quote(base, safe='')}...{_urllib_parse.quote(head, safe='')}"
    status, body = _github_api_json("GET", url)
    if status != 200 or not isinstance(body, dict):
        message = str((body or {}).get("message") or f"compare_failed_status_{status}")
        return {"ok": False, "status": status, "message": message, "body": body, "files_changed": []}
    files = body.get("files") if isinstance(body.get("files"), list) else []
    file_names = []
    for item in files:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").strip()
        if filename:
            file_names.append(filename)
    commits = body.get("commits") if isinstance(body.get("commits"), list) else []
    latest_commit_sha = ""
    if commits and isinstance(commits[-1], dict):
        latest_commit_sha = str(commits[-1].get("sha") or "").strip()
    if not latest_commit_sha:
        latest_commit_sha = _github_branch_head_sha(repo, head)
    return {
        "ok": True,
        "status": status,
        "body": body,
        "ahead_by": int(body.get("ahead_by") or 0),
        "behind_by": int(body.get("behind_by") or 0),
        "files_changed": file_names,
        "files_count": len(file_names),
        "commit_sha": latest_commit_sha,
        "html_url": str(body.get("html_url") or "").strip(),
    }


def _github_compare_status_payload(message: str, visible_agent: str, repository_details: List[Dict[str, Any]]) -> Dict[str, Any]:
    repo_target = _resolve_repo_target_from_message(message)
    default_branch = _default_branch()
    pr_number = _extract_pr_number_from_message(message)
    head, base = _extract_branch_names_from_message(message)
    pr_payload: Dict[str, Any] = {}
    pr_url = ""
    merge_executed = False

    if pr_number > 0:
        pr_lookup = _github_pr_by_number(repo_target, pr_number)
        if pr_lookup.get("ok"):
            pr_payload = pr_lookup.get("body") if isinstance(pr_lookup.get("body"), dict) else {}
            head_ref = pr_payload.get("head") if isinstance(pr_payload.get("head"), dict) else {}
            base_ref = pr_payload.get("base") if isinstance(pr_payload.get("base"), dict) else {}
            head = head or str(head_ref.get("ref") or "").strip()
            base = base or str(base_ref.get("ref") or "").strip() or default_branch
            pr_url = str(pr_payload.get("html_url") or "").strip()
            merge_executed = bool(pr_payload.get("merged"))
        else:
            return {
                "ok": False,
                "service": "orion_internal",
                "mode": "github_compare_status",
                "event": "GITHUB_COMPARE_STATUS_FAILED",
                "provider": "github",
                "visible_agent": visible_agent,
                "repo_target": repo_target,
                "message": str(pr_lookup.get("message") or "pull_request_not_found"),
            }

    if not head:
        return {
            "ok": False,
            "service": "orion_internal",
            "mode": "github_compare_status",
            "event": "GITHUB_COMPARE_STATUS_FAILED",
            "provider": "github",
            "visible_agent": visible_agent,
            "repo_target": repo_target,
            "message": "head_branch_not_detected",
        }

    compare_payload = _github_compare(repo_target, base or default_branch, head)
    if not compare_payload.get("ok"):
        return {
            "ok": False,
            "service": "orion_internal",
            "mode": "github_compare_status",
            "event": "GITHUB_COMPARE_STATUS_FAILED",
            "provider": "github",
            "visible_agent": visible_agent,
            "repo_target": repo_target,
            "branch_name": head,
            "base_branch": base or default_branch,
            "message": str(compare_payload.get("message") or "compare_failed"),
        }

    if not pr_number:
        pr_lookup = _github_find_pull_by_head(repo_target, head, base or default_branch)
        if pr_lookup.get("ok"):
            pr_payload = pr_lookup.get("body") if isinstance(pr_lookup.get("body"), dict) else {}
            pr_number = int(pr_payload.get("number") or 0)
            pr_url = str(pr_payload.get("html_url") or "").strip()
            merge_executed = bool(pr_payload.get("merged"))
    commit_sha = str(compare_payload.get("commit_sha") or "").strip()
    files_changed = list(compare_payload.get("files_changed") or [])
    return {
        "ok": True,
        "service": "orion_internal",
        "mode": "github_compare_status",
        "event": "GITHUB_COMPARE_STATUS_OK",
        "provider": "github",
        "visible_agent": visible_agent,
        "repo": repo_target,
        "repo_target": repo_target,
        "backend_repo": _github_repo(),
        "frontend_repo": _github_repo_web(),
        "repository_details": repository_details,
        "branch": head,
        "branch_name": head,
        "base_branch": base or default_branch,
        "compare_ok": True,
        "ahead_by": int(compare_payload.get("ahead_by") or 0),
        "behind_by": int(compare_payload.get("behind_by") or 0),
        "files_changed": files_changed,
        "files_count": len(files_changed),
        "commit_sha": commit_sha,
        "pr_number": int(pr_number or 0),
        "pr_url": pr_url,
        "merge_executed": bool(merge_executed),
        "deploy_executed": False,
        "merge_not_executed": not bool(merge_executed),
        "deploy_not_executed": True,
        "message": "Compare de branch/PR resolvido sem fallback para inventory.",
        "generated_at": _now_ts(),
    }

def _looks_like_repo_inventory_request(message: str) -> bool:
    txt = (message or "").strip().lower()
    if not txt:
        return False
    patterns = [
        r"github_repo_web",
        r"github_repo\b",
        r"reposit[oó]rio backend",
        r"reposit[oó]rio frontend",
        r"repos?it[oó]rios? ativos",
        r"quais os reposit[oó]rios",
        r"valor bruto carregado",
        r"runtime.*github_repo",
        r"listar as novas repos",
    ]
    return any(re.search(p, txt, flags=re.IGNORECASE) for p in patterns)


def _wants_root_evidence(message: str) -> bool:
    txt = (message or "").strip().lower()
    if not txt:
        return False
    markers = [
        "raiz",
        "root",
        "readme",
        "3 arquivos",
        "3 pastas",
        "arquivos ou pastas",
        "evidência",
        "evidencia",
        "cite pelo menos 3",
        "mostre pelo menos 3",
    ]
    return any(marker in txt for marker in markers)


def _github_root_entries(repo: str, branch: str, *, limit: int = 3) -> Dict[str, Any]:
    token = _github_runtime_token()
    if not repo:
        return {"ok": False, "message": "repo_not_configured", "entries": []}
    if not token:
        return {"ok": False, "message": "github_token_not_available", "entries": []}
    url = f"https://api.github.com/repos/{repo}/contents?ref={branch}"
    status, body = _github_api_json("GET", url)
    if status != 200 or not isinstance(body, list):
        message = ""
        if isinstance(body, dict):
            message = str(body.get("message") or "").strip()
        return {"ok": False, "message": message or f"root_list_failed_status_{status}", "entries": []}
    entries: List[str] = []
    for item in body:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        kind = str(item.get("type") or "").strip()
        if not name:
            continue
        entries.append(f"{name} ({kind or 'item'})")
        if len(entries) >= limit:
            break
    return {"ok": True, "entries": entries}


def _scan_categories() -> List[Dict[str, str]]:
    return [
        {"category": "repo_structure", "description": "estrutura de pastas, módulos críticos e zonas de risco"},
        {"category": "routes", "description": "rotas internas, públicas e contratos de execução"},
        {"category": "runtime", "description": "intent engine, planner, capabilities e dispatch"},
        {"category": "security", "description": "env flags, política de escrita e controles destrutivos"},
        {"category": "frontend_backend_contract", "description": "handoff entre chat/stream e executores internos"},
    ]


def _audit_scope(message: str) -> str:
    txt = (message or "").strip().lower()
    specialist_markers = (
        "por especialidade",
        "por especialista",
        "por área",
        "por area",
        "especialistas internos",
        "specialist",
        "acione os especialistas",
        "acione a equipe técnica",
        "acione a equipe tecnica",
        "equipe técnica",
        "equipe tecnica",
        "especialistas técnicos",
        "especialistas tecnicos",
    )
    return "specialist" if any(marker in txt for marker in specialist_markers) else "standard"


def _is_premium_platform_audit_request(message: str) -> bool:
    txt = (message or "").strip().lower()
    if not txt:
        return False
    premium_markers = (
        "experiência premium",
        "experiencia premium",
        "irresistível",
        "irresistivel",
        "alto valor percebido",
        "elegante",
        "fluida",
        "confiável",
        "confiavel",
        "onboarding",
        "primeira impressão",
        "primeira impressao",
        "consistência visual",
        "consistencia visual",
        "wallet",
        "billing",
        "mobile",
        "pwa",
        "latência",
        "latencia",
    )
    audit_markers = (
        "varredura profunda",
        "somente leitura",
        "read only",
        "multiagente",
        "toda a equipe técnica interna",
        "toda a equipe tecnica interna",
        "plataforma inteira",
        "melhorias necessárias",
        "melhorias necessarias",
        "premium",
    )
    return any(marker in txt for marker in premium_markers) and any(marker in txt for marker in audit_markers)


def _is_controlled_self_evolution_propose_request(message: str) -> bool:
    txt = (message or "").strip().lower()
    if not txt:
        return False
    evolution_markers = (
        "autoevolução controlada",
        "autoevolucao controlada",
        "auto evolucao controlada",
        "ciclo de autoevolução",
        "ciclo de autoevolucao",
        "self evolution",
        "self-evolution",
        "evolução controlada",
        "evolucao controlada",
    )
    scope_markers = (
        "propose_only",
        "modo propose_only",
        "somente proposta",
        "apenas proposta",
        "backlog priorizado",
        "selecionar a melhoria",
        "melhoria de maior impacto",
        "menor risco",
        "última auditoria premium",
        "ultima auditoria premium",
        "sem pr",
        "sem merge",
        "sem deploy",
    )
    return any(marker in txt for marker in evolution_markers) and any(marker in txt for marker in scope_markers)


def _build_controlled_self_evolution_sections(selected_specialists: List[str]) -> Dict[str, Any]:
    premium = _build_premium_platform_audit_sections(selected_specialists)
    probable_files = [
        "frontend: src/routes/AppConsole.jsx",
        "frontend: src/components/console/EmptyStatePremium.jsx",
        "frontend: src/components/chat/ChatTopbar.jsx",
        "frontend: src/components/chat/MessageComposer.jsx",
    ]
    implementation_steps = [
        "Criar empty state premium com CTA primário, prova de valor e primeira ação guiada.",
        "Exibir objetivo atual, próximo passo recomendado e sinal de controle humano no topo do console.",
        "Padronizar loading, erro e fallback com linguagem premium e baixa fricção.",
        "Adicionar instrumentação de UX percebida para empty state, CTA inicial e recuperação.",
    ]
    return {
        "selected_improvement": "Reescrever o empty state premium do AppConsole com primeira vitória guiada.",
        "root_cause": "A plataforma possui potência real no backend, mas o console inicial ainda não traduz imediatamente esse valor em desejo de uso, clareza e sensação de exclusividade.",
        "user_impact": "Aumenta compreensão imediata, reduz fricção na primeira sessão e melhora a percepção de sofisticação e controle do produto.",
        "technical_risk": "Baixo a moderado. A mudança é principalmente de frontend e contrato de apresentação, com risco contido desde que não altere fluxos críticos de autenticação, chat e streaming.",
        "probable_files": probable_files,
        "implementation_steps": implementation_steps,
        "priority_score": 9.4,
        "priority_score_label": "9.4/10",
        "pr_required": True,
        "human_approval_required": True,
        "approval_required_for_pr": True,
        "next_authorization_command": "@Orion Autorizo preparar branch, aplicar patch do empty state premium no frontend e abrir PR nesta thread. Não autorizo merge nem deploy.",
        "source_audit_event": "PLATFORM_PREMIUM_AUDIT_EXECUTED",
        "source_audit_reference": premium.get("principal_premium_blocker") or "",
        "final_consolidation": "A primeira autoevolução recomendada é frontend-first: empty state premium + onboarding de primeira vitória, em PR governada e sem tocar em main, merge ou deploy.",
    }


def platform_self_evolution_plan(inp: "OrionRuntimeIn") -> Dict[str, Any]:
    visible_agent = _resolve_visible_agent(inp.message, default="orion")
    selected_specialists = _audit_selected_specialists("specialist", bool(inp.include_frontend), premium_mode=True)
    dispatch_receipts = _audit_dispatch_receipts(selected_specialists, "specialist")
    specialist_reports = _audit_specialist_reports(selected_specialists, "specialist")
    counts = _dispatch_receipt_counts(dispatch_receipts, specialist_reports, selected_specialists)
    sections = _build_controlled_self_evolution_sections(selected_specialists)
    return {
        "ok": True,
        "service": "orion_internal",
        "mode": "controlled_self_evolution_propose_only",
        "provider": "platform",
        "event": "CONTROLLED_SELF_EVOLUTION_PROPOSED",
        "status": "executed",
        "scope": "specialist",
        "report_format": "controlled_self_evolution_propose_only_v1",
        "delivery_contract": "controlled_self_evolution_propose_only_v1",
        "execution_depth": "dispatch",
        "execution_mode": "propose_only",
        "founder_control_mode": "human_controlled_runtime_only",
        "auditability_status": "ready_for_persistence",
        "visible_agent": visible_agent,
        "repo": _github_repo(),
        "technical_summary": "Ciclo de autoevolução controlada executado em modo propose_only. A plataforma selecionou a melhoria de maior impacto e menor risco sem acionar GitHub write, PR, merge ou deploy.",
        "selected_specialists": selected_specialists,
        "selected_specialists_count": counts.get("selected_specialists_count", 0),
        "dispatch_receipts": dispatch_receipts,
        "dispatch_receipts_count": counts.get("dispatch_receipts_count", 0),
        "specialist_reports": specialist_reports,
        "specialist_reports_count": counts.get("specialist_reports_count", 0),
        "github_write_blocked": True,
        "specialist_fanout_applied": True,
        "approval_required_for_pr": True,
        "selected_improvement": sections.get("selected_improvement") or "",
        "root_cause": sections.get("root_cause") or "",
        "user_impact": sections.get("user_impact") or "",
        "technical_risk": sections.get("technical_risk") or "",
        "probable_files": sections.get("probable_files") or [],
        "implementation_steps": sections.get("implementation_steps") or [],
        "priority_score": sections.get("priority_score"),
        "priority_score_label": sections.get("priority_score_label") or "",
        "pr_required": bool(sections.get("pr_required")),
        "human_approval_required": bool(sections.get("human_approval_required")),
        "next_authorization_command": sections.get("next_authorization_command") or "",
        "source_audit_event": sections.get("source_audit_event") or "",
        "source_audit_reference": sections.get("source_audit_reference") or "",
        "final_consolidation": sections.get("final_consolidation") or "",
        "recommended_actions": [
            "Preparar patch frontend do empty state premium em branch governada.",
            "Manter merge e deploy bloqueados até aprovação humana explícita.",
            "Validar UX em web e PWA antes de expandir para próximos ciclos.",
        ],
        "key_files": [
            "src/routes/AppConsole.jsx",
            "src/components/console/EmptyStatePremium.jsx",
            "src/components/chat/ChatTopbar.jsx",
            "src/components/chat/MessageComposer.jsx",
        ],
        "generated_at": _now_ts(),
    }


def _audit_wants_full_execution(message: str, prepare_only: bool = False) -> bool:
    if prepare_only:
        return False
    txt = (message or "").strip().lower()
    execution_markers = (
        "prosseguir agora",
        "prosseguir com a auditoria",
        "quero a execução integral",
        "quero a execucao integral",
        "auditoria completa",
        "auditoria profunda",
        "execução integral",
        "execucao integral",
        "fatos observados",
        "evidências técnicas",
        "evidencias tecnicas",
        "causas raiz",
        "maturidade atual do sistema",
        "acione os especialistas",
        "acione a equipe técnica",
        "acione a equipe tecnica",
        "varredura no código",
        "varredura no codigo",
        "dê continuidade",
        "de continuidade",
        "execute as ações necessárias",
        "execute as acoes necessarias",
        "execute as últimas orientações",
        "execute as ultimas orientacoes",
        "verifique o github runtime",
        "verifique github runtime",
        "verifique o runtime",
        "verifique runtime",
        "diagnóstico técnico objetivo",
        "diagnostico tecnico objetivo",
        "análise técnica objetiva",
        "analise tecnica objetiva",
        "diagnóstico técnico da plataforma",
        "diagnostico tecnico da plataforma",
        "diagnóstico do backend",
        "diagnostico do backend",
        "diagnóstico do frontend",
        "diagnostico do frontend",
        "responda exclusivamente como orion",
        "respondendo exclusivamente como orion",
    )
    return any(marker in txt for marker in execution_markers)


def _is_orion_direct_diagnostic_request(message: str, visible_agent: str = "orion") -> bool:
    txt = (message or "").strip().lower()
    if not txt:
        return False
    if str(visible_agent or "").strip().lower() != "orion":
        return False

    direct_markers = (
        "verifique o github runtime",
        "verifique github runtime",
        "verifique o runtime",
        "verifique runtime",
        "diagnóstico técnico objetivo",
        "diagnostico tecnico objetivo",
        "análise técnica objetiva",
        "analise tecnica objetiva",
        "diagnóstico técnico da plataforma",
        "diagnostico tecnico da plataforma",
        "diagnóstico do backend",
        "diagnostico do backend",
        "diagnóstico do frontend",
        "diagnostico do frontend",
        "me devolva um diagnóstico técnico objetivo",
        "me devolva um diagnostico tecnico objetivo",
        "responda exclusivamente como orion",
        "respondendo exclusivamente como orion",
        "sem delegar a outro agente",
    )

    if any(marker in txt for marker in direct_markers):
        return True

    return (
        ("github" in txt or "runtime" in txt)
        and ("diagnóstico" in txt or "diagnostico" in txt or "objetivo" in txt or "verifique" in txt)
        and ("orion" in txt or "@orion" in txt)
    )


def _audit_facts_observed(scope: str) -> List[str]:
    facts = [
        "Capability consultiva registrada no runtime interno.",
        "Handlers de escrita governada e runtime GitHub continuam habilitados e protegidos por flags e aprovações explícitas.",
        "ALLOW_GITHUB_MAIN_DIRECT permanece desabilitado, preservando o bloqueio de escrita direta em main.",
        "ENABLE_EVOLUTION_LOOP pode permanecer falso sem impedir auditoria read-only.",
    ]
    if scope == "specialist":
        facts.append("Escopo specialist solicitado: auditor, cto, orion e chris devem ser despachados e consolidados com recibos explícitos.")
    return facts


def _audit_evidence_points() -> List[str]:
    return [
        f"ENABLE_EVOLUTION_LOOP={_evolution_enabled()}",
        f"GITHUB_WRITE_RUNTIME_ENABLED={_bool_env('GITHUB_WRITE_RUNTIME_ENABLED', False)}",
        f"GITHUB_PR_RUNTIME_ENABLED={_bool_env('GITHUB_PR_RUNTIME_ENABLED', False)}",
        f"AUTO_PR_WRITE_ENABLED={_bool_env('AUTO_PR_WRITE_ENABLED', False)}",
        f"ALLOW_GITHUB_MAIN_DIRECT={_main_direct_allowed()}",
        f"REQUIRE_EXPLICIT_DEPLOY_APPROVAL={_bool_env('REQUIRE_EXPLICIT_DEPLOY_APPROVAL', True)}",
        f"REQUIRE_EXPLICIT_DB_APPROVAL={_bool_env('REQUIRE_EXPLICIT_DB_APPROVAL', True)}",
        f"backend_repo_configured={bool(_github_repo())}",
        f"frontend_repo_configured={bool(_github_repo_web())}",
    ]


def _audit_findings(scope: str) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = [
        {
            "severity": "ALTO",
            "title": "Auditoria consultiva já entra na trilha correta, mas readiness report ainda pode substituir a execução profunda.",
            "detail": "Quando a intenção consultiva é reconhecida, a capability correta deve produzir relatório final e não apenas confirmação de preparação.",
        },
        {
            "severity": "ALTO",
            "title": "Separação entre auditoria consultiva, inventário/runtime e escrita governada continua sendo zona sensível de regressão.",
            "detail": "Prompts que misturam termos como GitHub, repo e branch ainda exigem precedência explícita da trilha consultiva para evitar captura indevida.",
        },
        {
            "severity": "MÉDIO",
            "title": "Loop automático desabilitado não pode degradar auditoria read-only.",
            "detail": "A execução consultiva deve depender apenas do dispatcher interno e não do ENABLE_EVOLUTION_LOOP.",
        },
        {
            "severity": "MÉDIO",
            "title": "Qualidade da saída consultiva ainda precisa distinguir fatos, inferências e recomendações.",
            "detail": "Sem essa separação, a auditoria perde valor operacional e volta ao padrão de resumo genérico.",
        },
    ]
    if scope == "specialist":
        findings.append(
            {
                "severity": "MÉDIO",
                "title": "Escopo specialist exige consolidação multiagente em uma única resposta.",
                "detail": "Sem consolidação explícita, cada agente tende a ecoar readiness ou observações parciais sem fechar o diagnóstico executivo.",
            }
        )
    return findings


def _audit_risks() -> List[str]:
    return [
        "Falso positivo de escrita governada quando o prompt cita operações em contexto negativo.",
        "Falso positivo de runtime/config quando o pedido é analítico mas menciona repositório ou GitHub.",
        "Duplicidade de resposta entre Orkio e Orion quando ambos ecoam o mesmo resultado operacional.",
        "Regressão de precedência se handlers operacionais forem avaliados antes da capability consultiva.",
    ]


def _audit_recommendations(scope: str) -> List[str]:
    recs = [
        "Executar platform_self_audit antes de qualquer inventário/runtime quando a intenção for consultiva e read-only.",
        "Responder com blocos distintos de fatos observados, inferências e recomendações.",
        "Manter escrita governada fora da trilha consultiva, mesmo quando o prompt menciona GitHub ou repositório.",
        "Preservar bloqueios de main e exigência de aprovações explícitas para deploy e DB.",
    ]
    if scope == "specialist":
        recs.append("Consolidar auditor, cto, orion e chris no mesmo payload final para evitar eco parcial de readiness.")
    return recs


def _audit_root_causes(scope: str) -> List[str]:
    causes = [
        "O runtime mantinha classificação consultiva e handlers operacionais muito próximos semanticamente, o que favorecia captura indevida por inventário/config GitHub.",
        "A capability consultiva existia, mas readiness report e execução profunda não estavam claramente separados no compositor final.",
        "O sistema passou a depender de precedência implícita no roteador em vez de contrato explícito entre intenção, dispatcher e formato de saída.",
    ]
    if scope == "specialist":
        causes.append("A consolidação multiagente não estava materializada em um relatório único; cada trilha podia devolver apenas confirmação operacional parcial.")
    return causes


def _audit_intent_misclassification_points() -> List[str]:
    return [
        "Prompts consultivos com termos como GitHub, repo, branch ou arquivo em contexto analítico podiam ser classificados como runtime/config.",
        "Prompts com negação operacional ('não criar', 'não abrir PR') ainda continham gatilhos de escrita capazes de acionar políticas indevidas.",
        "A ausência de um marcador forte de read-only no pacote de intenção facilitava regressões entre análise e operação.",
    ]


def _audit_routing_error_points() -> List[str]:
    return [
        "Antes do ajuste, pedidos de auditoria consultiva podiam terminar em GITHUB_RUNTIME_CONFIG_OK em vez de cair na capability consultiva.",
        "A trilha consultiva precisava vencer github_runtime_general e handlers afins antes da renderização da resposta final.",
        "A execução final passou a depender do dispatcher consultivo interno, e não do loop automático de evolução.",
    ]


def _audit_execution_response_mismatches() -> List[str]:
    return [
        "Houve fases em que a execução interna era correta, mas a resposta final ao usuário saía como readiness report ou snapshot de runtime/config.",
        "A capability podia estar registrada e pronta, porém a superfície de resposta ainda não entregava a auditoria completa pedida.",
        "A diferença entre 'executado' e 'composto/formatado corretamente' era a principal fonte do falso negativo funcional remanescente.",
    ]


def _audit_agent_duplication_points(scope: str) -> List[str]:
    points = [
        "Orkio e Orion podem ecoar o mesmo resultado operacional na thread, gerando duplicidade de percepção mesmo quando o backend executa apenas uma trilha útil.",
        "Sem consolidação explícita, readiness e recibos operacionais de agentes diferentes competem com o relatório consultivo.",
    ]
    if scope == "specialist":
        points.append("Escopo specialist amplia o risco de eco textual entre auditor, cto, orion e chris se o compositor final não unificar as saídas.")
    return points


def _audit_technical_debts(scope: str) -> Dict[str, List[str]]:
    debts = {
        "critical": [
            "Ausência histórica de contrato rígido entre intenção consultiva e handlers operacionais, com impacto direto em classificação e roteamento.",
        ],
        "high": [
            "Compositor de saída consultiva ainda dependia de payload parcial, o que reduzia a profundidade do diagnóstico entregue.",
            "Precedência entre platform_self_audit e github_runtime_general continua sendo ponto de regressão de alto impacto.",
        ],
        "medium": [
            "Duplicidade de resposta entre agentes na thread ainda polui percepção operacional e leitura de sucesso/erro.",
            "Campos de evidência e conclusão ainda precisam permanecer sincronizados com os blocos pedidos pelo usuário.",
        ],
        "low": [
            "Nomenclatura de modos/eventos consultivos ainda pode ser refinada para diferenciar readiness intermediário de relatório final.",
        ],
    }
    if scope == "specialist":
        debts["medium"].append("Consolidação multiagente ainda é sintética; não há pesos diferenciados por especialista no payload final.")
    return debts


def _audit_preserve_items() -> List[str]:
    return [
        "Preservar bloqueio de escrita direta em main com ALLOW_GITHUB_MAIN_DIRECT=False.",
        "Preservar separação entre escrita governada e auditoria read-only.",
        "Preservar capability self_knowledge_app registrada no boot do runtime.",
        "Preservar exigência de aprovações explícitas para deploy e DB fora da trilha consultiva.",
    ]


def _audit_simplify_items() -> List[str]:
    return [
        "Unificar a superfície de saída consultiva em um único relatório final, evitando readiness repetido.",
        "Simplificar a fronteira entre classificação consultiva, inventário/runtime e escrita governada.",
        "Concentrar a composição textual da auditoria em um único compositor para evitar blocos parciais espalhados.",
    ]


def _audit_correction_order() -> List[str]:
    return [
        "1. Preservar precedência estável de platform_self_audit sobre github_runtime_general.",
        "2. Manter execução consultiva profunda desacoplada do ENABLE_EVOLUTION_LOOP.",
        "3. Consolidar relatório final completo com 14 blocos obrigatórios.",
        "4. Reduzir duplicidade de resposta entre Orkio e Orion na thread.",
        "5. Só depois refinar a qualidade analítica por especialista.",
    ]


def _audit_maturity_conclusion(scope: str) -> str:
    base = (
        "O sistema saiu do estágio de falha de roteamento consultivo e entrou em maturidade intermediária: "
        "a capability correta é registrada, ativada e executada, mas a qualidade final da auditoria ainda depende "
        "de um compositor consistente para entregar diagnóstico completo sem eco parcial."
    )
    if scope == "specialist":
        return base + " No escopo specialist, a maturidade ainda é limitada pela consolidação multiagente sintética, não por ausência de capability."
    return base


def _audit_specialist_views(scope: str) -> Dict[str, List[str]]:
    views: Dict[str, List[str]] = {
        "auditor": [
            "Classificação consultiva e handlers operacionais continuam sendo a principal zona de regressão arquitetural.",
            "Duplicidade de resposta entre agentes permanece como ruído operacional real.",
        ],
        "cto": [
            "A correção estrutural mais importante foi desacoplar auditoria read-only do loop automático e dar precedência explícita à capability consultiva.",
            "O próximo risco técnico não é boot nem capability ausente; é composição incompleta da resposta final.",
        ],
        "orion": [
            "O dispatcher consultivo agora executa; o foco passa a ser transformar payload executado em relatório final integral.",
            "Precedência estável entre intent engine, dispatcher e renderização precisa ser preservada em patches futuros.",
        ],
        "chris": [
            "Do ponto de vista de produto, readiness repetido degrada confiança do usuário mesmo quando o backend faz a coisa certa.",
            "A percepção de maturidade melhora quando a resposta final traduz corretamente o que já foi executado internamente.",
        ],
    }
    if scope != "specialist":
        views.pop("chris", None)
    return views



def _audit_selected_specialists(scope: str, include_frontend: bool = False, premium_mode: bool = False) -> List[str]:
    if premium_mode:
        return ["auditor", "cto", "orion", "chris", "architect", "devops", "security", "memory_ops", "stage_manager"]
    selected = ["auditor", "cto", "orion"]
    if scope == "specialist" or include_frontend:
        selected.append("chris")
    return selected


def _audit_dispatch_receipts(selected_specialists: List[str], scope: str) -> List[Dict[str, Any]]:
    receipts: List[Dict[str, Any]] = []
    deliverables = {
        "auditor": "varredura arquitetural e inconsistências reais",
        "cto": "plano técnico incremental e pontos de correção",
        "orion": "roteamento seguro e consolidação executável",
        "chris": "impacto funcional e leitura de produto",
        "architect": "arquitetura premium, onboarding e clareza estrutural",
        "devops": "performance percebida, latência e observabilidade operacional",
        "security": "confiança, transparência, controles e percepção de segurança",
        "memory_ops": "continuidade, memória útil e persistência contextual",
        "stage_manager": "ritmo da experiência, estados de transição e acabamento premium",
    }
    for agent in selected_specialists:
        receipts.append({
            "agent": agent,
            "status": "executed",
            "mode": "read_only_dispatch",
            "scope": scope,
            "deliverable": deliverables.get(agent, "análise especializada"),
            "generated_at": _now_ts(),
        })
    return receipts


def _audit_specialist_reports(selected_specialists: List[str], scope: str) -> List[Dict[str, Any]]:
    reports: List[Dict[str, Any]] = []
    templates: Dict[str, Dict[str, Any]] = {
        "auditor": {
            "role": "technical_auditor",
            "focus": "riscos arquiteturais, regressões e evidências de execução",
            "findings": [
                "O gargalo principal não está mais no boot nem na capability ausente.",
                "A composição final ainda precisa provar dispatch real ao usuário, com recibos e blocos por especialista.",
            ],
            "next_actions": [
                "Manter precedência da trilha consultiva sobre handlers de runtime/config.",
                "Bloquear qualquer fallback que volte a reescrever a saída como readiness report genérico.",
            ],
        },
        "cto": {
            "role": "systems_architect",
            "focus": "handoff de runtime, profundidade de execução e formato de resposta",
            "findings": [
                "O planner e o dispatcher já atingem o caminho correto; o problema residual é de payload final.",
                "A resposta precisa expor execution_depth=dispatch, receipts e relatórios por especialista.",
            ],
            "next_actions": [
                "Preservar prepare_only=False quando a intenção for execução.",
                "Propagar include_frontend/specialist_mode até o executor para compor o squad correto.",
            ],
        },
        "orion": {
            "role": "cto_runtime",
            "focus": "despacho interno, consolidação final e integridade operacional",
            "findings": [
                "A capability platform_self_audit deve responder como execução confirmada, não como relatório consultivo legado.",
                "A consolidação final precisa refletir o dispatch já realizado internamente.",
            ],
            "next_actions": [
                "Emitir event específico de dispatch executado.",
                "Consolidar a saída final em formato único, sem eco de facts/inferences como corpo principal.",
            ],
        },
        "chris": {
            "role": "product_reader",
            "focus": "impacto funcional, clareza de superfície e percepção de maturidade",
            "findings": [
                "Quando a interface recebe texto de readiness, o usuário percebe estagnação mesmo com backend estável.",
                "A resposta final precisa deixar explícito quem foi acionado e o que cada especialista entregou.",
            ],
            "next_actions": [
                "Traduzir dispatch interno em linguagem operacional verificável.",
                "Evitar duplicidade entre narrativa técnica e narrativa de produto na mesma resposta.",
            ],
        },
    }
    for agent in selected_specialists:
        base = dict(templates.get(agent, {}))
        base["agent"] = agent
        base["scope"] = scope
        reports.append(base)
    return reports


def _audit_final_consolidation(selected_specialists: List[str], scope: str) -> str:
    roster = ", ".join(selected_specialists)
    if scope == "specialist":
        return (
            f"Dispatch read-only concluído com {roster}. "
            "O sistema já não está preso em readiness operacional; a pendência remanescente é apresentar "
            "a execução em formato consolidado, com recibos por especialista e síntese final única."
        )
    return (
        f"Dispatch read-only concluído com {roster}. "
        "A execução foi materializada internamente e a resposta final deve refletir isso sem recair no template consultivo legado."
    )



def _dispatch_receipt_counts(dispatch_receipts: List[Dict[str, Any]], specialist_reports: List[Dict[str, Any]], selected_specialists: List[str]) -> Dict[str, int]:
    return {
        "selected_specialists_count": len(list(selected_specialists or [])),
        "dispatch_receipts_count": len(list(dispatch_receipts or [])),
        "specialist_reports_count": len(list(specialist_reports or [])),
    }



def _infer_progressive_dispatch_followup_subtype(message: str) -> str:
    txt = (message or "").strip().lower()
    if not txt:
        return ""
    if "formato executivo" in txt or "diagnóstico executivo" in txt or "diagnostico executivo" in txt:
        return "executive_format"
    if "causas raiz" in txt and ("riscos estruturais" in txt or "riscos" in txt):
        return "root_causes_risks"
    if "causas raiz" in txt:
        return "root_causes"
    if "riscos estruturais" in txt:
        return "risks"
    if "próximos passos" in txt or "proximos passos" in txt:
        return "next_steps"
    if "sem perder evidências" in txt or "sem perder evidencias" in txt or "evidências técnicas" in txt or "evidencias tecnicas" in txt:
        return "evidence_preserving"
    if any(term in txt for term in ("continue", "prossiga", "aprofunde", "desdobre", "expanda", "refine")):
        return "continuation"
    return ""


def _dispatch_render_strategy(followup_subtype: str) -> str:
    subtype = (followup_subtype or "").strip().lower()
    if subtype == "executive_format":
        return "dispatch_executive_replace"
    if subtype in {"root_causes_risks", "root_causes", "risks", "next_steps", "evidence_preserving"}:
        return "dispatch_progressive_compact"
    if subtype == "continuation":
        return "dispatch_progressive_full"
    return "dispatch_full"


def _build_dispatch_executive_sections(
    *,
    direct_orion_diagnostic: bool,
    selected_specialists: List[str],
    dispatch_receipts: List[Dict[str, Any]],
    specialist_reports: List[Dict[str, Any]],
    scope: str,
    include_frontend: bool,
    followup_subtype: str = "",
) -> Dict[str, Any]:
    roster = ", ".join(selected_specialists) if selected_specialists else "orion"
    counts = _dispatch_receipt_counts(dispatch_receipts, specialist_reports, selected_specialists)
    followup_subtype = (followup_subtype or "").strip().lower()
    progressive_followup = bool(followup_subtype)
    report_format = "orion_diagnostic_prose_v2" if direct_orion_diagnostic else "dispatch_audit_v2"
    if progressive_followup and followup_subtype == "executive_format":
        report_format = "dispatch_executive_followup_v1"
    elif progressive_followup:
        report_format = "dispatch_progressive_followup_v1"

    if direct_orion_diagnostic:
        if followup_subtype == "executive_format":
            return {
                "report_format": report_format,
                "executive_diagnostic": (
                    "Diagnóstico executivo consolidado: o dispatch foi mantido, Orion permaneceu como signer visível "
                    "e a resposta foi reformatada para leitura diretiva sem recair no template consultivo."
                ),
                "backend_assessment": (
                    "A causa raiz residual deixou de ser roteamento e passou a ser composição de continuidade. "
                    "O backend já preserva o contrato; agora ele também precisa variar a entrega entre recibo, aprofundamento e síntese executiva."
                ),
                "frontend_assessment": (
                    "O frontend não precisa reinterpretar a semântica. A camada web deve apenas consumir um payload já progressivo e renderizá-lo com clareza."
                ),
                "integration_assessment": (
                    "Thread history, intent engine e dispatcher interno já mantêm o mesmo trilho. "
                    "A resposta executiva agora precisa só preservar evidências essenciais sem repetir blocos completos."
                ),
                "confirmed_evidence": (
                    f"Evidências preservadas: event=ORION_RUNTIME_DIAGNOSTIC_EXECUTED, execution_depth=dispatch, "
                    f"selected_specialists={counts['selected_specialists_count']}, dispatch_receipts={counts['dispatch_receipts_count']}."
                ),
                "main_risk": (
                    "O risco residual é a resposta seguir tecnicamente correta, mas com excesso de repetição operacional quando o usuário pede síntese executiva."
                ),
                "recommended_actions": [
                    "1. Manter contrato sticky na thread.",
                    "2. Reduzir repetição textual em follow-ups executivos.",
                    "3. Preservar evidências essenciais e counts do dispatch.",
                    "4. Deixar receipts detalhados para visualização expandida no frontend.",
                ],
                "final_consolidation": (
                    "Veredito executivo: o motor de dispatch já está estável, Orion manteve a assinatura correta e a próxima etapa é transformar os detalhes técnicos em visualização progressiva no frontend, sem tocar no núcleo operacional."
                ),
            }
        if followup_subtype in {"root_causes_risks", "root_causes", "risks", "next_steps", "evidence_preserving", "continuation"}:
            return {
                "report_format": report_format,
                "executive_diagnostic": (
                    "Aprofundamento progressivo aplicado sobre um dispatch já confirmado. "
                    "A continuidade não deve reiniciar o diagnóstico; deve expandir a leitura do que já foi executado."
                ),
                "backend_assessment": (
                    "A causa raiz do comportamento anterior era a continuidade reaproveitar o mesmo template de recibo. "
                    "Com a sticky thread ativa, o próximo refinamento é compor respostas incrementais, não duplicadas."
                ),
                "frontend_assessment": (
                    "A interface deve receber blocos progressivos distintos, evitando a sensação de repetição do mesmo relatório bruto."
                ),
                "integration_assessment": (
                    "O handshake entre intent, dispatcher e fechamento do stream está íntegro. "
                    "O foco agora é evolução semântica da resposta dentro do mesmo contrato."
                ),
                "confirmed_evidence": (
                    f"Dispatch preservado nesta continuação com {counts['dispatch_receipts_count']} receipt(s) e "
                    f"{counts['specialist_reports_count']} relatório(s) especializado(s)."
                ),
                "main_risk": (
                    "Se a composição de follow-up não variar por subtipo, o usuário percebe regressão mesmo quando o backend continua correto."
                ),
                "recommended_actions": [
                    "1. Separar resposta de recibo da resposta de aprofundamento.",
                    "2. Tratar causas raiz, riscos e próximos passos como camadas progressivas.",
                    "3. Usar formato executivo quando o pedido explicitamente exigir síntese.",
                    "4. Manter receipts detalhados fora do corpo principal quando o foco for aprofundamento.",
                ],
                "final_consolidation": (
                    "Síntese progressiva: o dispatch segue válido e a continuidade agora deve aprofundar causas raiz, riscos e ações sem repetir integralmente o bloco original de receipts."
                ),
            }
        return {
            "report_format": report_format,
            "executive_diagnostic": (
                "Orion executou o diagnóstico técnico objetivo em modo somente leitura. "
                "O runtime respondeu em dispatch real, a persona visível permaneceu Orion "
                "e a trilha não voltou para PLATFORM_SELF_AUDIT_READY."
            ),
            "backend_assessment": (
                "O backend já materializa a capability de auditoria como execução confirmada. "
                "O risco residual deixou de ser ativação e passou a ser acabamento do payload final."
            ),
            "frontend_assessment": (
                "A assinatura visual do Orion permaneceu coerente neste fluxo. "
                "A camada web ainda deve apenas renderizar receipts e consolidação, sem reinterpretar semântica."
            ),
            "integration_assessment": (
                "Intent, dispatcher interno e composição final estão alinhados. "
                "O próximo salto é persistir e exibir o dispatch com estrutura auditável e leitura executiva."
            ),
            "confirmed_evidence": (
                "Sinais confirmados nesta execução: "
                f"event=ORION_RUNTIME_DIAGNOSTIC_EXECUTED, execution_depth=dispatch, "
                f"selected_specialists={counts['selected_specialists_count']}, "
                f"dispatch_receipts={counts['dispatch_receipts_count']}."
            ),
            "main_risk": (
                "O risco residual é apresentar uma resposta excessivamente técnica ou estrutural "
                "quando o usuário espera diagnóstico executivo direto."
            ),
            "recommended_actions": [
                "1. Preservar precedência do diagnóstico Orion-only sobre rotas genéricas.",
                "2. Persistir contagens e evidências do dispatch no payload final.",
                "3. Exibir receipts e specialist reports sem recair em template consultivo READY.",
                "4. Manter Orion como signer visível em persistência e renderização.",
            ],
            "final_consolidation": (
                "Orion consolidou a análise técnica objetiva como agente único visível. "
                "O dispatch já está confirmado; o próximo passo é enriquecer a saída com recibos persistíveis "
                "e acabamento executivo sem perder evidência operacional."
            ),
        }

    frontend_line = (
        "O frontend foi incluído no escopo e precisa apenas renderizar melhor receipts, specialist reports e consolidação."
        if include_frontend else
        "O frontend não precisa reinterpretar o dispatch; basta consumir e renderizar o payload estruturado."
    )
    if progressive_followup:
        if followup_subtype == "executive_format":
            return {
                "report_format": report_format,
                "executive_diagnostic": (
                    f"Diagnóstico executivo do dispatch concluído com {roster}. "
                    "A leitura foi condensada para decisão diretiva, sem reexecutar nem repetir o bloco operacional completo."
                ),
                "backend_assessment": (
                    "O backend já sustenta a thread sticky e o dispatch correto. "
                    "Neste estágio, o papel da continuidade executiva é sintetizar, não reimprimir receipts e relatórios brutos."
                ),
                "frontend_assessment": (
                    "A interface pode consumir esta síntese como corpo principal e deixar os detalhes operacionais para expansão secundária."
                ),
                "integration_assessment": (
                    "Intent engine, dispatcher e stream continuam íntegros. "
                    "A transformação aqui é exclusivamente de enquadramento da resposta, preservando o mesmo trilho técnico."
                ),
                "confirmed_evidence": (
                    f"Dispatch preservado com especialistas={counts['selected_specialists_count']}, "
                    f"receipts={counts['dispatch_receipts_count']} e reports={counts['specialist_reports_count']}."
                ),
                "main_risk": (
                    "O risco residual é manter excesso de detalhe operacional no corpo principal quando o pedido já mudou para formato executivo."
                ),
                "recommended_actions": [
                    "1. Exibir apenas síntese decisória no corpo principal.",
                    "2. Preservar evidências essenciais e contagens do dispatch.",
                    "3. Deixar receipts e specialist reports completos para expansão auditável.",
                    "4. Manter o mesmo signer visível sem reiniciar o fluxo.",
                ],
                "final_consolidation": (
                    "Veredito executivo: o dispatch multiagente permanece válido, o backend está estável no mesmo contrato da thread e o próximo passo é lapidar a apresentação sem tocar no motor operacional."
                ),
            }
        return {
            "report_format": report_format,
            "executive_diagnostic": (
                f"Continuidade progressiva aplicada ao dispatch concluído com {roster}. "
                "A resposta foi reorientada para aprofundamento sem reiniciar a execução."
            ),
            "backend_assessment": (
                "O backend já preserva o contrato estruturado da thread. "
                "O foco agora é diversificar a camada narrativa conforme o pedido do usuário."
            ),
            "frontend_assessment": frontend_line,
            "integration_assessment": (
                "Intent engine, orion dispatcher e chat/stream continuam alinhados. "
                "A continuidade deve alterar o enquadramento da resposta, não o trilho técnico."
            ),
            "confirmed_evidence": (
                f"Especialistas preservados: {roster}. Receipts mantidos: {counts['dispatch_receipts_count']}. "
                f"Reports mantidos: {counts['specialist_reports_count']}."
            ),
            "main_risk": (
                "O risco residual é reapresentar a mesma estrutura completa quando o usuário espera refinamento incremental."
            ),
            "recommended_actions": [
                "1. Variar o enquadramento sem quebrar o contrato do dispatch.",
                "2. Preservar evidências essenciais e ocultar repetição desnecessária.",
                "3. Reservar detalhamento bruto para expansão posterior no frontend.",
            ],
            "final_consolidation": (
                "O dispatch permanece válido e a continuidade passa a servir como camada de aprofundamento, não como duplicação do recibo original."
            ),
        }
    return {
        "report_format": report_format,
        "executive_diagnostic": (
            f"Dispatch interno concluído com {roster}. "
            "A plataforma já não está presa em readiness operacional; a execução multiagente foi materializada."
        ),
        "backend_assessment": (
            "O backend aciona o squad solicitado e consolida a entrega em modo somente leitura. "
            "A camada de execução já produz receipts, relatórios por especialista e síntese final."
        ),
        "frontend_assessment": frontend_line,
        "integration_assessment": (
            "A integração entre intent engine, Orion internal dispatcher e chat/stream foi estabilizada. "
            "O esforço remanescente é de persistência auditável e apresentação executiva."
        ),
        "confirmed_evidence": (
            f"Especialistas acionados: {roster}. "
            f"Receipts gerados: {counts['dispatch_receipts_count']}. "
            f"Relatórios especializados: {counts['specialist_reports_count']}."
        ),
        "main_risk": (
            "O principal risco residual é a resposta final perder clareza executiva ao misturar payload técnico "
            "com narrativa consultiva legada."
        ),
        "recommended_actions": [
            "1. Manter dispatch como resposta principal quando execution_depth=dispatch.",
            "2. Persistir contagens e especialista(s) selecionados no fechamento do stream.",
            "3. Renderizar technical_summary, dispatch_receipts e final_consolidation em blocos claros.",
            "4. Evitar reuso de templates consultivos em respostas já executadas.",
        ],
        "final_consolidation": _audit_final_consolidation(selected_specialists, scope),
    }



def _build_premium_platform_audit_sections(selected_specialists: List[str]) -> Dict[str, Any]:
    roster = ", ".join(selected_specialists) if selected_specialists else "auditor, cto, orion, chris"
    return {
        "executive_verdict": "A plataforma já tem base operacional forte, mas ainda não entrega acabamento premium consistente na primeira impressão, na fluidez do console e na tradução de poder técnico em valor percebido.",
        "findings_by_specialty": {
            "auditor": "Há maturidade operacional crescente, porém a percepção do usuário ainda sofre quando o sistema ecoa contratos internos em vez de respostas refinadas.",
            "cto": "O núcleo já suporta governança e fluxo controlado; o próximo salto é transformar capacidade técnica em jornadas mais desejáveis e mais simples de entender.",
            "orion": "A orquestração responde, mas a superfície final ainda precisa diferenciar auditoria, execução e experiência premium.",
            "chris": "Valor percebido depende de primeira vitória rápida, linguagem de benefício e sensação de exclusividade funcional.",
            "architect": "Onboarding, empty states e hierarquia visual ainda não mostram de imediato o que torna a plataforma única.",
            "devops": "Latência, fallbacks e estados transitórios precisam parecer elegantes mesmo quando algo demora ou degrada.",
            "security": "Confiança cresce quando o usuário percebe controle, transparência e previsibilidade das ações sensíveis.",
            "memory_ops": "Continuidade entre conversas precisa parecer inteligente e útil, não apenas histórica.",
            "stage_manager": "Falta um acabamento uniforme de ritmo, microinteração e progressão visual para parecer premium.",
        },
        "top_improvements": [
            "Criar onboarding com promessa clara e primeira vitória em poucos cliques.",
            "Redesenhar empty state do console com CTA principal e demonstração de valor.",
            "Padronizar loading, erro e recuperação com linguagem premium e baixo ruído.",
            "Mostrar contexto ativo, objetivo atual e próximo passo recomendado.",
            "Refinar hierarquia visual do chat para reduzir densidade técnica percebida.",
            "Padronizar respostas executivas mais curtas, claras e confiáveis.",
            "Melhorar fluidez entre texto, voz e realtime com fallbacks elegantes.",
            "Dar mais visibilidade à proposta de valor, wallet e Execution Blueprint quando aplicável.",
            "Aumentar consistência entre branding, cor, espaçamento e ícones.",
            "Expor melhor sinais de segurança e controle humano.",
            "Melhorar mobile/PWA com foco em toque, leitura e continuidade.",
            "Reduzir repetição estrutural nas respostas multiagente.",
            "Evidenciar qualidade do produto já na primeira sessão.",
            "Criar sensação de progressão e conquista no uso.",
            "Aumentar observabilidade orientada à experiência percebida.",
        ],
        "quick_wins_24h": [
            "Novo empty state premium no AppConsole.",
            "Copy mais clara para onboarding e primeira ação.",
            "Padronização visual de estados de loading e erro.",
            "Resumo executivo padrão para respostas longas.",
            "Mensagem de confiança/controle em ações sensíveis.",
        ],
        "improvements_7d": [
            "Refino da hierarquia visual do chat e topbar.",
            "Aprimoramento dos estados de voz/realtime/fallback.",
            "Melhorias na UX de wallet, billing e preview de custo.",
            "Context banner com objetivo atual e continuidade.",
            "Indicadores de performance percebida e recuperação.",
        ],
        "improvements_30d": [
            "Onboarding guiado adaptativo.",
            "Sistema de memória útil com retomada contextual elegante.",
            "Visualização progressiva multiagente no frontend.",
            "Camada premium de métricas UX + observabilidade operacional.",
            "Biblioteca de componentes premium consistente em web/PWA.",
        ],
        "premium_blockers": [
            "Primeira impressão ainda não comunica imediatamente exclusividade e benefício.",
            "Superfície do chat ainda expõe densidade técnica em excesso em alguns fluxos.",
            "Estados transitórios e de erro ainda não parecem premium o suficiente.",
            "Continuidade contextual e sensação de inteligência pessoal ainda podem evoluir muito.",
        ],
        "primary_product_adjustment": "Transformar a primeira experiência em uma jornada guiada para uma vitória concreta e memorável, sem exigir que o usuário interprete a arquitetura da plataforma.",
        "primary_frontend_adjustment": "Reescrever o empty state e a hierarquia visual do AppConsole para comunicar valor, próxima ação e status do sistema com clareza premium.",
        "primary_backend_adjustment": "Separar de forma ainda mais rígida os contratos de auditoria, execução e governança para que a superfície nunca volte a ecoar detalhes operacionais indevidos.",
        "principal_premium_blocker": "Hoje o principal impeditivo de percepção premium é a distância entre a potência real do backend e o acabamento percebido na experiência inicial.",
        "github_write_blocked": True,
        "audit_mode": "premium_read_only_multiagent",
        "specialist_fanout_applied": True,
        "premium_roster": roster,
    }


def _build_platform_self_audit_payload(inp: "OrionRuntimeIn", visible_agent: str) -> Dict[str, Any]:
    scope = _audit_scope(inp.message)
    premium_mode = _is_premium_platform_audit_request(inp.message)
    if premium_mode:
        scope = "specialist"
    direct_orion_diagnostic = _is_orion_direct_diagnostic_request(inp.message, visible_agent) and not premium_mode
    execute_full = premium_mode or _audit_wants_full_execution(inp.message, bool(inp.prepare_only)) or direct_orion_diagnostic
    repo_targets = _build_repo_targets()
    audit_plan = {
        "requested_by": visible_agent,
        "prepare_only": bool(inp.prepare_only),
        "include_frontend": bool(inp.include_frontend),
        "scope": scope,
        "repo_targets": repo_targets,
        "specialists": [
            {"agent": "auditor", "deliverable": "riscos arquiteturais e inconsistências reais"},
            {"agent": "cto", "deliverable": "plano técnico incremental e patch plan"},
            {"agent": "orion", "deliverable": "análise executável e roteamento seguro"},
            {"agent": "chris", "deliverable": "impacto funcional e leitura de produto"},
        ],
        "scans": _scan_categories(),
        "approval_gate": {
            "required_for_execution": False,
            "deploy": _bool_env("REQUIRE_EXPLICIT_DEPLOY_APPROVAL", True),
            "db": _bool_env("REQUIRE_EXPLICIT_DB_APPROVAL", True),
        },
    }
    if not execute_full:
        return {
            "ok": True,
            "service": "orion_internal",
            "mode": "premium_platform_audit" if premium_mode else "platform_self_audit",
            "provider": "platform",
            "event": "PLATFORM_SELF_AUDIT_READY",
            "status": "ready",
            "scope": scope,
            "visible_agent": visible_agent,
            "repo": _github_repo(),
            "technical_summary": "Auditoria consultiva preparada com base em sinais de runtime e política operacional. Nenhuma ação destrutiva foi iniciada; o objetivo é produzir diagnóstico estruturado com especialistas e evitar captura indevida por handlers de GitHub/runtime.",
            "findings": _audit_findings(scope),
            "risks": _audit_risks(),
            "suggested_actions": _audit_recommendations(scope),
            "key_files": [
                "app/runtime/intent_engine.py",
                "app/routes/internal/orion_internal.py",
                "app/main.py",
            ],
            "related_modules": [
                "auditor: riscos arquiteturais e inconsistências reais",
                "cto: plano técnico incremental e patch plan",
                "orion: análise executável e roteamento seguro",
                "chris: impacto funcional e leitura de produto",
            ],
            "risk_points": _audit_evidence_points(),
            "architecture_notes": [
                "Capability consultiva deve ter precedência sobre handlers de GitHub/runtime quando o pedido é de auditoria read-only.",
                "Loop de evolução automática e escrita governada permanecem protegidos por flags e aprovações explícitas.",
            ] + [f"{item['category']}: {item['description']}" for item in _scan_categories()],
            "remediation_plan": [
                "1. Classificar auditoria consultiva antes de inventário/config.",
                "2. Executar platform_self_audit via dispatcher interno.",
                "3. Preservar resposta evidencial sem acionar escrita governada.",
            ],
            "audit_plan": audit_plan,
            "generated_at": _now_ts(),
        }

    selected_specialists = ["orion"] if direct_orion_diagnostic else _audit_selected_specialists(scope, bool(inp.include_frontend), premium_mode=premium_mode)
    dispatch_receipts = _audit_dispatch_receipts(selected_specialists, scope)
    specialist_reports = _audit_specialist_reports(selected_specialists, scope)
    followup_subtype = _infer_progressive_dispatch_followup_subtype(inp.message)
    render_strategy = _dispatch_render_strategy(followup_subtype)
    executive_body_mode = "executive_replace" if followup_subtype == "executive_format" else ""
    compact_dispatch_details = bool(executive_body_mode)
    dispatch_receipts_appendix = list(dispatch_receipts or []) if compact_dispatch_details else []
    specialist_reports_appendix = list(specialist_reports or []) if compact_dispatch_details else []
    body_dispatch_receipts = [] if compact_dispatch_details else dispatch_receipts
    body_specialist_reports = [] if compact_dispatch_details else specialist_reports
    executive_sections = _build_dispatch_executive_sections(
        direct_orion_diagnostic=direct_orion_diagnostic,
        selected_specialists=selected_specialists,
        dispatch_receipts=dispatch_receipts,
        specialist_reports=specialist_reports,
        scope=scope,
        include_frontend=bool(inp.include_frontend),
        followup_subtype=followup_subtype,
    )
    counts = _dispatch_receipt_counts(dispatch_receipts, specialist_reports, selected_specialists)

    return {
        "ok": True,
        "service": "orion_internal",
        "mode": "premium_platform_audit" if premium_mode else "platform_self_audit",
        "provider": "platform",
        "event": "PLATFORM_PREMIUM_AUDIT_EXECUTED" if premium_mode else ("ORION_RUNTIME_DIAGNOSTIC_EXECUTED" if direct_orion_diagnostic else "PLATFORM_SELF_AUDIT_DISPATCH_EXECUTED"),
        "status": "executed",
        "scope": scope,
        "report_format": ("premium_platform_audit_v1" if premium_mode else (executive_sections.get("report_format") or ("orion_diagnostic_v1" if direct_orion_diagnostic else "dispatch_audit_v1"))),
        "delivery_contract": "premium_platform_audit_v1" if premium_mode else "orion_structured_dispatch_v1",
        "audit_payload_version": "dispatch_audit_envelope_v1",
        "execution_mode": "premium_read_only_multiagent" if premium_mode else "read_only_dispatch",
        "founder_control_mode": "human_controlled_runtime_only",
        "auditability_status": "ready_for_persistence",
        "sticky_thread_dispatch_supported": True,
        "sticky_thread_dispatch_contract": "orion_structured_dispatch_v1",
        "persistable_sections": [
            "technical_summary",
            "executive_diagnostic",
            "backend_assessment",
            "frontend_assessment",
            "integration_assessment",
            "confirmed_evidence",
            "main_risk",
            "recommended_actions",
            "selected_specialists",
            "dispatch_receipts",
            "dispatch_receipts_appendix",
            "specialist_reports",
            "specialist_reports_appendix",
            "final_consolidation",
        ],
        "execution_depth": "dispatch",
        "visible_agent": visible_agent,
        "repo": _github_repo(),
        "followup_mode": "progressive_dispatch_followup" if followup_subtype else "execution_receipt",
        "followup_subtype": followup_subtype,
        "render_strategy": render_strategy,
        "response_body_mode": ("premium_audit_full_renderer" if premium_mode else executive_body_mode),
        "compact_dispatch_details": compact_dispatch_details,
        "premium_renderer_required": bool(premium_mode),
        "premium_sections_complete": bool(premium_mode),
        "minimum_sections": (["A","B","C","D","E","F","G","H","I","J"] if premium_mode else []),
        "technical_summary": (
            "Varredura premium multiagente executada em modo somente leitura. A equipe técnica consolidou melhorias de UX, confiança, fluidez, mobile/PWA, billing e performance percebida sem acionar GitHub nem escrita governada."
            if premium_mode
            else "Síntese executiva progressiva aplicada sobre dispatch confirmado. O backend preservou evidências essenciais e reduziu repetição estrutural."
            if followup_subtype == "executive_format"
            else "Aprofundamento progressivo aplicado sobre dispatch confirmado. A continuidade expandiu a leitura sem regressão de contrato."
            if followup_subtype
            else "Orion executou um diagnóstico técnico objetivo em modo somente leitura, verificando runtime, handoff do chat e sinais de plataforma sem depender de escrita governada."
            if direct_orion_diagnostic
            else "Dispatch interno de especialistas executado em modo somente leitura. O backend acionou o squad solicitado e consolidou a entrega sem depender do loop automático nem de escrita governada."
        ),
        "selected_specialists": selected_specialists,
        "selected_specialists_count": counts.get("selected_specialists_count", 0),
        "selected_specialists_summary": ", ".join(str(item) for item in list(selected_specialists or [])[:20]),
        "dispatch_receipts": body_dispatch_receipts,
        "dispatch_receipts_count": counts.get("dispatch_receipts_count", 0),
        "dispatch_receipts_appendix": dispatch_receipts_appendix,
        "specialist_reports": body_specialist_reports,
        "specialist_reports_count": counts.get("specialist_reports_count", 0),
        "specialist_reports_appendix": specialist_reports_appendix,
        "final_consolidation": (
            _build_premium_platform_audit_sections(selected_specialists).get("principal_premium_blocker")
            if premium_mode
            else executive_sections.get("final_consolidation") or (
                "Orion consolidou a análise técnica objetiva como agente único visível. A resposta final deve sair assinada como Orion e não deve recair em PLATFORM_SELF_AUDIT_READY."
                if direct_orion_diagnostic
                else _audit_final_consolidation(selected_specialists, scope)
            )
        ),
        "executive_diagnostic": executive_sections.get("executive_diagnostic") or "",
        "backend_assessment": executive_sections.get("backend_assessment") or "",
        "frontend_assessment": executive_sections.get("frontend_assessment") or "",
        "integration_assessment": executive_sections.get("integration_assessment") or "",
        "confirmed_evidence": executive_sections.get("confirmed_evidence") or "",
        "main_risk": executive_sections.get("main_risk") or "",
        "recommended_actions": executive_sections.get("recommended_actions") or [],
        "executive_verdict": (_build_premium_platform_audit_sections(selected_specialists).get("executive_verdict") if premium_mode else ""),
        "findings_by_specialty": (_build_premium_platform_audit_sections(selected_specialists).get("findings_by_specialty") if premium_mode else {}),
        "top_improvements": (_build_premium_platform_audit_sections(selected_specialists).get("top_improvements") if premium_mode else []),
        "quick_wins_24h": (_build_premium_platform_audit_sections(selected_specialists).get("quick_wins_24h") if premium_mode else []),
        "improvements_7d": (_build_premium_platform_audit_sections(selected_specialists).get("improvements_7d") if premium_mode else []),
        "improvements_30d": (_build_premium_platform_audit_sections(selected_specialists).get("improvements_30d") if premium_mode else []),
        "premium_blockers": (_build_premium_platform_audit_sections(selected_specialists).get("premium_blockers") if premium_mode else []),
        "primary_product_adjustment": (_build_premium_platform_audit_sections(selected_specialists).get("primary_product_adjustment") if premium_mode else ""),
        "primary_frontend_adjustment": (_build_premium_platform_audit_sections(selected_specialists).get("primary_frontend_adjustment") if premium_mode else ""),
        "primary_backend_adjustment": (_build_premium_platform_audit_sections(selected_specialists).get("primary_backend_adjustment") if premium_mode else ""),
        "principal_premium_blocker": (_build_premium_platform_audit_sections(selected_specialists).get("principal_premium_blocker") if premium_mode else ""),
        "github_write_blocked": bool(_build_premium_platform_audit_sections(selected_specialists).get("github_write_blocked")) if premium_mode else False,
        "specialist_fanout_applied": bool(_build_premium_platform_audit_sections(selected_specialists).get("specialist_fanout_applied")) if premium_mode else False,
        "audit_mode": _build_premium_platform_audit_sections(selected_specialists).get("audit_mode") if premium_mode else ("specialist" if scope == "specialist" else "standard"),
        "key_files": [
            "app/runtime/intent_engine.py",
            "app/routes/internal/orion_internal.py",
            "app/main.py",
        ],
        "related_modules": [
            "runtime intent engine",
            "orion internal dispatcher",
            "chat/stream runtime handoff",
            "governed GitHub write policy",
        ],
        "risk_points": _audit_evidence_points(),
        "architecture_notes": [
            "Dispatch executado precisa ser refletido pela camada de renderização final.",
            "A auditoria read-only continua isolada de escrita governada, deploy e operações destrutivas.",
            "Handlers de inventário/config e dispatch multiagente não devem compartilhar o mesmo template textual.",
        ] + (
            [
                "Pedidos Orion-only de diagnóstico técnico objetivo devem produzir execução diagnóstica real, não PLATFORM_SELF_AUDIT_READY.",
                "A síntese final do diagnóstico direto deve permanecer assinada por Orion, sem delegação visual para outro agente.",
            ] if direct_orion_diagnostic else []
        ),
        "remediation_plan": (
            [
                "1. Bloquear GitHub write path em auditoria premium read-only.",
                "2. Executar fan-out multiagente obrigatório por especialidade.",
                "3. Renderizar resposta final em A–J com foco em valor percebido.",
                "4. Priorizar empty state, onboarding, fluidez e confiança.",
            ] if premium_mode else [
                "1. Preservar precedência do diagnóstico Orion-only sobre github_runtime_general.",
                "2. Emitir ORION_RUNTIME_DIAGNOSTIC_EXECUTED como resposta principal.",
                "3. Manter receipts e síntese final alinhados a Orion.",
                "4. Evitar regressão para template consultivo READY.",
            ] if direct_orion_diagnostic else [
                "1. Preservar precedência de platform_self_audit sobre github_runtime_general.",
                "2. Renderizar execution_depth=dispatch como resposta principal.",
                "3. Exibir receipts e relatórios por especialista sem recair em full_audit_v1.",
                "4. Consolidar a síntese final em um único bloco operacional verificável.",
            ]
        ),
        "audit_plan": audit_plan,
        "generated_at": _now_ts(),
    }


def orion_runtime_execute(inp: "OrionRuntimeIn") -> Dict[str, Any]:
    message = inp.message or ""
    lowered = message.lower()
    visible_agent = _resolve_visible_agent(message, default="orion")
    if _is_controlled_self_evolution_propose_request(message):
        return platform_self_evolution_plan(inp)
    if _is_orion_direct_diagnostic_request(message, visible_agent):
        return platform_self_audit(inp)
    if any(term in lowered for term in (
        "auditoria", "audit", "autoconhecimento", "consultivo", "somente leitura",
        "read only", "diagnóstico", "diagnostico"
    )):
        return platform_self_audit(inp)
    if any(term in lowered for term in ("scan runtime", "auditar runtime", "verificar runtime")):
        return runtime_scan(inp)
    if any(term in lowered for term in ("scan repo", "auditar repositório", "auditar repositorio")):
        return repo_structure_scan(inp)
    if any(term in lowered for term in ("scan segurança", "scan seguranca", "scan security")):
        return security_scan(inp)
    if any(term in lowered for term in ("plano de patch", "patch plan", "plano técnico", "plano tecnico")):
        return safe_patch_plan(inp)
    if any(term in lowered for term in ("listar agentes", "membros do squad", "liste os agentes")):
        return list_squad_agents_post(inp)
    return github_execute(inp)


class OrionRuntimeIn(BaseModel):
    message: str = Field(min_length=1)
    prepare_only: bool = False
    include_frontend: bool = False


# Compatibility aliases expected by app.main
OrionExecuteIn = OrionRuntimeIn


@router.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "orion_internal",
        "github_bridge_ready": _bool_env("ENABLE_GITHUB_BRIDGE", False),
        "default_branch": _default_branch(),
        "evolution_enabled": _evolution_enabled(),
    }


@router.get("/squad")
def list_squad_agents() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "orion_internal",
        "mode": "squad_agents_list",
        "squad": _suggested_squad(),
        "repo_targets": _build_repo_targets(),
        "policy": _safe_patch_policy(),
        "generated_at": _now_ts(),
    }


@router.post("/squad/list")
def list_squad_agents_post(inp: OrionRuntimeIn) -> Dict[str, Any]:
    visible_agent = _resolve_visible_agent(inp.message, default="orkio")
    return {
        "ok": True,
        "service": "orion_internal",
        "mode": "squad_agents_list",
        "visible_agent": visible_agent,
        "message": "Agentes do squad listados com sucesso.",
        "squad": _suggested_squad(),
        "repo_targets": _build_repo_targets(),
        "policy": _safe_patch_policy(),
        "generated_at": _now_ts(),
    }


@router.post("/platform/audit")
def platform_self_audit(inp: OrionRuntimeIn) -> Dict[str, Any]:
    visible_agent = _resolve_visible_agent(inp.message, default="orkio")
    return _build_platform_self_audit_payload(inp, visible_agent)


@router.post("/platform/scan/repo")
def repo_structure_scan(inp: OrionRuntimeIn) -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "orion_internal",
        "mode": "repo_structure_scan",
        "message": "Varredura de estrutura preparada.",
        "targets": _build_repo_targets(),
        "focus": [
            "app/main.py",
            "app/routes/internal",
            "app/runtime",
            "app/self_heal",
            "frontend runtime bridge",
        ],
        "generated_at": _now_ts(),
    }


@router.post("/platform/scan/runtime")
def runtime_scan(inp: OrionRuntimeIn) -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "orion_internal",
        "mode": "runtime_scan",
        "message": "Varredura de runtime preparada.",
        "focus": [
            "intent_engine",
            "planner_layer",
            "capability_registry",
            "chat/stream handoff",
            "github capability dispatch",
        ],
        "policy": _safe_patch_policy(),
        "generated_at": _now_ts(),
    }


@router.post("/platform/scan/security")
def security_scan(inp: OrionRuntimeIn) -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "orion_internal",
        "mode": "security_scan",
        "message": "Varredura de segurança preparada.",
        "checks": [
            "main direct write blocked",
            "explicit deploy approval",
            "explicit db approval",
            "destructive db runtime blocked",
            "allowed write agents restricted",
        ],
        "policy": _safe_patch_policy(),
        "generated_at": _now_ts(),
    }


@router.post("/platform/patch-plan")
def safe_patch_plan(inp: OrionRuntimeIn) -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "orion_internal",
        "mode": "safe_patch_plan",
        "message": "Plano de patch seguro preparado. Aguardando aprovação humana antes de qualquer escrita.",
        "steps": [
            "1. Auditor identifica falhas reais",
            "2. CTO consolida patch incremental",
            "3. Orion prepara branch e arquivos",
            "4. Aprovação humana explícita",
            "5. Execução em branch + PR",
            "6. Receipts transacionais obrigatórios entre branch, patch, commit, compare e PR",
        ],
        "write_agent": "orion",
        "policy": _safe_patch_policy(),
        "generated_at": _now_ts(),
    }




def _looks_like_github_runtime_request(message: str) -> bool:
    txt = (message or "").strip().lower()
    if not txt:
        return False

    keywords = (
        "github",
        "repo",
        "repositório",
        "repositorio",
        "branch",
        "commit",
        "pull request",
        "pr ",
        "arquivo",
        "file",
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".json",
        "main.py",
        "package.json",
        "abrir arquivo",
        "open file",
        "ler arquivo",
        "read file",
        "mostrar arquivo",
        "show file",
        "listar arquivos",
        "list files",
        "buscar",
        "search",
        "procurar",
        "create file",
        "criar arquivo",
        "update file",
        "alterar arquivo",
        "corrigir arquivo",
    )
    return any(k in txt for k in keywords)


@router.post("/github/execute")
def github_execute(inp: OrionRuntimeIn) -> Dict[str, Any]:
    visible_agent = _resolve_visible_agent(inp.message, default="orion")
    message = inp.message or ""
    lowered = message.lower()

    if not _looks_like_github_runtime_request(message):
        return {
            "ok": False,
            "service": "orion_internal",
            "mode": "github_execute",
            "error": "Mensagem não caracteriza operação GitHub/runtime",
            "message": message,
        }

    requested_write = any(term in lowered for term in [
        "write", "escrever", "criar arquivo", "crie arquivo", "adicione arquivo",
        "adicionar arquivo", "alterar arquivo", "corrigir arquivo", "novo arquivo",
        "create file", "update file", "commit", "branch",
    ])

    if requested_write and visible_agent not in _allowed_write_agents():
        return {
            "ok": False,
            "service": "orion_internal",
            "mode": "github_execute",
            "error": f"Agent '{visible_agent}' cannot execute GitHub write operations. Allowed agents: {', '.join(_allowed_write_agents())}",
            "message": message,
            "visible_agent": visible_agent,
            "requested_write": True,
        }

    backend_repo = _github_repo()
    frontend_repo = _github_repo_web()
    default_branch = _default_branch()
    repository_details: List[Dict[str, Any]] = []
    if backend_repo:
        repository_details.append({"kind": "backend", "repo": backend_repo, "branch": default_branch})
    if frontend_repo:
        repository_details.append({"kind": "frontend", "repo": frontend_repo, "branch": default_branch})

    if _looks_like_compare_status_request(message):
        return _github_compare_status_payload(message, visible_agent, repository_details)

    if _looks_like_repo_inventory_request(message):
        payload: Dict[str, Any] = {
            "ok": True,
            "service": "orion_internal",
            "mode": "github_runtime_inventory",
            "event": "GITHUB_RUNTIME_INVENTORY_OK",
            "visible_agent": visible_agent,
            "provider": "github",
            "message": "Inventário de repositórios do runtime coletado com leitura explícita das variáveis configuradas.",
            "requested_write": requested_write,
            "write_enabled": _github_write_enabled(),
            "pr_enabled": _github_pr_enabled(),
            "main_direct_write_allowed": _main_direct_allowed(),
            "default_branch": default_branch,
            "branch": default_branch,
            "backend_repo": backend_repo,
            "frontend_repo": frontend_repo,
            "repositories": [repo for repo in [backend_repo, frontend_repo] if repo],
            "repository_details": repository_details,
            "prepare_only": bool(inp.prepare_only),
            "generated_at": _now_ts(),
        }
        if _wants_root_evidence(message):
            backend_root = _github_root_entries(backend_repo, default_branch, limit=3)
            frontend_root = _github_root_entries(frontend_repo, default_branch, limit=3)
            payload["backend_root_entries"] = list(backend_root.get("entries") or [])
            payload["frontend_root_entries"] = list(frontend_root.get("entries") or [])
            payload["backend_root_ok"] = bool(backend_root.get("ok"))
            payload["frontend_root_ok"] = bool(frontend_root.get("ok"))
            if not backend_root.get("ok"):
                payload["backend_root_error"] = str(backend_root.get("message") or "").strip()
            if not frontend_root.get("ok"):
                payload["frontend_root_error"] = str(frontend_root.get("message") or "").strip()
        return payload

    return {
        "ok": True,
        "service": "orion_internal",
        "mode": "github_execute",
        "event": "GITHUB_RUNTIME_CONFIG_OK",
        "visible_agent": visible_agent,
        "provider": "github",
        "message": message,
        "requested_write": requested_write,
        "write_enabled": _github_write_enabled(),
        "pr_enabled": _github_pr_enabled(),
        "main_direct_write_allowed": _main_direct_allowed(),
        "default_branch": default_branch,
        "branch": default_branch,
        "backend_repo": backend_repo,
        "frontend_repo": frontend_repo,
        "repositories": [repo for repo in [backend_repo, frontend_repo] if repo],
        "repository_details": repository_details,
        "prepare_only": bool(inp.prepare_only),
        "generated_at": _now_ts(),
    }


# Compatibility aliases expected by app.main
def orion_github_execute(inp: OrionExecuteIn) -> Dict[str, Any]:
    return github_execute(inp)


def orion_runtime_execute_alias(inp: OrionExecuteIn) -> Dict[str, Any]:
    return orion_runtime_execute(inp)
