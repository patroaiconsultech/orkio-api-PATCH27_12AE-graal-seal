from __future__ import annotations

from typing import Any, Dict, List, Optional


CAPABILITY_EXECUTION_BINDINGS = {
    # GitHub runtime
    "github_repo_read": {
        "executor": "orion_internal.github_execute",
        "mode": "runtime",
        "allowed_agents": ["orkio", "orion", "chris", "auditor"],
        "write": False,
    },
    "github_repo_write": {
        "executor": "orion_internal.github_execute",
        "mode": "runtime",
        "allowed_agents": ["orion"],
        "write": True,
    },
    "github_branch_create": {
        "executor": "orion_internal.github_execute",
        "mode": "runtime",
        "allowed_agents": ["orion"],
        "write": True,
    },
    "github_file_create": {
        "executor": "orion_internal.github_execute",
        "mode": "runtime",
        "allowed_agents": ["orion"],
        "write": True,
    },
    "github_repo_fix": {
        "executor": "orion_internal.github_execute",
        "mode": "runtime",
        "allowed_agents": ["orion"],
        "write": True,
    },
    "github_pr_compare_status": {
        "executor": "orion_internal.github_execute",
        "mode": "runtime",
        "allowed_agents": ["orkio", "orion", "chris", "auditor"],
        "write": False,
    },
    "github_pr_prepare": {
        "executor": "orion_internal.github_execute",
        "mode": "runtime",
        "allowed_agents": ["orion"],
        "write": True,
    },

    # Squad visibility / audit runtime
    "squad_agents_list": {
        "executor": "orion_internal.list_squad_agents",
        "mode": "runtime",
        "allowed_agents": ["orkio", "orion"],
        "write": False,
    },
    "platform_self_audit": {
        "executor": "orion_internal.platform_self_audit",
        "mode": "runtime",
        "allowed_agents": ["orkio", "orion", "auditor"],
        "write": False,
    },
    "repo_structure_scan": {
        "executor": "orion_internal.platform_self_audit",
        "mode": "runtime",
        "allowed_agents": ["orkio", "orion", "auditor"],
        "write": False,
    },
    "routes_scan": {
        "executor": "orion_internal.platform_self_audit",
        "mode": "runtime",
        "allowed_agents": ["orkio", "orion", "auditor"],
        "write": False,
    },
    "runtime_scan": {
        "executor": "orion_internal.platform_self_audit",
        "mode": "runtime",
        "allowed_agents": ["orkio", "orion", "auditor"],
        "write": False,
    },
    "security_scan": {
        "executor": "orion_internal.platform_self_audit",
        "mode": "runtime",
        "allowed_agents": ["orkio", "orion", "auditor"],
        "write": False,
    },
    "safe_patch_plan": {
        "executor": "orion_internal.platform_self_audit",
        "mode": "runtime",
        "allowed_agents": ["orkio", "orion", "auditor", "cto"],
        "write": False,
    },
    "controlled_self_evolution_propose_only": {
        "executor": "orion_internal.platform_self_evolution_plan",
        "mode": "runtime",
        "allowed_agents": ["orkio", "orion", "auditor", "cto", "chris"],
        "write": False,
    },
    "premium_audit_backlog_generate": {
        "executor": "orion_internal.platform_self_evolution_plan",
        "mode": "runtime",
        "allowed_agents": ["orkio", "orion", "auditor", "cto", "chris"],
        "write": False,
    },
    "premium_audit_patch_candidate_select": {
        "executor": "orion_internal.platform_self_evolution_plan",
        "mode": "runtime",
        "allowed_agents": ["orkio", "orion", "auditor", "cto", "chris"],
        "write": False,
    },
    "controlled_self_evolution_execute_proposal": {
        "executor": "orion_internal.github_execute",
        "mode": "runtime",
        "allowed_agents": ["orion"],
        "write": True,
    },
}


