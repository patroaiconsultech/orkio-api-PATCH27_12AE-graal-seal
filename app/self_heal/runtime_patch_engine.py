from __future__ import annotations

from dataclasses import asdict
from typing import Any


class RuntimePatchEngine:
    def __init__(self, logger=None):
        self.logger = logger

    async def build_patch_bundle(self, issue, decision) -> dict[str, Any]:
        return {
            "issue": asdict(issue),
            "decision": asdict(decision),
            "mode": "governed-routing",
            "proposed_actions": self._proposed_actions(issue, decision),
        }

    def _proposed_actions(self, issue, decision) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []

        category = getattr(issue, "category", "runtime")
        code = getattr(issue, "code", "UNKNOWN")
        details = getattr(issue, "details", {}) or {}
        action = getattr(decision, "action", "simulate")

        if action == "propose_schema_patch":
            actions.append(
                {
                    "type": "schema_patch_proposal",
                    "code": code,
                    "safe": True,
                    "details": details,
                }
            )
            return actions

        if action == "pr_only":
            actions.append(
                {
                    "type": "manual_pr_required",
                    "code": code,
                    "safe": True,
                    "details": details,
                }
            )
            return actions

        if action == "simulate":
            actions.append(
                {
                    "type": "simulation_only",
                    "category": category,
                    "code": code,
                    "safe": True,
                    "details": details,
                }
            )
            return actions

        actions.append(
            {
                "type": "ignored",
                "category": category,
                "code": code,
                "safe": True,
                "details": details,
            }
        )
        return actions
