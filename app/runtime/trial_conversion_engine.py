from __future__ import annotations
from typing import Any, Dict, Optional

def build_trial_hints(user_state: Optional[Dict[str, Any]], continuity_hints: Optional[Dict[str, Any]], profile_hints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    user_state = user_state or {}
    continuity_hints = continuity_hints or {}
    profile_hints = profile_hints or {}
    day = int(user_state.get("trial_day") or 0)
    if day <= 0:
        action = "deliver_first_win"
        activation = "low"
        readiness = "low"
        message_hint = "mostrar utilidade prática imediata"
    elif day <= 1:
        action = "resume_context"
        activation = "medium"
        readiness = "low"
        message_hint = "retomar algo concreto da sessão anterior"
    elif day <= 3:
        action = "light_checkin"
        activation = "medium"
        readiness = "medium"
        message_hint = "acompanhar progresso e remover bloqueio"
    elif day <= 5:
        action = "deepen_value"
        activation = "high"
        readiness = "medium"
        message_hint = "abrir camada de aprofundamento opcional"
    else:
        action = "continuity_invite"
        activation = "high"
        readiness = "high" if continuity_hints.get("has_active_project") else "medium"
        message_hint = "convidar para continuidade com base no valor percebido"

    if continuity_hints.get("numerology_invite_window") and day >= 3:
        action = "numerology_invite"
        message_hint = "abrir camada de aprofundamento opcional"

    return {
        "trial_day": day,
        "activation_level": activation,
        "conversion_readiness": readiness,
        "recommended_next_action": action,
        "message_hint": message_hint,
    }
