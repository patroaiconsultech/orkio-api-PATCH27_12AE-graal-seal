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


def _audit_scope(message: str) -> str:
    txt = (message or "").strip().lower()
    specialist_markers = (
        "por especialidade",
        "por especialista",
        "por área",
        "por area",
        "especialistas internos",
        "specialist",
    )
    return "specialist" if any(marker in txt for marker in specialist_markers) else "standard"


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
    )
    return any(marker in txt for marker in execution_markers)


def _audit_facts_observed(scope: str) -> List[str]:
    facts = [
        "Capability consultiva registrada no runtime interno.",
        "Handlers de escrita governada e runtime GitHub continuam habilitados e protegidos por flags e aprovações explícitas.",
        "ALLOW_GITHUB_MAIN_DIRECT permanece desabilitado, preservando o bloqueio de escrita direta em main.",
        "ENABLE_EVOLUTION_LOOP pode permanecer falso sem impedir auditoria read-only.",
    ]
    if scope == "specialist":
        facts.append("Escopo specialist solicitado: auditor, cto, orion e chris devem convergir no mesmo relatório consultivo.")
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


def _build_platform_self_audit_payload(inp: "OrionRuntimeIn", visible_agent: str) -> Dict[str, Any]:
    scope = _audit_scope(inp.message)
    execute_full = _audit_wants_full_execution(inp.message, bool(inp.prepare_only))
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
            "mode": "platform_self_audit",
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

    return {
        "ok": True,
        "service": "orion_internal",
        "mode": "platform_self_audit",
        "provider": "platform",
        "event": "PLATFORM_SELF_AUDIT_EXECUTED",
        "status": "executed",
        "scope": scope,
        "visible_agent": visible_agent,
        "repo": _github_repo(),
        "technical_summary": "Auditoria consultiva executada em modo somente leitura. O roteamento consultivo venceu os handlers operacionais e o diagnóstico foi consolidado em blocos distintos de fatos, inferências e recomendações.",
        "facts_observed": _audit_facts_observed(scope),
        "evidence_points": _audit_evidence_points(),
        "inferences": [
            "O gargalo principal deixou de ser boot/capability ausente e passou a ser profundidade de execução da auditoria consultiva.",
            "Sempre que a resposta cair em readiness report repetido, o problema está no executor/saída e não mais no classificador primário.",
            "A presença simultânea de handlers GitHub e capability consultiva exige precedência estável para evitar regressões.",
        ],
        "findings": _audit_findings(scope),
        "risks": _audit_risks(),
        "suggested_actions": _audit_recommendations(scope),
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
            "Fatos observados devem permanecer separados de inferências e recomendações na saída final.",
            "A auditoria consultiva não depende do loop automático de evolução para produzir relatório de leitura.",
            "Handlers de inventário/config e escrita governada devem continuar isolados da trilha consultiva.",
        ],
        "fragile_areas": [
            "precedência entre consultivo e runtime/config",
            "profundidade de execução da auditoria",
            "duplicidade de resposta entre agentes",
        ],
        "corrected_areas": [
            "roteamento inicial da auditoria consultiva",
            "evitação de captura indevida por GITHUB_RUNTIME_CONFIG_OK",
            "preservação de modo read-only sem registrar autorização de escrita",
        ],
        "remediation_plan": [
            "1. Preservar precedência de platform_self_audit sobre github_runtime_general.",
            "2. Forçar saída executada com fatos, inferências e recomendações.",
            "3. Tratar readiness apenas como etapa intermediária opcional, nunca como resposta final padrão.",
            "4. Consolidar especialistas internos no mesmo relatório consultivo.",
        ],
        "audit_plan": audit_plan,
        "generated_at": _now_ts(),
    }


def orion_runtime_execute(inp: "OrionRuntimeIn") -> Dict[str, Any]:
    message = inp.message or ""
    lowered = message.lower()
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
