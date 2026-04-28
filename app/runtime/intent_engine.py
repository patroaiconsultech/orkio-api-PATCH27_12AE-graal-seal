from __future__ import annotations

from typing import Any, Dict, Optional


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _contains_any(text: str, terms: list[str]) -> bool:
    txt = _normalize(text)
    return any(_normalize(term) in txt for term in terms if term)




def _contains_all(text: str, terms: list[str]) -> bool:
    txt = _normalize(text)
    return all(_normalize(term) in txt for term in terms if term)

def _context_has_sticky_dispatch(context: Optional[Dict[str, Any]]) -> bool:
    ctx = context or {}
    if not isinstance(ctx, dict):
        return False
    if not bool(ctx.get("sticky_dispatch_active")):
        return False
    delivery_contract = str(ctx.get("sticky_delivery_contract") or "").strip().lower()
    dispatch_event = str(ctx.get("sticky_dispatch_event") or "").strip().upper()
    return bool(
        delivery_contract == "orion_structured_dispatch_v1"
        or dispatch_event in {"ORION_RUNTIME_DIAGNOSTIC_EXECUTED", "PLATFORM_SELF_AUDIT_DISPATCH_EXECUTED"}
    )


def _looks_like_sticky_dispatch_followup(text: str) -> bool:
    txt = _normalize(text)
    if not txt or len(txt) > 600:
        return False
    patterns = [
        "continue",
        "prossiga",
        "aprofunde",
        "desdobre",
        "expanda",
        "refine",
        "causas raiz",
        "riscos estruturais",
        "próximos passos",
        "proximos passos",
        "evidências técnicas",
        "evidencias tecnicas",
        "formato executivo",
        "diagnóstico executivo",
        "diagnostico executivo",
        "sem perder evidências",
        "sem perder evidencias",
        "executive_diagnostic",
        "technical_summary",
        "final_consolidation",
        "dispatch_receipts",
        "specialist_reports",
    ]
    return any(term in txt for term in patterns)




def _infer_sticky_dispatch_followup_subtype(text: str) -> str:
    txt = _normalize(text)
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
# =========================
# GitHub Runtime Detection
# =========================

PATCH_SENTINEL_EXPECTED = "FRONTEND_REPO_EMISSION_SENTINEL_12BI_V1"
PATCH_FEATURE_EXPECTED = "frontend_repo_target_hard_binding_and_proposal_file_emission"
PATCH_EXPECTED_BEHAVIOR = "frontend_repo_hard_binding_and_proposal_patch_file_emission"

