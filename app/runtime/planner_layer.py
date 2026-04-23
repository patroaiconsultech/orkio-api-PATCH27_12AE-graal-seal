from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional


def _normalize_agent_name(name: str) -> str:
    return (name or "").strip().lower()


def _available(agent_names: Optional[Iterable[str]]) -> set[str]:
    return {_normalize_agent_name(x) for x in (agent_names or []) if x}


def _task_for_agent(name: str, registry: Dict[str, Any]) -> str:
    meta = registry.get(name, {}) or {}
    caps = meta.get("capabilities") or []
    return caps[0] if caps else "guide"


def _build_runtime_override(
    intent_package: Dict[str, Any],
    capability_registry: Dict[str, Any],
    available: set[str],
) -> Optional[Dict[str, Any]]:
    runtime_op = (intent_package or {}).get("runtime_operation") or {}
    kind = str(runtime_op.get("kind") or "").strip().lower()
    target_agent = _normalize_agent_name(runtime_op.get("target_agent") or "")

    if not kind or not target_agent:
        return None

    present = (not available) or (target_agent in available)
    planner_confidence = float(intent_package.get("confidence") or 0.95)

    route_by_kind = {
        "squad_list": "squad_agents_list",
        "platform_audit": "platform_self_audit",
        "runtime_scan": "runtime_scan",
        "repo_scan": "repo_structure_scan",
        "security_scan": "security_scan",
        "patch_plan": "safe_patch_plan",
        "github_runtime_read": runtime_op.get("requires_capability") or "github_repo_read",
        "github_runtime_write": runtime_op.get("requires_capability") or "github_repo_write",
        "github_runtime_general": runtime_op.get("requires_capability") or "github_repo_read",
        "db_runtime_governed": runtime_op.get("requires_capability") or "db_schema_fix_governed",
    }

    task = route_by_kind.get(kind) or runtime_op.get("requires_capability") or _task_for_agent(target_agent, capability_registry)

    nodes: List[Dict[str, Any]] = [
        {
            "id": target_agent,
            "mode": "execute",
            "task": task,
            "available": present,
            "role": (capability_registry.get(target_agent, {}) or {}).get("role"),
            "runtime_operation": kind,
        }
    ]

    if target_agent != "metatron":
        nodes.append({
            "id": "metatron",
            "mode": "scribe",
            "task": _task_for_agent("metatron", capability_registry),
            "available": (not available or "metatron" in available),
            "role": (capability_registry.get("metatron", {}) or {}).get("role"),
        })

    # Specialist advisory mesh for audits
    if kind == "platform_audit":
        for specialist in ["auditor", "cto", "chris", "saint_germain"]:
            specialist_present = (not available) or (specialist in available)
            nodes.append({
                "id": specialist,
                "mode": "advisory",
                "task": _task_for_agent(specialist, capability_registry),
                "available": specialist_present,
                "role": (capability_registry.get(specialist, {}) or {}).get("role"),
            })

    edges: List[Dict[str, Any]] = []

    if kind == "platform_audit":
        for specialist in ["auditor", "cto", "chris", "saint_germain"]:
            edges.append({"from": target_agent, "to": specialist, "condition": "specialist_review"})
            edges.append({"from": specialist, "to": "metatron", "condition": "register_audit_findings"})
    elif len(nodes) > 1:
        edges.append({"from": target_agent, "to": "metatron", "condition": "register_execution_receipt"})

    execution_order = [target_agent] if present else []
    if kind == "platform_audit":
        execution_order = [x for x in [target_agent, "auditor", "cto", "chris", "saint_germain", "metatron"] if (not available) or (x in available)]

    default_order = list(execution_order)
    baseline_order = ["orkio"]

    primary_objective = intent_package.get("first_win_goal") or "execute_runtime_operation"
    stop_condition = "runtime_execution_or_error"
    if kind == "platform_audit":
        stop_condition = "audit_plan_ready_without_execution"

    return {
        "planner_version": "v4-evolution-orchestrator",
        "routing_mode": "runtime_execution_priority",
        "routing_source": "planner",
        "routing_override_reason": f"runtime_operation_detected:{kind}",
        "primary_objective": primary_objective,
        "stop_condition": stop_condition,
        "execution_strategy": "single_visible_speaker",
        "single_visible_speaker": True,
        "fallback_strategy": "single_path_json_fallback",
        "parallelizable_nodes": [],
        "confidence_threshold": 0.67,
        "execution_order": execution_order,
        "default_order": default_order,
        "baseline_order": baseline_order,
        "nodes": nodes,
        "edges": edges,
        "planner_confidence": round(min(0.99, max(0.85, planner_confidence)), 2),
        "resume_hint": kind,
        "routing_confidence": round(min(0.99, max(0.90, planner_confidence)), 2),
        "runtime_operation": runtime_op,
        "requires_runtime_execution": True,
        "target_agent": target_agent,
        "requires_capability": runtime_op.get("requires_capability") or task,
        "audit_mode": runtime_op.get("audit_mode") or "",
        "prepare_only": bool(runtime_op.get("prepare_only", False)),
    }


