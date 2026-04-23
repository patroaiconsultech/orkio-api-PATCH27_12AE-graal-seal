from __future__ import annotations

import logging
import os

from app.self_heal.code_emitter import code_emitter
from app.self_heal.credential_scope import github_runtime_context, is_branch_allowed, is_protected_branch


logger = logging.getLogger(__name__)


class GitHubBridgeExecutor:
    """
    Deprecated runtime bridge.
    Governed git writes must flow through proposal -> master approval -> git_internal.
    This component is intentionally inert unless explicitly re-enabled in a controlled environment.
    """

    def __init__(self):
        runtime = github_runtime_context()
        self.backend_repo = runtime.get("github_repo")
        self.frontend_repo = runtime.get("github_repo_web")
        self.branch = "selfheal/runtime-bridge"
        self.enabled = bool(os.getenv("ENABLE_GOVERNED_RUNTIME_BRIDGE", "").strip().lower() in {"1", "true", "yes", "on"})

    def execute(self, capability_name: str):
        logger.warning("GITHUB_BRIDGE_DEPRECATED capability=%s enabled=%s", capability_name, self.enabled)
        if not self.enabled:
            return {"ok": False, "reason": "governed_runtime_bridge_disabled"}

        payload = code_emitter.generated_artifacts.get(capability_name)
        if not payload:
            logger.warning("GITHUB_BRIDGE_NO_PAYLOAD %s", capability_name)
            return {"ok": False, "reason": "no_payload"}

        if is_protected_branch(self.branch) or not is_branch_allowed(self.branch):
            logger.warning("GITHUB_BRIDGE_BLOCKED branch=%s capability=%s", self.branch, capability_name)
            return {"ok": False, "reason": "unsafe_runtime_branch", "branch": self.branch}

        # Even when explicitly enabled, this component only prepares metadata and never writes directly.
        return {
            "ok": True,
            "reason": "runtime_bridge_prepare_only",
            "branch": self.branch,
            "backend_repo": self.backend_repo,
            "frontend_repo": self.frontend_repo,
        }