CAPABILITY_REGISTRY = {
    "orkio": {
        "role": "orchestrator",
        "capabilities": [
            "coordinate",
            "synthesize",
            "guide_next_step",
            "github_repo_read",
            "github_pr_compare_status",
            "squad_agents_list",
            "platform_self_audit",
            "repo_structure_scan",
            "routes_scan",
            "runtime_scan",
            "security_scan",
            "safe_patch_plan",
            "controlled_self_evolution_propose_only",
            "premium_audit_backlog_generate",
            "premium_audit_patch_candidate_select",
            "controlled_self_evolution_execute_proposal",
        ],
        "triggers": [
            "default",
            "general",
            "unclear",
            "squad",
            "agentes",
            "auditar",
            "scan",
            "varredura",
            "melhorias",
            "plataforma",
        ],
        "dependencies": [],
        "priority": 100,
        "writes_memory": False,
    },

    "orion": {
        "role": "cto",
        "capabilities": [
            "technical_analysis",
            "github_repo_read",
            "github_pr_compare_status",
            "github_repo_fix",
            "github_branch_create",
            "github_file_create",
            "github_repo_write",
            "github_pr_prepare",
            "governed_patch_execution",
            "safe_evolution_control",
            "db_schema_read",
            "db_schema_fix_governed",
            "squad_agents_list",
            "platform_self_audit",
            "repo_structure_scan",
            "routes_scan",
            "runtime_scan",
            "security_scan",
            "safe_patch_plan",
            "controlled_self_evolution_propose_only",
            "premium_audit_backlog_generate",
            "premium_audit_patch_candidate_select",
        ],
        "triggers": [
            "github",
            "repo",
            "code",
            "patch",
            "fix",
            "technical",
            "database",
            "banco",
            "schema",
            "drift",
            "migration",
            "migracao",
            "tabela",
            "coluna",
            "audit",
            "auditar",
            "scan",
            "platform",
            "plataforma",
            "squad",
            "frontend",
            "empty state premium",
        ],
        "dependencies": ["orkio"],
        "priority": 98,
        "writes_memory": False,
    },

    "auditor": {
        "role": "technical_auditor",
        "capabilities": [
            "platform_self_audit",
            "repo_structure_scan",
            "routes_scan",
            "runtime_scan",
            "security_scan",
            "safe_patch_plan",
            "controlled_self_evolution_propose_only",
            "premium_audit_backlog_generate",
            "premium_audit_patch_candidate_select",
            "github_repo_read",
            "github_pr_compare_status",
            "technical_analysis",
            "risk_guard",
        ],
        "triggers": [
            "auditor",
            "audit",
            "auditar",
            "varredura",
            "risco",
            "segurança",
            "security",
            "arquitetura",
            "diagnóstico",
            "classificação operacional",
            "classificacao operacional",
            "read only",
            "somente leitura",
            "intent_engine.py",
            "capability_registry.py",
        ],
        "dependencies": ["orkio", "orion"],
        "priority": 97,
        "writes_memory": False,
    },

    "cto": {
        "role": "systems_architect",
        "capabilities": [
            "technical_analysis",
            "safe_patch_plan",
            "repo_structure_scan",
            "routes_scan",
            "runtime_scan",
            "controlled_self_evolution_propose_only",
            "premium_audit_backlog_generate",
            "premium_audit_patch_candidate_select",
        ],
        "triggers": [
            "cto",
            "arquitetura",
            "architecture",
            "patch plan",
            "plano técnico",
            "refino técnico",
        ],
        "dependencies": ["orkio", "orion"],
        "priority": 96,
        "writes_memory": False,
    },

    "miguel": {
        "role": "guardian",
        "capabilities": ["risk_guard", "safety_boundary", "sensitive_review"],
        "triggers": ["sensitive", "compliance", "high_risk"],
        "dependencies": ["orkio"],
        "priority": 95,
        "writes_memory": False,
    },

    "uriel": {
        "role": "diagnostician",
        "capabilities": ["root_cause", "priority_diagnosis", "clarify_decision"],
        "triggers": ["overload", "priority", "decision", "blocker"],
        "dependencies": ["orkio"],
        "priority": 90,
        "writes_memory": False,
    },

    "rafael": {
        "role": "organizer",
        "capabilities": ["reframe", "small_steps", "practical_plan"],
        "triggers": ["execution", "plan", "next_step"],
        "dependencies": ["uriel"],
        "priority": 85,
        "writes_memory": False,
    },

    "gabriel": {
        "role": "translator",
        "capabilities": ["simplify", "translate_for_user", "clarify_message"],
        "triggers": ["communication", "explain", "summarize"],
        "dependencies": ["orkio"],
        "priority": 80,
        "writes_memory": False,
    },

    "chris": {
        "role": "commercial_strategist",
        "capabilities": [
            "controlled_self_evolution_propose_only",
            "premium_audit_backlog_generate",
            "premium_audit_patch_candidate_select",
            "github_repo_read",
            "github_pr_compare_status",
            "platform_self_audit",
            "repo_structure_scan",
            "routes_scan",
            "runtime_scan",
            "clarify_message",
            "summarize",
        ],
        "triggers": [
            "chris",
            "comercial",
            "negócio",
            "read repo",
            "ler repo",
            "resumir",
            "explicar",
        ],
        "dependencies": ["orkio"],
        "priority": 79,
        "writes_memory": False,
    },

    "metatron": {
        "role": "scribe",
        "capabilities": ["candidate_memory", "session_register", "continuity_signal"],
        "triggers": ["memory", "followup", "continuity"],
        "dependencies": ["orkio"],
        "priority": 75,
        "writes_memory": True,
    },

    "saint_germain": {
        "role": "refiner",
        "capabilities": ["incremental_refinement", "maturity", "process_improvement"],
        "triggers": ["refine", "improve", "transform"],
        "dependencies": ["orkio"],
        "priority": 70,
        "writes_memory": False,
    },
}


def get_capability_registry() -> Dict[str, Any]:
    return CAPABILITY_REGISTRY.copy()


def get_capability_executor(capability: str) -> Optional[Dict[str, Any]]:
    return CAPABILITY_EXECUTION_BINDINGS.get(capability)


def get_capability_allowed_agents(capability: str) -> List[str]:
    binding = CAPABILITY_EXECUTION_BINDINGS.get(capability) or {}
    agents = binding.get("allowed_agents") or []
    return [str(a).strip().lower() for a in agents if str(a).strip()]


def capability_is_write(capability: str) -> bool:
    binding = CAPABILITY_EXECUTION_BINDINGS.get(capability) or {}
    return bool(binding.get("write", False))


def agent_can_execute_capability(agent_name: str, capability: str) -> bool:
    normalized_agent = (agent_name or "").strip().lower()
    if not normalized_agent or not capability:
        return False

    meta = CAPABILITY_REGISTRY.get(normalized_agent) or {}
    declared_caps = {str(c).strip() for c in (meta.get("capabilities") or []) if str(c).strip()}
    if capability not in declared_caps:
        return False

    binding = CAPABILITY_EXECUTION_BINDINGS.get(capability)
    if not binding:
        return True

    allowed = get_capability_allowed_agents(capability)
    if not allowed:
        return True

    return normalized_agent in allowed
