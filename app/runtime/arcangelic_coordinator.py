from __future__ import annotations
from typing import Any, Dict, List

def build_arcangelic_chain(
    intent_package: Dict[str, Any],
    first_win_plan: Dict[str, Any],
    continuity_hints: Dict[str, Any],
    profile_hints: Dict[str, Any] | None,
    capability_registry: Dict[str, Any],
) -> Dict[str, Any]:
    visible_responder = "orkio"
    advisors = [str(x).strip().lower() for x in (intent_package.get("advisor_agents") or []) if x]
    if not advisors:
        advisors = [
            str(x).strip().lower()
            for x in (intent_package.get("recommended_agents") or [])
            if x and str(x).strip().lower() != visible_responder
        ]

    visible_cap = capability_registry.get(visible_responder, {}) or {}
    execution: List[Dict[str, Any]] = [{
        "agent": visible_responder,
        "task": (visible_cap.get("capabilities") or ["guide"])[0],
        "mode": "orchestrator",
        "visible": True,
    }]

    internal_advisors: List[Dict[str, Any]] = []
    for name in advisors:
        cap = capability_registry.get(name, {}) or {}
        mode = "internal_advisor"
        if name == "rafael":
            mode = "supportive_internal"
        elif name == "gabriel":
            mode = "translator_internal"
        elif name == "orion":
            mode = "technical_internal"
        internal_advisors.append({
            "agent": name,
            "task": (cap.get("capabilities") or ["guide"])[0],
            "mode": mode,
            "visible": False,
        })

    sensitivity = (intent_package.get("sensitivity_level") or "low").lower()
    pre_guard = "miguel" if sensitivity in ("medium", "high") else None
    scribe = "metatron"
    numerology_window = bool(continuity_hints.get("numerology_invite_window"))
    return {
        "chain_type": intent_package.get("intent") or "general_guidance",
        "pre_guard": pre_guard,
        "orchestrator": visible_responder,
        "visible_responder": visible_responder,
        "single_visible_speaker": True,
        "execution_sequence": execution,
        "internal_advisors": internal_advisors,
        "post_guard": None,
        "scribe": scribe,
        "final_response_style": "clear_and_structured",
        "followup_mode": continuity_hints.get("followup_mode") or intent_package.get("followup_mode") or "light_checkin",
        "numerology_invite_window": numerology_window,
    }

def build_system_overlay(intent_package: Dict[str, Any], first_win_plan: Dict[str, Any], continuity_hints: Dict[str, Any], chain: Dict[str, Any]) -> str:
    questions = first_win_plan.get("questions") or []
    qtxt = "\n".join([f"- {q}" for q in questions[:2]])
    resume_hint = continuity_hints.get("resume_hint") or ""
    advisor_names = ", ".join([str(x.get("agent") or "") for x in (chain.get("internal_advisors") or []) if x.get("agent")]) or "none"
    return (
        "Runtime guidance for this response:\n"
        f"- dominant_intent: {intent_package.get('intent')}\n"
        f"- response_strategy: {intent_package.get('response_strategy')}\n"
        f"- first_win_goal: {intent_package.get('first_win_goal')}\n"
        f"- followup_mode: {chain.get('followup_mode')}\n"
        f"- resume_hint: {resume_hint}\n"
        f"- final_response_style: {chain.get('final_response_style')}\n"
        f"- visible_responder: {chain.get('visible_responder') or chain.get('orchestrator')}\n"
        f"- internal_advisors: {advisor_names}\n"
        "Instructions:\n"
        "1. Only the visible responder may speak directly to the user.\n"
        "2. Use internal advisors silently to improve the answer, but do not output advisor names or parallel replies.\n"
        "3. If the user requests an internal adjustment or correction, acknowledge the action plainly and state what will be adjusted internally.\n"
        "4. Prefer one concrete next step over abstract explanation.\n"
        "5. If helpful, ask at most two targeted questions that unlock a first win.\n"
        "6. Keep continuity natural, not forced.\n"
        "7. Do not mention internal engines, guards, routing modes, or chain names.\n"
        "8. Do not claim lack of access to your own code or inability to adjust internal behavior; instead, describe the intended internal adjustment at a high level without exposing proprietary details.\n"
        f"Suggested first-win questions:\n{qtxt}"
    )

def build_runtime_hints(
    intent_package: Dict[str, Any],
    continuity_hints: Dict[str, Any],
    trial_hints: Dict[str, Any],
    chain: Dict[str, Any],
    planner_snapshot: Dict[str, Any] | None = None,
    memory_snapshot: Dict[str, Any] | None = None,
    trial_analytics: Dict[str, Any] | None = None,
    dag_snapshot: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    out = {
        "intent": intent_package.get("intent"),
        "followup_mode": chain.get("followup_mode") or continuity_hints.get("followup_mode"),
        "trial_action": trial_hints.get("recommended_next_action"),
        "trial_day": trial_hints.get("trial_day"),
        "resume_hint": continuity_hints.get("resume_hint"),
        "followup_target": continuity_hints.get("followup_target"),
        "numerology_invite_window": bool(chain.get("numerology_invite_window")),
        "visible_responder": chain.get("visible_responder") or chain.get("orchestrator"),
        "single_visible_speaker": bool(chain.get("single_visible_speaker")),
    }
    if planner_snapshot:
        out["planner"] = {
            "version": planner_snapshot.get("planner_version"),
            "execution_order": planner_snapshot.get("execution_order"),
            "primary_objective": planner_snapshot.get("primary_objective"),
            "confidence": planner_snapshot.get("planner_confidence"),
            "execution_strategy": planner_snapshot.get("execution_strategy"),
            "fallback_strategy": planner_snapshot.get("fallback_strategy"),
        }
    if memory_snapshot:
        out["memory"] = {
            "count": memory_snapshot.get("count"),
            "avg_confidence": memory_snapshot.get("avg_confidence"),
            "high_confidence_count": memory_snapshot.get("high_confidence_count"),
            "freshest_updated_at": memory_snapshot.get("freshest_updated_at"),
            "strong_resume_ready": memory_snapshot.get("strong_resume_ready"),
            "resume_candidate": bool(memory_snapshot.get("strong_resume_ready")),
        }
    if trial_analytics:
        out["trial"] = {
            "stage": trial_analytics.get("stage"),
            "activation_score": trial_analytics.get("activation_score"),
            "behavior_score": trial_analytics.get("behavior_score"),
            "activation_probability": trial_analytics.get("activation_probability"),
            "conversion_probability": trial_analytics.get("conversion_probability"),
            "recommended_action": trial_analytics.get("recommended_action"),
        }
    if dag_snapshot:
        out["routing"] = {
            "mode": dag_snapshot.get("routing_mode"),
            "route_applied": dag_snapshot.get("route_applied"),
            "ready_nodes": dag_snapshot.get("ready_nodes"),
            "routing_source": dag_snapshot.get("routing_source"),
            "routing_confidence": dag_snapshot.get("routing_confidence"),
            "override_reason": dag_snapshot.get("routing_override_reason"),
            "execution_cursor": dag_snapshot.get("execution_cursor"),
            "execution_lifecycle": dag_snapshot.get("execution_lifecycle"),
        }
    return out
