from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel

SourceTrustLevel = Literal["trusted", "internal", "external", "untrusted"]

_EXTERNAL_HINTS = {
    "github", "git", "pr", "pull_request", "issue", "commit", "external", "webhook",
    "mcp", "tool_output", "tool", "docs_external", "remote", "integration",
}
_INTERNAL_HINTS = {
    "governance", "detector", "classifier", "internal", "master_admin", "operator",
    "system", "self_heal", "evolution_internal", "audit",
}
_SECRET_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-\._=]{16,}"),
    re.compile(r"(?i)(token|secret|apikey|api_key|password)\s*[:=]\s*['\"]?[A-Za-z0-9\-\._]{8,}"),
]


class TrustEnvelope(BaseModel):
    source_type: str
    source_trust_level: SourceTrustLevel
    source_origin: str | None = None
    source_ref: str | None = None
    content_hash: str | None = None
    instruction_authority: bool = False
    secret_exposure_risk: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return self.model_dump()


def _jsonable(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value)


def _hash_content(value: Any) -> str | None:
    raw = _jsonable(value).strip()
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalized_hint(*values: Any) -> str:
    return " ".join(str(v or "").strip().lower() for v in values if str(v or "").strip())


def infer_source_trust_level(
    *,
    source_type: Any = None,
    source_origin: Any = None,
    explicit_level: Any = None,
) -> SourceTrustLevel:
    explicit = str(explicit_level or "").strip().lower()
    if explicit in {"trusted", "internal", "external", "untrusted"}:
        return explicit  # type: ignore[return-value]
    hint = _normalized_hint(source_type, source_origin)
    if not hint:
        return "untrusted"
    if any(token in hint for token in _EXTERNAL_HINTS):
        return "external"
    if any(token in hint for token in _INTERNAL_HINTS):
        return "internal"
    if "trusted" in hint:
        return "trusted"
    if "untrusted" in hint:
        return "untrusted"
    return "untrusted"


def estimate_secret_exposure_risk(value: Any) -> float:
    raw = _jsonable(value)
    if not raw:
        return 0.0
    matches = sum(1 for pattern in _SECRET_PATTERNS if pattern.search(raw))
    if matches <= 0:
        return 0.0
    return min(1.0, 0.34 * matches)


def normalize_instruction_authority(*, source_trust_level: Any, instruction_authority: Any) -> bool:
    trust = str(source_trust_level or "").strip().lower()
    requested = bool(instruction_authority)
    if trust not in {"trusted", "internal"}:
        return False
    return requested


def build_trust_envelope(
    *,
    source_type: Any,
    source_origin: Any = None,
    source_ref: Any = None,
    content: Any = None,
    explicit_level: Any = None,
    instruction_authority: bool = False,
    secret_exposure_risk: Any = None,
) -> Dict[str, Any]:
    trust = infer_source_trust_level(
        source_type=source_type,
        source_origin=source_origin,
        explicit_level=explicit_level,
    )
    risk = estimate_secret_exposure_risk(content) if secret_exposure_risk is None else max(0.0, min(1.0, float(secret_exposure_risk or 0.0)))
    envelope = TrustEnvelope(
        source_type=str(source_type or "unknown"),
        source_trust_level=trust,
        source_origin=(str(source_origin).strip() if source_origin is not None else None),
        source_ref=(str(source_ref).strip() if source_ref is not None else None),
        content_hash=_hash_content(content),
        instruction_authority=normalize_instruction_authority(
            source_trust_level=trust,
            instruction_authority=instruction_authority,
        ),
        secret_exposure_risk=risk,
    )
    return envelope.as_dict()


def coerce_trust_envelope(value: Any, *, fallback_source_type: Any = None, fallback_source_origin: Any = None) -> Dict[str, Any]:
    if isinstance(value, TrustEnvelope):
        return value.as_dict()
    if isinstance(value, dict):
        trust = infer_source_trust_level(
            source_type=value.get("source_type") or fallback_source_type,
            source_origin=value.get("source_origin") or fallback_source_origin,
            explicit_level=value.get("source_trust_level"),
        )
        return build_trust_envelope(
            source_type=value.get("source_type") or fallback_source_type or "unknown",
            source_origin=value.get("source_origin") or fallback_source_origin,
            source_ref=value.get("source_ref"),
            content=value.get("content_hash") or value,
            explicit_level=trust,
            instruction_authority=bool(value.get("instruction_authority")),
            secret_exposure_risk=value.get("secret_exposure_risk"),
        )
    return build_trust_envelope(
        source_type=fallback_source_type or "unknown",
        source_origin=fallback_source_origin,
        content=value,
    )


def trust_gate_reasons(envelope: Any) -> list[str]:
    env = coerce_trust_envelope(envelope)
    reasons: list[str] = []
    level = str(env.get("source_trust_level") or "untrusted").lower()
    if level in {"external", "untrusted"} and bool(env.get("instruction_authority")):
        reasons.append("untrusted_instruction_authority")
    risk = float(env.get("secret_exposure_risk") or 0.0)
    if risk >= 0.65:
        reasons.append("secret_exposure_risk_high")
    elif risk >= 0.35:
        reasons.append("secret_exposure_risk_medium")
    return reasons
