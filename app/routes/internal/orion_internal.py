from __future__ import annotations

import json
import os
import re
import time
import urllib.request as _urllib_request
import ssl as _ssl
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/internal/orion", tags=["orion_internal"])


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
    return (
        _bool_env("ENABLE_GITHUB_BRIDGE", False)
        and _bool_env("GITHUB_AUTOMATION_ALLOWED", False)
        and _bool_env("AUTO_CODE_EMISSION_ENABLED", False)
    )


def _github_pr_enabled() -> bool:
    return _bool_env("GITHUB_PR_RUNTIME_ENABLED", False) and _bool_env("AUTO_PR_WRITE_ENABLED", False)


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
        "require_explicit_db_approval": _bool_env("REQUIRE_EXPLICIT_DB_APPROVAL", True),
        "db_runtime_allow_destructive": _bool_env("DB_RUNTIME_ALLOW_DESTRUCTIVE", False),
        "controlled_overlay_enabled": _bool_env("CONTROLLED_EVOLUTION_OVERLAY_ENABLED", True),
        "evolution_loop_enabled": _evolution_enabled(),
        "write_allowed_agents": _allowed_write_agents(),
        "read_allowed_agents": _allowed_read_agents(),
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
    return _platform_audit_payload(inp, visible_agent)


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

    if _looks_like_platform_audit_request(message):
        payload = _platform_audit_payload(inp, visible_agent)
        payload["routed_via"] = "github_execute_bypass"
        return payload

    if not _looks_like_github_runtime_request(message):
        return {
            "ok": False,
            "service": "orion_internal",
            "mode": "github_execute",
            "error": "Mensagem não caracteriza operação GitHub/runtime",
            "message": message,
        }

    if _looks_like_consultive_only_request(message) and _looks_like_platform_audit_request(message):
        payload = _platform_audit_payload(inp, visible_agent)
        payload["routed_via"] = "github_execute_consultive_guard"
        return payload

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


# Compatibility alias expected by app.main
def orion_github_execute(inp: OrionExecuteIn) -> Dict[str, Any]:
    return github_execute(inp)

def _looks_like_platform_audit_request(message: str) -> bool:
    txt = (message or "").strip().lower()
    if not txt:
        return False
    audit_markers = [
        "auditoria",
        "auditar",
        "análise interna",
        "analise interna",
        "diagnóstico",
        "diagnostico",
        "autoconhecimento",
        "modo consultivo",
        "somente leitura",
        "read-only",
    ]
    scope_markers = [
        "sistema",
        "plataforma",
        "arquitetura",
        "thread",
        "runtime",
        "agentes",
    ]
    return any(marker in txt for marker in audit_markers) and any(marker in txt for marker in scope_markers)


def _looks_like_consultive_only_request(message: str) -> bool:
    txt = (message or "").strip().lower()
    if not txt:
        return False
    markers = [
        "somente leitura",
        "apenas leitura",
        "modo consultivo",
        "estritamente consultivo",
        "read-only",
        "nenhuma execução operacional",
        "nenhuma execucao operacional",
        "nenhuma alteração estrutural",
        "nenhuma alteracao estrutural",
        "nenhuma publicação de mudança",
        "nenhuma publicacao de mudanca",
    ]
    return any(marker in txt for marker in markers)


def _platform_audit_scope(message: str) -> str:
    txt = (message or "").strip().lower()
    if any(term in txt for term in ("por especialidade", "por especialista", "por área", "por area")):
        return "specialist"
    return "standard"


def _audit_runtime_evidence() -> List[Dict[str, Any]]:
    return [
        {"fact": "ENABLE_EVOLUTION_LOOP", "value": _evolution_enabled(), "kind": "env_flag"},
        {"fact": "GITHUB_WRITE_RUNTIME_ENABLED", "value": _bool_env("GITHUB_WRITE_RUNTIME_ENABLED", False), "kind": "env_flag"},
        {"fact": "GITHUB_PR_RUNTIME_ENABLED", "value": _bool_env("GITHUB_PR_RUNTIME_ENABLED", False), "kind": "env_flag"},
        {"fact": "AUTO_PR_WRITE_ENABLED", "value": _bool_env("AUTO_PR_WRITE_ENABLED", False), "kind": "env_flag"},
        {"fact": "ALLOW_GITHUB_MAIN_DIRECT", "value": _main_direct_allowed(), "kind": "env_flag"},
        {"fact": "REQUIRE_EXPLICIT_DEPLOY_APPROVAL", "value": _bool_env("REQUIRE_EXPLICIT_DEPLOY_APPROVAL", True), "kind": "env_flag"},
        {"fact": "REQUIRE_EXPLICIT_DB_APPROVAL", "value": _bool_env("REQUIRE_EXPLICIT_DB_APPROVAL", True), "kind": "env_flag"},
        {"fact": "backend_repo_configured", "value": bool(_github_repo()), "kind": "runtime_config"},
        {"fact": "frontend_repo_configured", "value": bool(_github_repo_web()), "kind": "runtime_config"},
    ]


