from __future__ import annotations
from typing import Any, Dict, List, Optional

def _extract_target(memory_context: List[Dict[str, Any]], latest_messages: List[Dict[str, Any]]) -> str:
    for item in memory_context or []:
        value = str(item.get("memory_value") or "").strip()
        if value:
            return value
    for item in reversed(latest_messages or []):
        content = str(item.get("content") or "").strip()
        if content:
            return content[:120]
    return ""

def build_continuity_hints(
    thread_id: str,
    user_id: str,
    memory_context: Optional[List[Dict[str, Any]]] = None,
    latest_intent: Optional[Dict[str, Any]] = None,
    latest_messages: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    memory_context = memory_context or []
    latest_messages = latest_messages or []
    latest_intent = latest_intent or {}
    followup_target = _extract_target(memory_context, latest_messages)
    has_active_project = any("project" in str(m.get("memory_key","")) or "priority" in str(m.get("memory_key","")) for m in memory_context) or len(latest_messages) >= 4
    has_pending_decision = any("decision" in str(m.get("memory_key","")) for m in memory_context)
    trust_level = "high" if len(memory_context) >= 3 or len(latest_messages) >= 8 else "medium" if latest_messages else "low"
    followup_mode = latest_intent.get("followup_mode") or ("daily_checkin" if has_active_project else "light_checkin")
    resume_hint = ""
    if followup_target:
        resume_hint = f"retomar contexto de: {followup_target[:72]}"
    elif latest_intent.get("intent"):
        resume_hint = f"retomar intenção recente: {latest_intent['intent']}"
    numerology_window = bool(trust_level in ("medium", "high") and latest_intent.get("invite_numerology_later"))
    return {
        "has_active_project": bool(has_active_project),
        "has_pending_decision": bool(has_pending_decision),
        "followup_target": followup_target[:120],
        "followup_mode": followup_mode,
        "trust_level": trust_level,
        "resume_hint": resume_hint,
        "numerology_invite_window": numerology_window,
        "memory_count": len(memory_context),
    }
