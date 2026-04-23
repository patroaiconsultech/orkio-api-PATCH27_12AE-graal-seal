from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.self_heal.code_emitter import code_emitter

logger = logging.getLogger(__name__)


class GitHubPRWriterEngine:
    """
    Deprecated writer.
    Direct GitHub writes outside git_internal are disabled by policy.
    """

    def __init__(self) -> None:
        self.enabled = False
        self.backend_repo = None
        self.frontend_repo = None
        self.branch = "selfheal/decommissioned-writer"

    def execute(self, capability_name: str) -> Dict[str, Any]:
        payload = code_emitter.generated_artifacts.get(capability_name)
        logger.warning(
            "PR_WRITER_DECOMMISSIONED capability=%s payload_present=%s",
            capability_name,
            bool(payload),
        )
        return {
            "ok": False,
            "reason": "deprecated_writer_blocked_by_governance",
            "capability_name": capability_name,
        }

    # Legacy methods kept only to avoid import breakage. They never execute operational writes.
    def _write_files(self, repo: str, files: List[Dict[str, Any]], capability_name: str) -> None:
        logger.warning("PR_WRITER_WRITE_BLOCKED repo=%s capability=%s", repo, capability_name)

    def _get_file_sha(self, repo: str, path: str) -> Optional[str]:
        return None

    def _put_file(
        self,
        repo: str,
        path: str,
        content: str,
        capability_name: str,
        sha: Optional[str],
    ):
        logger.warning("PR_WRITER_PUT_BLOCKED repo=%s path=%s capability=%s", repo, path, capability_name)
        return None

    def _headers(self) -> Dict[str, str]:
        return {}


pr_writer = GitHubPRWriterEngine()
