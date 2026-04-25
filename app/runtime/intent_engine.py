from __future__ import annotations

from typing import Any, Dict, Optional


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _contains_any(text: str, terms: list[str]) -> bool:
    txt = _normalize(text)
    return any(_normalize(term) in txt for term in terms if term)


# =========================
# GitHub Runtime Detection
# =========================

_GITHUB_RUNTIME_TERMS = [
    "github",
    "repo",
    "repositório",
    "repositorio",
    "branch",
    "commit",
    "arquivo",
    "file",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
]

_GITHUB_WRITE_TERMS = [
    "write",
    "escrever",
    "criar arquivo",
    "crie arquivo",
    "adicione arquivo",
    "adicionar arquivo",
    "alterar arquivo",
    "corrigir arquivo",
    "novo arquivo",
    "create file",
    "update file",
    "editar arquivo",
    "modificar arquivo",
    "patch",
    "pull request",
    "pr ",
]

_GITHUB_READ_TERMS = [
    "ler",
    "leia",
    "mostrar",
    "abrir arquivo",
    "read file",
    "open file",
    "tree",
    "listar arquivos",
    "search",
    "buscar",
    "procure",
    "status",
    "show file",
    "list files",
]

# =========================
# Squad + Audit Detection
# =========================

_SQUAD_TERMS = [
    "agentes do squad",
    "listar agentes",
    "liste os agentes",
    "squad disponível",
    "squad disponivel",
    "agentes disponíveis",
    "agentes disponiveis",
    "liste o squad",
    "liste os membros",
    "listar membros",
    "membros do squad",
    "membros da equipe",
    "equipe disponível",
    "equipe disponivel",
    "time disponível",
    "time disponivel",
    "quais são os agentes",
    "quais sao os agentes",
    "liste os membros do seu squad",
    "liste os membros do squad",
    "listar equipe",
    "listar o squad",
]

_AUDIT_TERMS = [
    "audite a plataforma",
    "auditoria da plataforma",
    "scan da plataforma",
    "analise a plataforma",
    "análise da plataforma",
    "auditar plataforma",
    "audit platform",
    "platform audit",
    "auditoria interna",
    "auditoria interna profunda",
    "autoconhecimento técnico",
    "autoconhecimento tecnico",
    "diagnóstico técnico",
    "diagnostico tecnico",
    "modo consultivo",
    "somente leitura",
    "strictly read only",
    "read only audit",
    "consultive audit",
    "auditoria consultiva",
    "sugira melhorias por especialidade",
    "melhorias por especialidade",
    "sem executar nada",
]

_SPECIALIST_AUDIT_TERMS = [
    "por especialidade",
    "por especialista",
    "por área",
    "por area",
    "relatório por especialidade",
    "relatorio por especialidade",
]
_AUDIT_EXECUTION_TERMS = [
    "prosseguir agora",
    "prosseguir com a auditoria",
    "auditoria completa",
    "auditoria profunda",
    "execução integral",
    "execucao integral",
    "quero a execução integral",
    "quero a execucao integral",
    "fatos observados",
    "evidências técnicas",
    "evidencias tecnicas",
    "causas raiz estruturais",
    "conclusão final sincera",
    "conclusao final sincera",
]

# =========================
# Runtime Scan Detection
# =========================

_RUNTIME_SCAN_TERMS = [
    "scan runtime",
    "scan backend",
    "verificar runtime",
    "auditar runtime",
]

_REPO_SCAN_TERMS = [
    "scan repo",
    "scan repositório",
    "scan repositorio",
    "auditar repositório",
    "auditar repositorio",
]

_SECURITY_SCAN_TERMS = [
    "scan segurança",
    "scan seguranca",
    "scan security",
    "auditar segurança",
    "auditar seguranca",
]

_PATCH_PLAN_TERMS = [
    "plano de patch",
    "patch plan",
    "plano técnico",
    "plano tecnico",
    "plano seguro",
]