def _platform_audit_payload(inp: OrionRuntimeIn, visible_agent: str) -> Dict[str, Any]:
    consultive_only = _looks_like_consultive_only_request(inp.message)
    scope = _platform_audit_scope(inp.message)
    repo_targets = _build_repo_targets()
    evidence = _audit_runtime_evidence()

    findings: List[Dict[str, str]] = [
        {
            "severity": "ALTO",
            "title": "Classificação de intenção consultiva pode colidir com handlers operacionais",
            "detail": "Pedidos com termos de GitHub, repo ou branch podem ser capturados por handlers de inventário/configuração se a precedência do roteador não privilegiar auditoria consultiva.",
        },
        {
            "severity": "ALTO",
            "title": "Capability consultiva precisa vencer o roteamento antes de GitHub runtime",
            "detail": "A resposta correta para auditoria read-only deve ser produzida pela trilha consultiva, sem registrar autorização de escrita e sem retornar inventário GitHub como se fosse o resultado final da tarefa.",
        },
        {
            "severity": "MÉDIO",
            "title": "Resposta consultiva sem evidência degrada a utilidade da auditoria",
            "detail": "Mesmo quando a auditoria é acionada, ela precisa separar fatos observados, inferências e recomendações para evitar respostas genéricas e pouco acionáveis.",
        },
    ]

    if not _evolution_enabled():
        findings.append(
            {
                "severity": "MÉDIO",
                "title": "Loop de evolução automática desabilitado por ambiente",
                "detail": "A auditoria consultiva continua possível, mas qualquer execução automática do squad depende de ENABLE_EVOLUTION_LOOP=true e de aprovações explícitas.",
            }
        )

    risks = [
        "Falso positivo de escrita governada quando o prompt cita operações em contexto negativo.",
        "Falso positivo de runtime/config quando o pedido é analítico mas menciona repositório ou GitHub.",
        "Duplicidade de resposta entre Orkio e Orion quando ambos ecoam o mesmo resultado operacional.",
    ]

    suggested_actions = [
        "Priorizar platform_self_audit antes de github_runtime_general em pedidos de auditoria consultiva.",
        "Separar explicitamente intenção consultiva, inventário runtime e escrita governada.",
        "Responder auditorias com fatos observados, inferências e recomendações em blocos distintos.",
    ]

    if consultive_only:
        suggested_actions.insert(0, "Preservar modo read-only: nenhuma escrita, branch, commit ou PR deve ser acionado nesta tarefa.")

    technical_summary = (
        "Auditoria consultiva preparada com base em sinais de runtime e política operacional. "
        "Nenhuma ação destrutiva foi iniciada; o objetivo é produzir diagnóstico estruturado com especialistas e "
        "evitar captura indevida por handlers de GitHub/runtime."
    )

    return {
        "ok": True,
        "service": "orion_internal",
        "provider": "platform",
        "mode": "platform_self_audit",
        "event": "PLATFORM_SELF_AUDIT_READY",
        "status": "consultive_ready",
        "visible_agent": visible_agent,
        "scope": scope,
        "consultive_only": consultive_only,
        "message": "Auditoria consultiva preparada com sucesso. Nenhuma escrita foi iniciada.",
        "technical_summary": technical_summary,
        "findings": findings,
        "risks": risks,
        "suggested_actions": suggested_actions,
        "architecture_notes": [
            "Capability consultiva deve ter precedência sobre handlers de GitHub/runtime quando o pedido é de auditoria read-only.",
            "Loop de evolução automática e escrita governada permanecem protegidos por flags e aprovações explícitas.",
        ],
        "key_files": [
            "app/runtime/intent_engine.py",
            "app/routes/internal/orion_internal.py",
            "app/main.py",
        ],
        "remediation_plan": [
            "1. Classificar auditoria consultiva antes de inventário/config.",
            "2. Executar platform_self_audit via dispatcher interno.",
            "3. Preservar resposta evidencial sem acionar escrita governada.",
        ],
        "audit_plan": {
            "requested_by": visible_agent,
            "prepare_only": True,
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
            "evidence": evidence,
            "approval_gate": {
                "required_for_execution": True,
                "deploy": _bool_env("REQUIRE_EXPLICIT_DEPLOY_APPROVAL", True),
                "db": _bool_env("REQUIRE_EXPLICIT_DB_APPROVAL", True),
            },
            "next_action": "Produzir diagnóstico técnico com evidências antes de qualquer patch.",
        },
        "policy": _safe_patch_policy(),
        "generated_at": _now_ts(),
    }

