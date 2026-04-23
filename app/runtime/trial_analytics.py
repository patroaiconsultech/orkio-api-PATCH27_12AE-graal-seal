from __future__ import annotations
from typing import Any, Dict

def build_trial_analytics(
    trial_day: int,
    runtime_hints: Dict[str, Any],
    continuity_hints: Dict[str, Any],
    memory_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    action = str((runtime_hints or {}).get("trial_action") or "")
    activation_score = 20
    behavior_score = 0
    if continuity_hints.get("has_active_project"):
        activation_score += 20
        behavior_score += 20
    if continuity_hints.get("has_pending_decision"):
        activation_score += 10
        behavior_score += 10
    avg_conf = float(memory_snapshot.get("avg_confidence") or 0)
    activation_score += int(avg_conf * 30)
    if memory_snapshot.get("strong_resume_ready"):
        behavior_score += 20
    if int(memory_snapshot.get("high_confidence_count") or 0) >= 2:
        behavior_score += 10
    if action in {"resume_context", "light_checkin", "deepen_value", "continuity_invite"}:
        activation_score += 10
        behavior_score += 10
    if action == "numerology_invite":
        activation_score += 5
    activation_score = max(0, min(100, activation_score))
    behavior_score = max(0, min(100, behavior_score))

    stage = "new"
    if trial_day >= 1 or activation_score >= 35:
        stage = "activated"
    if trial_day >= 3 or behavior_score >= 40:
        stage = "engaged"
    if trial_day >= 6 or (activation_score >= 65 and behavior_score >= 50):
        stage = "conversion_window"

    activation_probability = round(min(0.98, max(0.05, activation_score / 100.0)), 2)
    conversion_probability = round(min(0.96, max(0.03, ((activation_score * 0.6) + (behavior_score * 0.4)) / 100.0)), 2)

    return {
        "trial_day": int(trial_day or 0),
        "stage": stage,
        "activation_score": activation_score,
        "behavior_score": behavior_score,
        "activation_probability": activation_probability,
        "conversion_probability": conversion_probability,
        "memory_signal": avg_conf,
        "recommended_action": action or "deliver_first_win",
    }
