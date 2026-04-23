from __future__ import annotations
from typing import Any, Dict, List, Iterable

_ACTIVE_STATUSES = {"ready", "running", "done"}

def _normalize_ids(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values or []:
        name = str(value or "").strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out

def _default_order(nodes_in: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for node in nodes_in:
        nid = str(node.get("id") or "").strip().lower()
        if not nid:
            continue
        mode = str(node.get("mode") or "").strip().lower()
        if mode in {"guard", "scribe"}:
            continue
        if bool(node.get("available", True)):
            out.append(nid)
    return out

def build_dag_execution_snapshot(planner_snapshot: Dict[str, Any] | None) -> Dict[str, Any]:
    planner_snapshot = planner_snapshot or {}
    nodes_in = list(planner_snapshot.get("nodes") or [])
    execution_order = _normalize_ids(planner_snapshot.get("execution_order") or [])
    node_map = {str(n.get("id") or "").strip().lower(): n for n in nodes_in if n.get("id")}
    default_order = _default_order(nodes_in)
    baseline_order = _normalize_ids(planner_snapshot.get("baseline_order") or []) or list(default_order)
    override_reason = planner_snapshot.get("routing_override_reason") or ""
    route_applied = bool(execution_order) and (
        bool(override_reason) or execution_order != baseline_order
    )

    execution_cursor = {
        "current_index": 0,
        "planned_current_node": execution_order[0] if execution_order else None,
        "current_node": execution_order[0] if execution_order else None,
        "completed": [],
        "remaining": execution_order[1:] if execution_order else [],
        "executed_nodes": [],
        "failed_nodes": [],
        "final_node": None,
        "execution_started_at": None,
        "execution_finished_at": None,
    }

    nodes: List[Dict[str, Any]] = []
    ready_count = 0
    unavailable_count = 0

    for idx, name in enumerate(execution_order):
        meta = node_map.get(name, {}) or {}
        available = bool(meta.get("available", True))
        status = "ready" if available else "unavailable"
        if available and execution_cursor["current_node"] == name:
            status = "running"
            execution_cursor["current_index"] = idx
        elif available and execution_cursor["current_node"] is not None:
            status = "pending"
        if status in _ACTIVE_STATUSES:
            ready_count += 1
        else:
            unavailable_count += 1

        deps = []
        for edge in (planner_snapshot.get("edges") or []):
            if str(edge.get("to") or "").strip().lower() == name:
                dep = str(edge.get("from") or "").strip().lower()
                if dep:
                    deps.append(dep)

        nodes.append({
            "id": name,
            "status": status,
            "mode": meta.get("mode") or "concise",
            "task": meta.get("task") or "guide",
            "role": meta.get("role"),
            "position": idx + 1,
            "dependencies": deps,
            "readiness": 1.0 if available else 0.0,
        })

    skipped = []
    for node in nodes_in:
        nid = str(node.get("id") or "").strip().lower()
        if not nid or nid in execution_order:
            continue
        mode = str(node.get("mode") or "").strip().lower()
        skipped.append({
            "id": nid,
            "status": "guarded" if mode == "guard" else "skipped",
            "mode": node.get("mode") or "concise",
            "task": node.get("task") or "guide",
            "role": node.get("role"),
            "dependencies": [],
            "readiness": 1.0 if bool(node.get("available", True)) else 0.0,
        })

    lifecycle = {
        "planned_nodes": list(execution_order),
        "executed_nodes": [],
        "failed_nodes": [],
        "skipped_nodes": [row["id"] for row in skipped],
    }

    return {
        "routing_mode": planner_snapshot.get("routing_mode") or "default",
        "routing_source": planner_snapshot.get("routing_source") or ("planner" if route_applied else "default"),
        "routing_confidence": float(planner_snapshot.get("routing_confidence") or 0.0),
        "ready_nodes": [n["id"] for n in nodes if n["status"] in {"ready", "running", "pending"}],
        "unavailable_nodes": [n["id"] for n in nodes if n["status"] == "unavailable"],
        "execution_nodes": [n["id"] for n in nodes],
        "standby_nodes": [n["id"] for n in skipped],
        "route_applied": route_applied,
        "baseline_order": baseline_order,
        "default_order": default_order,
        "nodes": nodes,
        "skipped_nodes": skipped,
        "execution_cursor": execution_cursor,
        "execution_lifecycle": lifecycle,
        "routing_override_reason": override_reason or (planner_snapshot.get("routing_source") if route_applied else ""),
        "planner_confidence": planner_snapshot.get("planner_confidence"),
        "primary_objective": planner_snapshot.get("primary_objective"),
        "ready_count": ready_count,
        "unavailable_count": unavailable_count,
    }

def finalize_execution_snapshot(
    dag_snapshot: Dict[str, Any] | None,
    executed_nodes: Iterable[Any] | None = None,
    failed_nodes: Iterable[Any] | None = None,
    *,
    started_at: int | None = None,
    finished_at: int | None = None,
) -> Dict[str, Any]:
    dag = dict(dag_snapshot or {})
    nodes = [dict(n or {}) for n in (dag.get("nodes") or [])]
    skipped_nodes = [dict(n or {}) for n in (dag.get("skipped_nodes") or [])]
    cursor = dict(dag.get("execution_cursor") or {})
    lifecycle = dict(dag.get("execution_lifecycle") or {})
    executed = _normalize_ids(executed_nodes or [])
    failed = _normalize_ids(failed_nodes or [])

    for node in nodes:
        nid = str(node.get("id") or "").strip().lower()
        if nid in failed:
            node["status"] = "failed"
            node["readiness"] = 0.0
        elif nid in executed:
            node["status"] = "done"
            node["readiness"] = 1.0

    planned = _normalize_ids(lifecycle.get("planned_nodes") or dag.get("execution_nodes") or [])
    remaining = [nid for nid in planned if nid not in executed and nid not in failed]
    current = remaining[0] if remaining else (executed[-1] if executed else None)

    cursor.update({
        "current_index": planned.index(current) if current in planned else max(0, len(executed) - 1),
        "planned_current_node": planned[0] if planned else None,
        "current_node": current,
        "completed": list(executed),
        "remaining": remaining[1:] if remaining else [],
        "executed_nodes": list(executed),
        "failed_nodes": list(failed),
        "final_node": executed[-1] if executed else None,
        "execution_started_at": started_at,
        "execution_finished_at": finished_at,
    })
    lifecycle.update({
        "planned_nodes": planned,
        "executed_nodes": list(executed),
        "failed_nodes": list(failed),
        "skipped_nodes": [str(n.get("id") or "").strip().lower() for n in skipped_nodes if n.get("id")],
    })

    dag["nodes"] = nodes
    dag["skipped_nodes"] = skipped_nodes
    dag["execution_cursor"] = cursor
    dag["execution_lifecycle"] = lifecycle
    return dag