_GITHUB_RUNTIME_TERMS = [
    "github",
    "repo",
    "frontend",
    "backend",
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
    "empty state premium",
    "appconsole",
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

_GITHUB_AUTH_TERMS = [
    "autorizo",
    "confirmo",
    "aprovo",
    "não autorizo merge",
    "nao autorizo merge",
]

_GITHUB_AUTH_ACTION_TERMS = [
    "branch",
    "patch",
    "arquivo",
    "file",
    "commit",
    "pr",
    "pull request",
    "main",
]

_GITHUB_REVOKE_TERMS = [
    "revogo",
    "revogar",
    "cancelar autorização",
    "cancelar autorizacao",
    "revogo toda autorização",
    "revogo toda autorizacao",
]

_PREMIUM_AUDIT_TERMS = [
    "experiência premium",
    "experiencia premium",
    "premium",
    "irresistível",
    "irresistivel",
    "alto valor percebido",
    "elegante",
    "fluida",
    "confiável",
    "confiavel",
    "primeira impressão",
    "primeira impressao",
    "onboarding",
    "performance percebida",
    "consistência visual",
    "consistencia visual",
]

_PREMIUM_AUDIT_SCOPE_TERMS = [
    "somente leitura",
    "read only",
    "sem github",
    "sem branch",
    "sem patch",
    "sem commit",
    "sem pr",
    "sem pull request",
    "sem merge",
    "sem deploy",
    "sem alterar banco",
    "sem resposta genérica",
    "sem resposta generica",
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
    "acione a equipe técnica",
    "acione a equipe tecnica",
    "acione os especialistas",
    "especialistas técnicos",
    "especialistas tecnicos",
    "varredura no código",
    "varredura no codigo",
    "dê continuidade ao trabalho",
    "de continuidade ao trabalho",
    "execute as ações necessárias",
    "execute as acoes necessarias",
]

_SPECIALIST_AUDIT_TERMS = [
    "por especialidade",
    "por especialista",
    "por área",
    "por area",
    "relatório por especialidade",
    "relatorio por especialidade",
    "acione os especialistas",
    "acione a equipe técnica",
    "acione a equipe tecnica",
    "equipe técnica",
    "equipe tecnica",
    "especialistas técnicos",
    "especialistas tecnicos",
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
]

_ORION_DIRECT_DIAGNOSTIC_TERMS = [
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

_SELF_EVOLUTION_TERMS = [
    "autoevolução controlada",
    "autoevolução controlada",
    "auto evolucao controlada",
    "autoevolucao controlada",
    "self evolution",
    "self-evolution",
    "ciclo de autoevolução",
    "ciclo de autoevolucao",
    "evolução controlada",
    "evolucao controlada",
]

_SELF_EVOLUTION_SCOPE_TERMS = [
    "propose_only",
    "modo propose_only",
    "somente proposta",
    "apenas proposta",
    "sem pr",
    "sem pull request",
    "sem merge",
    "sem deploy",
    "não abrir pr",
    "nao abrir pr",
    "não fazer merge",
    "nao fazer merge",
    "não fazer deploy",
    "nao fazer deploy",
    "não escrever em main",
    "nao escrever em main",
]

_SELF_EVOLUTION_SOURCE_TERMS = [
    "última auditoria premium",
    "ultima auditoria premium",
    "last premium audit",
    "auditoria premium",
    "backlog priorizado",
    "selecionar a melhoria",
    "melhoria de maior impacto",
    "menor risco",
]

def _is_controlled_self_evolution_propose_request(text: str) -> bool:
    txt = _normalize(text)
    if not txt:
        return False
    return (
        _contains_any(txt, _SELF_EVOLUTION_TERMS)
        and (
            _contains_any(txt, _SELF_EVOLUTION_SCOPE_TERMS)
            or _contains_any(txt, _SELF_EVOLUTION_SOURCE_TERMS)
        )
    )



def _detect_runtime_operation(text: str) -> Dict[str, Any]:
    txt = _normalize(text)
    direct_orion_diagnostic = _contains_any(txt, _ORION_DIRECT_DIAGNOSTIC_TERMS)
    premium_audit = (
        _contains_any(txt, _AUDIT_TERMS)
        and _contains_any(txt, _PREMIUM_AUDIT_TERMS)
    ) or (
        _contains_any(txt, ["varredura profunda", "multiagente", "multiagente e somente leitura", "toda a equipe técnica interna", "toda a equipe tecnica interna"])
        and _contains_any(txt, _PREMIUM_AUDIT_TERMS + ["usuários", "usuarios", "plataforma inteira"])
    )

    if _contains_any(txt, _SQUAD_TERMS):
        return {
            "kind": "squad_list",
            "target_agent": "orion",
            "mode": "execute",
            "requires_capability": "agents_registry_read",
            "data_source": "agents_api",
        }

    if _is_controlled_self_evolution_propose_request(txt):
        return {
            "kind": "controlled_self_evolution_propose_only",
            "target_agent": "orion",
            "mode": "execute",
            "evolution_mode": "propose_only",
            "prepare_only": False,
            "execution_depth": "dispatch",
            "visible_only_agent": "orion",
            "response_profile": "controlled_self_evolution_propose_only",
            "delivery_contract": "controlled_self_evolution_propose_only_v1",
            "render_strategy": "controlled_self_evolution_A_to_J_full",
            "response_body_mode": "controlled_self_evolution_propose_only",
            "structured_output": True,
            "dispatch_receipts_expected": True,
            "specialist_reports_expected": True,
            "final_consolidation_expected": True,
            "auditability_expected": True,
            "execution_audit_expected": True,
            "persist_execution_audit": True,
            "specialist_fanout_required": True,
            "hard_block_github_write": True,
            "read_only_enforced": True,
            "github_write_blocked": True,
            "approval_required_for_pr": True,
            "requested_specialists": ["auditor", "cto", "orion", "chris", "architect", "devops", "security", "memory_ops", "stage_manager"],
            "planner_sections_required": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
            "source_preference": "latest_premium_audit",
            "patch_sentinel_expected": PATCH_SENTINEL_EXPECTED,
            "patch_feature_expected": PATCH_FEATURE_EXPECTED,
            "patch_expected_behavior": PATCH_EXPECTED_BEHAVIOR,
        }

    if premium_audit:
        specialist_mode = True
        wants_execution = True
        return {
            "kind": "premium_platform_audit",
            "target_agent": "orion",
            "mode": "execute",
            "audit_mode": "specialist",
            "prepare_only": False,
            "execution_depth": "dispatch",
            "visible_only_agent": "",
            "response_profile": "premium_platform_audit",
            "delivery_contract": "premium_platform_audit_v1",
            "render_strategy": "premium_audit_A_to_J_full",
            "response_body_mode": "premium_audit_full_renderer",
            "structured_output": True,
            "dispatch_receipts_expected": True,
            "specialist_reports_expected": True,
            "final_consolidation_expected": True,
            "auditability_expected": True,
            "execution_audit_expected": True,
            "persist_execution_audit": True,
            "specialist_fanout_required": True,
            "hard_block_github_write": True,
            "read_only_enforced": True,
            "github_write_blocked": True,
            "include_frontend": True,
            "requested_specialists": ["auditor", "cto", "orion", "chris", "architect", "devops", "security", "memory_ops", "stage_manager"],
            "premium_sections_required": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
            "patch_sentinel_expected": PATCH_SENTINEL_EXPECTED,
            "patch_feature_expected": PATCH_FEATURE_EXPECTED,
            "patch_expected_behavior": PATCH_EXPECTED_BEHAVIOR,
        }

    if direct_orion_diagnostic or _contains_any(txt, _AUDIT_TERMS):
        specialist_mode = _contains_any(txt, _SPECIALIST_AUDIT_TERMS)
        wants_execution = _contains_any(txt, _AUDIT_EXECUTION_TERMS) or direct_orion_diagnostic
        visible_only_agent = "orion" if (
            direct_orion_diagnostic
            or "@orion" in txt
            or "como orion" in txt
        ) else ""
        return {
            "kind": "platform_audit",
            "target_agent": "orion",
            "mode": "execute",
            "audit_mode": "specialist" if specialist_mode else "standard",
            "prepare_only": not wants_execution,
            "execution_depth": "dispatch" if wants_execution else "ready",
            "visible_only_agent": visible_only_agent,
            "response_profile": "orion_objective_diagnostic" if direct_orion_diagnostic else "platform_audit",
            "delivery_contract": "orion_structured_dispatch_v1" if wants_execution else "orion_audit_ready_v1",
            "structured_output": bool(wants_execution),
            "dispatch_receipts_expected": bool(wants_execution),
            "specialist_reports_expected": bool(wants_execution),
            "final_consolidation_expected": bool(wants_execution),
            "auditability_expected": bool(wants_execution),
            "execution_audit_expected": bool(wants_execution),
            "persist_execution_audit": bool(wants_execution),
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

    github_revoke_hit = _contains_any(txt, _GITHUB_REVOKE_TERMS) and _contains_any(txt, _GITHUB_AUTH_ACTION_TERMS)
    github_auth_hit = (_contains_any(txt, _GITHUB_AUTH_TERMS) or github_revoke_hit) and _contains_any(txt, _GITHUB_AUTH_ACTION_TERMS)
    if github_auth_hit:
        return {
            "kind": "github_runtime_write",
            "target_agent": "orion",
            "mode": "execute",
            "requires_capability": "github_repo_write",
            "response_profile": "github_governed_write",
            "delivery_contract": "github_governed_write_v1",
            "approval_required_expected": True,
            "human_confirmation_required": True,
            "transactional_flow_required": True,
            "transactional_flow": "branch_commit_pr",
            "receipt_required_steps": ["branch_created", "files_written", "commit_created", "compare_ok", "pull_request_opened"],
            "human_approval_source": "chat",
            "patch_sentinel_expected": PATCH_SENTINEL_EXPECTED,
            "patch_feature_expected": PATCH_FEATURE_EXPECTED,
            "patch_expected_behavior": PATCH_EXPECTED_BEHAVIOR,
        }

    github_hit = _contains_any(txt, _GITHUB_RUNTIME_TERMS)
    if github_hit:
        if _contains_any(txt, _GITHUB_WRITE_TERMS):
            return {
                "kind": "github_runtime_write",
                "target_agent": "orion",
                "mode": "execute",
                "requires_capability": "github_repo_write",
                "response_profile": "github_governed_write",
                "delivery_contract": "github_governed_write_v1",
                "approval_required_expected": True,
                "human_confirmation_required": True,
                "transactional_flow_required": True,
                "transactional_flow": "branch_commit_pr",
                "receipt_required_steps": ["branch_created", "files_written", "commit_created", "compare_ok", "pull_request_opened"],
                "human_approval_source": "chat",
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
    if (not runtime_op.get("kind")) and _context_has_sticky_dispatch(context) and _looks_like_sticky_dispatch_followup(text):
        followup_subtype = _infer_sticky_dispatch_followup_subtype(text)
        runtime_op = {
            "kind": "platform_audit",
            "target_agent": "orion",
            "mode": "execute",
            "audit_mode": "specialist",
            "prepare_only": False,
            "execution_depth": "dispatch",
            "visible_only_agent": "orion",
            "response_profile": "orion_objective_diagnostic_followup",
            "delivery_contract": "orion_structured_dispatch_v1",
            "structured_output": True,
            "dispatch_receipts_expected": True,
            "specialist_reports_expected": True,
            "final_consolidation_expected": True,
            "auditability_expected": True,
            "execution_audit_expected": True,
            "persist_execution_audit": True,
            "contract_inherited_from_thread": True,
            "sticky_dispatch_followup": True,
            "sticky_dispatch_event": str((context or {}).get("sticky_dispatch_event") or "").strip(),
            "requested_specialists": list((context or {}).get("sticky_selected_specialists") or []),
            "followup_mode": "progressive_dispatch_followup",
            "followup_subtype": followup_subtype or "continuation",
            "response_body_mode": "executive_replace" if (followup_subtype or "").strip().lower() == "executive_format" else "",
            "compact_dispatch_details": bool((followup_subtype or "").strip().lower() == "executive_format"),
            "render_strategy_hint": "dispatch_executive_replace" if (followup_subtype or "").strip().lower() == "executive_format" else "",
        }
    elif runtime_op.get("kind") == "platform_audit" and _context_has_sticky_dispatch(context):
        runtime_op["contract_inherited_from_thread"] = bool(runtime_op.get("contract_inherited_from_thread") or _looks_like_sticky_dispatch_followup(text))
        if runtime_op.get("contract_inherited_from_thread"):
            runtime_op["sticky_dispatch_followup"] = True
            runtime_op["sticky_dispatch_event"] = str((context or {}).get("sticky_dispatch_event") or "").strip()
            runtime_op["delivery_contract"] = runtime_op.get("delivery_contract") or "orion_structured_dispatch_v1"
            runtime_op["persist_execution_audit"] = True
            runtime_op["followup_mode"] = runtime_op.get("followup_mode") or "progressive_dispatch_followup"
            runtime_op["followup_subtype"] = runtime_op.get("followup_subtype") or _infer_sticky_dispatch_followup_subtype(text) or "continuation"
            if str(runtime_op.get("followup_subtype") or "").strip().lower() == "executive_format":
                runtime_op["render_strategy_hint"] = "dispatch_executive_replace"
                runtime_op["response_body_mode"] = "executive_replace"
                runtime_op["compact_dispatch_details"] = True
    intent = runtime_op.get("kind") or "general_guidance"

    recommended_agents = ["orkio"]
    advisor_agents = ["orkio", "metatron"]

    if runtime_op.get("target_agent"):
        recommended_agents = [runtime_op["target_agent"]]

    if intent == "platform_audit":
        if runtime_op.get("visible_only_agent") == "orion":
            advisor_agents = ["orion", "metatron"]
        else:
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
        if runtime_op.get("sticky_dispatch_followup"):
            subtype = str(runtime_op.get("followup_subtype") or "").strip().lower()
            first_win_goal = {
                "executive_format": "deliver_progressive_executive_dispatch_followup",
                "root_causes_risks": "deepen_root_causes_and_risks_from_dispatch",
                "root_causes": "deepen_root_causes_from_dispatch",
                "risks": "deepen_structural_risks_from_dispatch",
                "next_steps": "turn_dispatch_into_next_steps",
                "evidence_preserving": "preserve_evidence_while_reframing_dispatch",
            }.get(subtype, "continue_structured_dispatch_without_regression")
        else:
            first_win_goal = (
                "execute_orion_objective_diagnostic"
                if runtime_op.get("visible_only_agent") == "orion"
                else "produce_specialist_audit_plan"
            )
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
        "delivery_contract": runtime_op.get("delivery_contract") or "",
        "structured_output": bool(runtime_op.get("structured_output")),
        "auditability_expected": bool(runtime_op.get("auditability_expected")),
        "execution_audit_expected": bool(runtime_op.get("execution_audit_expected")),
        "context_summary": context.get("summary"),
        "first_win_goal": first_win_goal,
        "followup_mode": (
            runtime_op.get("followup_mode")
            or ("execution_receipt" if runtime_op.get("kind") else "light_checkin")
        ),
        "followup_subtype": runtime_op.get("followup_subtype") or "",
        "contract_inherited_from_thread": bool(runtime_op.get("contract_inherited_from_thread")),
        "sticky_dispatch_followup": bool(runtime_op.get("sticky_dispatch_followup")),
    }
