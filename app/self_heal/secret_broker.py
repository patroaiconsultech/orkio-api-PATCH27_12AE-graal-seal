from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Tuple

from pydantic import BaseModel


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip().strip('"').strip("'")


def _ref_env_name(ref: str) -> str:
    normalized = str(ref or "").strip().upper()
    normalized = normalized.replace(":", "__").replace("/", "_").replace("-", "_").replace(".", "_")
    normalized = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in normalized)
    return f"ORKIO_SECRET_REF_{normalized}"


def _broker_map() -> Dict[str, str]:
    raw = _env("ORKIO_SECRET_BROKER_MAP_JSON", "")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k).strip(): str(v).strip() for k, v in data.items() if str(k).strip() and str(v).strip()}


def _default_broker_map() -> Dict[str, str]:
    return {
        "control-plane:github": "envvar:ORKIO_GITHUB_CONTROL_PLANE_TOKEN",
        "mapped:control-plane.github": "envvar:ORKIO_GITHUB_CONTROL_PLANE_TOKEN",
        "control-plane:railway": "envvar:ORKIO_RAILWAY_CONTROL_PLANE_TOKEN",
        "mapped:control-plane.railway": "envvar:ORKIO_RAILWAY_CONTROL_PLANE_TOKEN",
    }


KNOWN_PROVIDER_SCHEMES = {"envvar", "file", "mapped", "vault", "kms", "external"}


