from __future__ import annotations
from typing import Any, Dict, Iterable

def score_memory_candidate(memory_key: str, memory_value: str, intent_confidence: float = 0.62, source: str = "chat_runtime") -> float:
    key = (memory_key or "").strip().lower()
    value = (memory_value or "").strip()
    score = 0.45
    if value:
        score += min(0.18, len(value) / 600.0)
    # PATCH_LEARN: Expanded scoring for new memory categories
    if key.startswith("active_") or key.startswith("pending_"):
        score += 0.14
    if key in {"latest_intent", "expected_result"}:
        score += 0.08
    if key in {"user_preference", "user_goal"}:
        score += 0.12
    if key in {"business_context", "team_context"}:
        score += 0.10
    if source == "chat_runtime":
        score += 0.05
    score += min(0.12, max(0.0, float(intent_confidence or 0.0)) * 0.12)
    return round(min(0.97, max(0.20, score)), 2)

def build_memory_snapshot(memories: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(memories or [])
    confidences = []
    by_key: Dict[str, float] = {}
    for item in rows:
        try:
            conf = float(item.get("confidence") or 0)
        except Exception:
            conf = 0.0
        confidences.append(conf)
        key = str(item.get("memory_key") or "")
        if key:
            by_key[key] = conf
    avg = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    high = len([c for c in confidences if c >= 0.8])
    medium = len([c for c in confidences if 0.6 <= c < 0.8])
    low = len([c for c in confidences if c < 0.6])
    freshest = max([int(item.get("updated_at") or 0) for item in rows], default=0)
    return {
        "count": len(rows),
        "avg_confidence": avg,
        "high_confidence_count": high,
        "medium_confidence_count": medium,
        "low_confidence_count": low,
        "keys": by_key,
        "freshest_updated_at": freshest,
        "strong_resume_ready": bool(high or (avg >= 0.72 and len(rows) >= 2)),
    }