def build_planner_snapshot(
    intent_package: Dict[str, Any],
    first_win_plan: Dict[str, Any],
    continuity_hints: Dict[str, Any],
    chain: Dict[str, Any],
    capability_registry: Dict[str, Any],
    available_agents: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    available = _available(available_agents)

    runtime_override = _build_runtime_override(intent_package, capability_registry, available)
    if runtime_override:
        return runtime_override

    desired = list(chain.get("execution_sequence") or [])
    execution_order: List[str] = []
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    previous: Optional[str] = None

    for step in desired:
        name = _normalize_agent_name(step.get("agent") or "")
        if not name:
            continue
        present = not available or name in available
        if present:
            execution_order.append(name)
        nodes.append({
            "id": name,
            "mode": step.get("mode") or "concise",
            "task": step.get("task") or _task_for_agent(name, capability_registry),
            "available": present,
            "role": (capability_registry.get(name, {}) or {}).get("role"),
        })
        if previous and name:
            edges.append({"from": previous, "to": name, "condition": "after_previous"})
        previous = name

    pre_guard = _normalize_agent_name(chain.get("pre_guard") or "")
    scribe = _normalize_agent_name(chain.get("scribe") or "")
    if pre_guard:
        nodes.insert(0, {
            "id": pre_guard,
            "mode": "guard",
            "task": _task_for_agent(pre_guard, capability_registry),
            "available": (not available or pre_guard in available),
            "role": (capability_registry.get(pre_guard, {}) or {}).get("role"),
        })
        if execution_order:
            edges.insert(0, {"from": pre_guard, "to": execution_order[0], "condition": "risk_gate"})
    if scribe and (not execution_order or execution_order[-1] != scribe):
        nodes.append({
            "id": scribe,
            "mode": "scribe",
            "task": _task_for_agent(scribe, capability_registry),
            "available": (not available or scribe in available),
            "role": (capability_registry.get(scribe, {}) or {}).get("role"),
        })
        if execution_order:
            edges.append({"from": execution_order[-1], "to": scribe, "condition": "register_continuity"})

    objective = first_win_plan.get("expected_result") or intent_package.get("first_win_goal") or "clear_next_step"
    confidence = float(intent_package.get("confidence") or 0.62)
    if continuity_hints.get("has_active_project"):
        confidence = min(0.99, confidence + 0.04)
    if continuity_hints.get("memory_count"):
        confidence = min(0.99, confidence + min(0.08, float(continuity_hints.get("memory_count") or 0) * 0.01))

    default_order = [
        str(n.get("id") or "").strip().lower()
        for n in nodes
        if n.get("id") and str(n.get("mode") or "").strip().lower() not in {"guard", "scribe"} and bool(n.get("available", True))
    ]
    baseline_order = [
        _normalize_agent_name(name)
        for name in (available_agents or [])
        if _normalize_agent_name(name)
    ] or list(default_order)
    route_override = execution_order != baseline_order

    return {
        "planner_version": "v4-evolution-orchestrator",
        "routing_mode": "orchestrator_priority",
        "routing_source": "planner" if route_override else "default",
        "routing_override_reason": "orchestrator_priority" if route_override else "",
        "primary_objective": objective,
        "stop_condition": "first_win_or_clear_next_step",
        "execution_strategy": "single_visible_speaker",
        "single_visible_speaker": True,
        "fallback_strategy": "single_path_json_fallback",
        "parallelizable_nodes": [],
        "confidence_threshold": 0.67,
        "execution_order": execution_order,
        "default_order": default_order,
        "baseline_order": baseline_order,
        "nodes": nodes,
        "edges": edges,
        "planner_confidence": round(confidence, 2),
        "resume_hint": continuity_hints.get("resume_hint"),
        "routing_confidence": round(max(0.05, min(0.99, confidence if route_override else confidence * 0.92)), 2),
        "runtime_operation": (intent_package or {}).get("runtime_operation") or {},
        "requires_runtime_execution": bool((intent_package or {}).get("requires_runtime_execution")),
        "target_agent": (intent_package or {}).get("target_agent") or "",
        "requires_capability": (intent_package or {}).get("requires_capability") or "",
    }
