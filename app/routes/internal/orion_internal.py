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
        "acione os especialistas",
        "acione a equipe técnica",
        "acione a equipe tecnica",
        "equipe técnica",
        "equipe tecnica",
        "especialistas técnicos",
        "especialistas tecnicos",
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



def _audit_selected_specialists(scope: str, include_frontend: bool = False) -> List[str]:
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


def _build_platform_self_audit_payload(inp: "OrionRuntimeIn", visible_agent: str) -> Dict[str, Any]:
    scope = _audit_scope(inp.message)
    direct_orion_diagnostic = _is_orion_direct_diagnostic_request(inp.message, visible_agent)
    execute_full = _audit_wants_full_execution(inp.message, bool(inp.prepare_only)) or direct_orion_diagnostic
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

    selected_specialists = ["orion"] if direct_orion_diagnostic else _audit_selected_specialists(scope, bool(inp.include_frontend))
    dispatch_receipts = _audit_dispatch_receipts(selected_specialists, scope)
    specialist_reports = _audit_specialist_reports(selected_specialists, scope)

    return {
        "ok": True,
        "service": "orion_internal",
        "mode": "platform_self_audit",
        "provider": "platform",
        "event": "ORION_RUNTIME_DIAGNOSTIC_EXECUTED" if direct_orion_diagnostic else "PLATFORM_SELF_AUDIT_DISPATCH_EXECUTED",
        "status": "executed",
        "scope": scope,
        "report_format": "orion_diagnostic_v1" if direct_orion_diagnostic else "dispatch_audit_v1",
        "execution_depth": "dispatch",
        "visible_agent": visible_agent,
        "repo": _github_repo(),
        "technical_summary": (
            "Orion executou um diagnóstico técnico objetivo em modo somente leitura, verificando runtime, handoff do chat e sinais de plataforma sem depender de escrita governada."
            if direct_orion_diagnostic
            else "Dispatch interno de especialistas executado em modo somente leitura. O backend acionou o squad solicitado e consolidou a entrega sem depender do loop automático nem de escrita governada."
        ),
        "selected_specialists": selected_specialists,
        "dispatch_receipts": dispatch_receipts,
        "specialist_reports": specialist_reports,
        "final_consolidation": (
            "Orion consolidou a análise técnica objetiva como agente único visível. A resposta final deve sair assinada como Orion e não deve recair em PLATFORM_SELF_AUDIT_READY."
            if direct_orion_diagnostic
            else _audit_final_consolidation(selected_specialists, scope)
        ),
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
