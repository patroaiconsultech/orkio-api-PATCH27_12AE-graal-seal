from __future__ import annotations

import os
import logging
from typing import Dict, Any


logger = logging.getLogger(__name__)


class FrontendEvolutionGuard:

    def __init__(self):
        self.enabled = os.getenv(
            "ENABLE_FRONTEND_EVOLUTION",
            "true"
        ).lower() in ("1", "true", "yes")

    def analyze_contract_mismatch(
        self,
        endpoint: str,
        expected_schema: Dict[str, Any],
        received_schema: Dict[str, Any],
    ) -> bool:

        if not self.enabled:
            return False

        if expected_schema == received_schema:
            return False

        logger.warning(
            "FRONTEND_SCHEMA_DRIFT_DETECTED endpoint=%s",
            endpoint,
        )

        return True


guard = FrontendEvolutionGuard()
