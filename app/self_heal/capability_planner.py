from __future__ import annotations

import logging
from typing import Dict, List


logger = logging.getLogger(__name__)


class CapabilityPlanner:

    def __init__(self):
        self.registry = {}

    def register_capability(
        self,
        name: str,
        required_models: List[str],
        required_routes: List[str],
        required_agents: List[str],
        required_views: List[str],
    ):
        self.registry[name] = {
            "models": required_models,
            "routes": required_routes,
            "agents": required_agents,
            "views": required_views,
        }

        logger.warning(
            "CAPABILITY_REGISTERED %s",
            name,
        )

    def build_execution_plan(
        self,
        capability_name: str,
    ) -> Dict:

        capability = self.registry.get(capability_name)

        if not capability:
            logger.warning(
                "CAPABILITY_UNKNOWN %s",
                capability_name,
            )
            return {}

        logger.warning(
            "CAPABILITY_PLAN_READY %s",
            capability_name,
        )

        return capability


planner = CapabilityPlanner()