def _detect_runtime_operation(text: str) -> Dict[str, Any]:
    txt = _normalize(text)

    if _contains_any(txt, _SQUAD_TERMS):
        return {
            "kind": "squad_list",
            "target_agent": "orion",
            "mode": "execute",
            "requires_capability": "agents_registry_read",
            "data_source": "agents_api",
        }

    if _contains_any(txt, _AUDIT_TERMS):
        specialist_mode = _contains_any(txt, _SPECIALIST_AUDIT_TERMS)
        wants_execution = _contains_any(txt, _AUDIT_EXECUTION_TERMS)
        return {
            "kind": "platform_audit",
            "target_agent": "orion",
            "mode": "execute",
            "audit_mode": "specialist" if specialist_mode else "standard",
            "prepare_only": not wants_execution,
            "execution_depth": "full" if wants_execution else "ready",
        }

    if _contains_any(txt, _RUNTIME_SCAN_TERMS):
        return {
            "kind": "runtime_scan",
            "target_agent": "orion",
            "mode": "execute",
        }

    if _contains_any(txt, _REPO_SCAN_TERMS):
        return {
            "kind": "repo_scan",
            "target_agent": "orion",
            "mode": "execute",
        }

    if _contains_any(txt, _SECURITY_SCAN_TERMS):
        return {
            "kind": "security_scan",
            "target_agent": "orion",
            "mode": "execute",
        }

    if _contains_any(txt, _PATCH_PLAN_TERMS):
        return {
            "kind": "patch_plan",
            "target_agent": "orion",
            "mode": "execute",
            "prepare_only": True,
        }

    github_hit = _contains_any(txt, _GITHUB_RUNTIME_TERMS)
    if github_hit:
        if _contains_any(txt, _GITHUB_WRITE_TERMS):
            return {
                "kind": "github_runtime_write",
                "target_agent": "orion",
                "mode": "execute",
                "requires_capability": "github_repo_write",
            }

        if _contains_any(txt, _GITHUB_READ_TERMS):
            return {
                "kind": "github_runtime_read",
                "target_agent": "orion",
                "mode": "execute",
                "requires_capability": "github_repo_read",
            }

        return {
            "kind": "github_runtime_general",
            "target_agent": "orion",
            "mode": "execute",
            "requires_capability": "github_repo_read",
        }

    return {
        "kind": "",
        "target_agent": "",
        "mode": "",
    }


def build_intent_package(
    user_input: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    text = _normalize(user_input)
    context = context or {}

    runtime_op = _detect_runtime_operation(text)
    intent = runtime_op.get("kind") or "general_guidance"

    recommended_agents = ["orkio"]
    advisor_agents = ["orkio", "metatron"]

    if runtime_op.get("target_agent"):
        recommended_agents = [runtime_op["target_agent"]]

    if intent == "platform_audit":
        advisor_agents = [
            "auditor",
            "cto",
            "orion",
            "chris",
            "saint_germain",
            "metatron",
        ]
    elif intent == "patch_plan":
        advisor_agents = ["cto", "orion", "auditor", "metatron"]
    elif intent == "runtime_scan":
        advisor_agents = ["orion", "auditor", "metatron"]
    elif intent == "security_scan":
        advisor_agents = ["auditor", "miguel", "orion", "metatron"]
    elif intent == "repo_scan":
        advisor_agents = ["orion", "chris", "metatron"]
    elif intent == "squad_list":
        advisor_agents = ["orion", "metatron"]
    elif intent in {
        "github_runtime_read",
        "github_runtime_write",
        "github_runtime_general",
    }:
        advisor_agents = ["orion", "metatron"]

    first_win_goal = "deliver_clear_next_step"

    if intent == "platform_audit":
        first_win_goal = "produce_specialist_audit_plan"
    elif intent == "patch_plan":
        first_win_goal = "prepare_safe_patch_plan"
    elif intent == "runtime_scan":
        first_win_goal = "prepare_runtime_scan"
    elif intent == "repo_scan":
        first_win_goal = "prepare_repo_scan"
    elif intent == "security_scan":
        first_win_goal = "prepare_security_scan"
    elif intent == "squad_list":
        first_win_goal = "list_squad_agents_from_registry"
    elif intent == "github_runtime_read":
        first_win_goal = "return_repo_evidence"
    elif intent == "github_runtime_write":
        first_win_goal = "execute_github_write_with_evidence"

    return {
        "intent": intent,
        "confidence": 0.98 if runtime_op.get("kind") else 0.62,
        "recommended_agents": recommended_agents,
        "advisor_agents": advisor_agents,
        "runtime_operation": runtime_op,
        "requires_runtime_execution": bool(runtime_op.get("kind")),
        "target_agent": runtime_op.get("target_agent") or "orkio",
        "requires_capability": runtime_op.get("requires_capability") or "",
        "context_summary": context.get("summary"),
        "first_win_goal": first_win_goal,
        "followup_mode": (
            "execution_receipt" if runtime_op.get("kind") else "light_checkin"
        ),
    }
