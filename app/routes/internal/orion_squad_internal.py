from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from ...db import get_db
from ...arcangelic.squad_registry import load_squad_agents, load_squad_runtime_defaults
from ...arcangelic.squad_dispatch import build_orion_squad_overlay

router = APIRouter(prefix="/api/internal/orion-squad", tags=["orion-squad-internal"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    return {
        "ok": True,
        "service": "orion_squad_internal",
        "agents_loaded": len(load_squad_agents(db)),
        "runtime_defaults": load_squad_runtime_defaults(db),
    }


@router.get("/preview")
def preview(message: str, x_org_slug: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    org = (x_org_slug or "patroai").strip()
    return build_orion_squad_overlay(db, org=org, message=message)
