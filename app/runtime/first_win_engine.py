from __future__ import annotations
from typing import Any, Dict

_DEFAULT = {
    "first_win_type": "clarity_boost",
    "questions": [
        "qual é a prioridade mais importante agora?",
        "qual seria um próximo passo útil ainda hoje?",
    ],
    "agent_sequence": ["orkio", "gabriel", "metatron"],
    "expected_result": "clear_next_step",
    "followup_mode": "light_checkin",
    "memory_candidates": ["active_priority_candidate"],
}

_BY_INTENT = {
    "priority_structuring": {
        "first_win_type": "priority_extraction",
        "questions": ["qual é o principal projeto teu hoje?", "o que está travando isso?"],
        "agent_sequence": ["uriel", "rafael", "metatron"],
        "expected_result": "structured_priority_output",
        "followup_mode": "daily_checkin",
        "memory_candidates": ["active_project_candidate", "execution_block_candidate"],
    },
    "execution_planning": {
        "first_win_type": "micro_plan",
        "questions": ["qual entrega precisa acontecer primeiro?", "qual é o menor passo executável nas próximas 24h?"],
        "agent_sequence": ["rafael", "uriel", "metatron"],
        "expected_result": "micro_execution_plan",
        "followup_mode": "light_checkin",
        "memory_candidates": ["execution_target_candidate", "next_step_candidate"],
    },
    "growth_strategy": {
        "first_win_type": "growth_lever_identification",
        "questions": ["qual alavanca de crescimento mais importa agora?", "qual prova ou ativo falta para avançar?"],
        "agent_sequence": ["uriel", "gabriel", "metatron"],
        "expected_result": "growth_focus_output",
        "followup_mode": "milestone_checkin",
        "memory_candidates": ["growth_goal_candidate", "missing_asset_candidate"],
    },
    "team_coordination": {
        "first_win_type": "team_alignment",
        "questions": ["quem precisa fazer o quê primeiro?", "qual decisão precisa sair agora?"],
        "agent_sequence": ["orkio", "gabriel", "metatron"],
        "expected_result": "team_alignment_output",
        "followup_mode": "checkpoint",
        "memory_candidates": ["team_alignment_candidate", "pending_decision_candidate"],
    },
    "symbolic_profile": {
        "first_win_type": "consented_symbolic_opening",
        "questions": ["você quer uma leitura simbólica opcional ou prefere seguir só pelo plano prático agora?"],
        "agent_sequence": ["orkio", "metatron"],
        "expected_result": "symbolic_consent_state",
        "followup_mode": "deepen_optional",
        "memory_candidates": ["symbolic_interest_candidate"],
    },
}

def build_first_win_plan(intent_package: Dict[str, Any]) -> Dict[str, Any]:
    intent = (intent_package or {}).get("intent") or "general_guidance"
    out = dict(_DEFAULT)
    out.update(_BY_INTENT.get(intent, {}))
    out["intent"] = intent
    return out
