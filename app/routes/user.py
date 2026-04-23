from __future__ import annotations

from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db import get_db
from ..models import User
from ..security import decode_token

router = APIRouter()

_ALLOWED_USER_TYPES = {"founder", "investor", "operator", "partner", "other"}
_ALLOWED_INTENTS = {"explore", "meeting", "pilot", "funding", "other"}

_USER_TYPE_ALIASES = {
    "founder": "founder",
    "investor": "investor",
    "operator": "operator",
    "enterprise": "operator",
    "developer": "operator",
    "partner": "partner",
    "other": "other",
}

_INTENT_ALIASES = {
    "explore": "explore",
    "exploring": "explore",
    "curious": "explore",
    "meeting": "meeting",
    "partnership": "meeting",
    "pilot": "pilot",
    "company_eval": "pilot",
    "funding": "funding",
    "investment": "funding",
    "other": "other",
}


def _current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


def _normalize_user_type(value: Optional[str]) -> str:
    raw = str(value or "").strip().lower()
    normalized = _USER_TYPE_ALIASES.get(raw, "")
    if normalized not in _ALLOWED_USER_TYPES:
        raise HTTPException(status_code=400, detail="Invalid user_type")
    return normalized


def _normalize_intent(value: Optional[str]) -> str:
    raw = str(value or "").strip().lower()
    normalized = _INTENT_ALIASES.get(raw, "")
    if normalized not in _ALLOWED_INTENTS:
        raise HTTPException(status_code=400, detail="Invalid intent")
    return normalized


def _is_summit_eligible(u: User) -> bool:
    usage_tier = str(getattr(u, "usage_tier", "") or "").lower()
    signup_source = str(getattr(u, "signup_source", "") or "").lower()
    signup_code_label = str(getattr(u, "signup_code_label", "") or "").lower()
    return (
        usage_tier.startswith("summit_")
        or signup_source == "investor"
        or signup_code_label == "efata777"
    )


class OnboardingIn(BaseModel):
    company: Optional[str] = Field(default=None, max_length=200)
    role: Optional[str] = Field(default=None, max_length=200)
    user_type: str = Field(..., max_length=40)
    intent: str = Field(..., max_length=40)
    country: Optional[str] = Field(default=None, max_length=40)
    language: Optional[str] = Field(default=None, max_length=40)
    whatsapp: Optional[str] = Field(default=None, max_length=60)
    notes: Optional[str] = Field(default=None, max_length=1200)
    onboarding_completed: bool = True


def _complete_onboarding(inp: OnboardingIn, user: Dict[str, Any], db: Session):
    uid = user.get("sub")
    org = user.get("org") or user.get("org_slug") or ""
    u = db.execute(select(User).where(User.id == uid, User.org_slug == org)).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not (u.role == "admin" or getattr(u, "approved_at", None) or _is_summit_eligible(u)):
        raise HTTPException(status_code=403, detail="Manual approval required before onboarding.")

    # Persist incoming values
    u.company = (inp.company or "").strip() or None
    u.profile_role = (inp.role or "").strip() or None
    u.user_type = _normalize_user_type(inp.user_type)
    u.intent = _normalize_intent(inp.intent)
    u.country = (inp.country or "").strip() or None
    u.language = (inp.language or "").strip() or None
    u.whatsapp = (inp.whatsapp or "").strip() or None
    u.notes = (inp.notes or "").strip() or None
    u.onboarding_completed = bool(inp.onboarding_completed)

    # Enterprise validation (required fields enforcement)
    missing = []

    if not u.company:
        missing.append("company")

    if not u.profile_role:
        missing.append("profile_role")

    if not u.user_type:
        missing.append("user_type")

    if not u.intent:
        missing.append("intent")

    if not u.country:
        missing.append("country")

    if not u.language:
        missing.append("language")

    # WhatsApp is optional in the fluid onboarding flow.

    if missing:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Missing required onboarding fields",
                "missing_fields": missing,
            },
        )

    db.add(u)
    db.commit()
    db.refresh(u)

    return {
        "ok": True,
        "user": {
            "id": u.id,
            "company": u.company,
            "profile_role": u.profile_role,
            "user_type": u.user_type,
            "intent": u.intent,
            "country": u.country,
            "language": u.language,
            "whatsapp": u.whatsapp,
            "notes": u.notes,
            "onboarding_completed": bool(u.onboarding_completed),
        },
    }


@router.post("/api/user/onboarding")
def complete_onboarding_post(inp: OnboardingIn, user=Depends(_current_user), db: Session = Depends(get_db)):
    return _complete_onboarding(inp, user, db)


@router.put("/api/user/onboarding")
def complete_onboarding_put(inp: OnboardingIn, user=Depends(_current_user), db: Session = Depends(get_db)):
    return _complete_onboarding(inp, user, db)
