from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session


_LOCAL_MANIFEST = Path(__file__).resolve().parent / "orkio_cto_squad_manifest.v2.json"


def load_squad_manifest() -> Dict[str, Any]:
    if _LOCAL_MANIFEST.exists():
        try:
            return json.loads(_LOCAL_MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            return {"agents": [], "runtime_defaults": {}}
    return {"agents": [], "runtime_defaults": {}}


def load_squad_agents(db: Session) -> List[Dict[str, Any]]:
    """
    Fail-open loader.
    1) tenta agents_registry
    2) cai para manifesto local
    """
    try:
        rows = db.execute(text("""
            SELECT
                slug, code, name, role, layer, visibility, can_answer_direct, priority,
                activate_when, silence_when, domain_tags, config
            FROM agents_registry
            ORDER BY priority DESC, slug ASC
        """)).mappings().all()

        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "slug": r.get("slug"),
                "code": r.get("code"),
                "name": r.get("name"),
                "role": r.get("role"),
                "layer": r.get("layer"),
                "visibility": r.get("visibility"),
                "can_answer_direct": bool(r.get("can_answer_direct")),
                "priority": int(r.get("priority") or 0),
                "activate_when": list(r.get("activate_when") or []),
                "silence_when": list(r.get("silence_when") or []),
                "domain_tags": list(r.get("domain_tags") or []),
                "config": dict(r.get("config") or {}),
            })
        if out:
            return out
    except Exception:
        pass

    manifest = load_squad_manifest()
    return list(manifest.get("agents") or [])


def load_squad_runtime_defaults(db: Session) -> Dict[str, Any]:
    manifest = load_squad_manifest()
    return dict(manifest.get("runtime_defaults") or {})
