from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ValidationResult:
    ok: bool
    checks: list[dict[str, Any]]


class SelfHealValidator:
    def __init__(self, logger=None):
        self.logger = logger

    async def validate(self, action: str, payload: dict[str, Any]) -> ValidationResult:
        checks: list[dict[str, Any]] = []

        checks.append(
            {
                "name": "simulation_mode_guard",
                "ok": action in {"simulate", "pr_only", "apply_if_tests_pass", "auto_apply"},
                "details": {"action": action},
            }
        )

        checks.append(
            {
                "name": "patch_bundle_shape",
                "ok": isinstance(payload, dict) and "issue" in payload and "decision" in payload,
                "details": {"keys": sorted(list(payload.keys())) if isinstance(payload, dict) else []},
            }
        )

        issue = payload.get("issue", {}) if isinstance(payload, dict) else {}
        checks.append(
            {
                "name": "issue_has_code",
                "ok": bool(issue.get("code")),
                "details": {"code": issue.get("code")},
            }
        )

        ok = all(c["ok"] for c in checks)
        return ValidationResult(ok=ok, checks=checks)