class SecretResolution(BaseModel):
    ref: str
    provider: str = "none"
    value_present: bool = False
    source_hint: str | None = None
    resolved_ref: str | None = None
    provider_available: bool = True
    error: str | None = None

    def as_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class SecretProvider(ABC):
    provider: str = "unknown"

    def provider_name(self) -> str:
        return self.provider

    @abstractmethod
    def can_resolve(self, scheme: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def resolve(self, ref: str, target: str, *, required: bool = False, depth: int = 0) -> Tuple[str, SecretResolution]:
        raise NotImplementedError


class EnvVarSecretProvider(SecretProvider):
    provider = "envvar"

    def can_resolve(self, scheme: str) -> bool:
        return scheme == "envvar"

    def resolve(self, ref: str, target: str, *, required: bool = False, depth: int = 0) -> Tuple[str, SecretResolution]:
        env_name = str(target or "").strip()
        value = _env(env_name, "")
        meta = SecretResolution(
            ref=ref,
            resolved_ref=f"envvar:{env_name}",
            provider=self.provider,
            value_present=bool(value),
            source_hint=env_name or None,
            provider_available=True,
            error=None if value else ("secret_unresolved" if required else None),
        )
        if required and not value:
            raise RuntimeError(f"secret_unresolved:{ref}")
        return value, meta


class FileSecretProvider(SecretProvider):
    provider = "file"

    def can_resolve(self, scheme: str) -> bool:
        return scheme == "file"

    def resolve(self, ref: str, target: str, *, required: bool = False, depth: int = 0) -> Tuple[str, SecretResolution]:
        raw_path = str(target or "").strip()
        if raw_path.startswith("//"):
            raw_path = raw_path[2:]
        elif raw_path.startswith("/"):
            raw_path = raw_path
        try:
            value = Path(raw_path).read_text(encoding="utf-8").strip()
            error = None
        except Exception:
            value = ""
            error = "secret_file_unreadable"
        meta = SecretResolution(
            ref=ref,
            resolved_ref=f"file://{raw_path}",
            provider=self.provider,
            value_present=bool(value),
            source_hint=raw_path or None,
            provider_available=True,
            error=error if (error or required) and not value else None,
        )
        if required and not value:
            raise RuntimeError(f"secret_unresolved:{ref}")
        return value, meta


class MappedSecretProvider(SecretProvider):
    provider = "mapped"

    def can_resolve(self, scheme: str) -> bool:
        return scheme == "mapped"

    def resolve(self, ref: str, target: str, *, required: bool = False, depth: int = 0) -> Tuple[str, SecretResolution]:
        symbolic = str(target or ref or "").strip()
        target_ref = _resolve_symbolic_target(symbolic)
        if target_ref and target_ref != ref:
            return resolve_secret(target_ref, required=required, _depth=depth + 1)
        meta = SecretResolution(
            ref=ref,
            resolved_ref=None,
            provider=self.provider,
            value_present=False,
            source_hint=symbolic or None,
            provider_available=True,
            error="secret_mapping_missing",
        )
        if required:
            raise RuntimeError(f"secret_unresolved:{ref}")
        return "", meta


class PlaceholderSecretProvider(SecretProvider):
    def __init__(self, provider: str) -> None:
        self.provider = provider

    def can_resolve(self, scheme: str) -> bool:
        return scheme == self.provider

    def resolve(self, ref: str, target: str, *, required: bool = False, depth: int = 0) -> Tuple[str, SecretResolution]:
        meta = SecretResolution(
            ref=ref,
            resolved_ref=ref,
            provider=self.provider,
            value_present=False,
            source_hint=str(target or "").strip() or None,
            provider_available=False,
            error=f"{self.provider}_provider_not_configured",
        )
        if required:
            raise RuntimeError(f"secret_unresolved:{ref}")
        return "", meta


_PROVIDER_REGISTRY: list[SecretProvider] = [
    EnvVarSecretProvider(),
    FileSecretProvider(),
    MappedSecretProvider(),
    PlaceholderSecretProvider("vault"),
    PlaceholderSecretProvider("kms"),
    PlaceholderSecretProvider("external"),
]


def _resolve_symbolic_target(symbolic: str) -> str:
    key = str(symbolic or "").strip()
    if not key:
        return ""
    broker = _default_broker_map()
    broker.update(_broker_map())
    return broker.get(key) or _env(_ref_env_name(key), "")


def _split_ref(ref: str) -> tuple[str, str]:
    raw = str(ref or "").strip()
    if not raw:
        return "mapped", "control-plane:github"
    if "://" in raw:
        scheme, target = raw.split("://", 1)
        scheme = scheme.strip().lower()
        if scheme in KNOWN_PROVIDER_SCHEMES:
            if scheme == "file":
                return scheme, f"/{target}" if not target.startswith("/") else target
            return scheme, target
    if ":" in raw:
        prefix, rest = raw.split(":", 1)
        scheme = prefix.strip().lower()
        if scheme in KNOWN_PROVIDER_SCHEMES:
            return scheme, rest
    return "mapped", raw


def secret_provider_registry() -> list[str]:
    return [provider.provider_name() for provider in _PROVIDER_REGISTRY]


def resolve_secret(ref: str | None, *, required: bool = False, _depth: int = 0) -> tuple[str, SecretResolution]:
    requested = str(ref or "").strip() or (_env("GITHUB_TOKEN_REF", "") or "mapped:control-plane.github")
    if _depth > 6:
        meta = SecretResolution(
            ref=requested,
            resolved_ref=None,
            provider="mapped",
            value_present=False,
            source_hint=requested,
            provider_available=True,
            error="secret_resolution_recursion",
        )
        if required:
            raise RuntimeError(f"secret_unresolved:{requested}")
        return "", meta

    redirected = _resolve_symbolic_target(requested)
    if redirected and redirected != requested:
        return resolve_secret(redirected, required=required, _depth=_depth + 1)

    scheme, target = _split_ref(requested)
    for provider in _PROVIDER_REGISTRY:
        if provider.can_resolve(scheme):
            return provider.resolve(requested, target, required=required, depth=_depth)

    meta = SecretResolution(
        ref=requested,
        resolved_ref=None,
        provider="unresolved",
        value_present=False,
        source_hint=target or requested,
        provider_available=False,
        error="secret_provider_unknown",
    )
    if required:
        raise RuntimeError(f"secret_unresolved:{requested}")
    return "", meta


def resolve_github_token(scope_id: str = "control-plane:github", *, required: bool = False) -> tuple[str, SecretResolution]:
    ref = _env("GITHUB_TOKEN_REF", "") or str(scope_id or "control-plane:github")
    return resolve_secret(ref, required=required)


def resolve_railway_token(scope_id: str = "control-plane:railway", *, required: bool = False) -> tuple[str, SecretResolution]:
    ref = _env("RAILWAY_TOKEN_REF", "") or str(scope_id or "control-plane:railway")
    return resolve_secret(ref, required=required)
