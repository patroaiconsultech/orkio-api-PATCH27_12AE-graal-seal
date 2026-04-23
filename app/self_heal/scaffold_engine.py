from __future__ import annotations

import logging
from typing import Dict, Any

from app.self_heal.capability_planner import planner


logger = logging.getLogger(__name__)


class ScaffoldEngine:

    def __init__(self):
        self.generated_blueprints = {}

    def generate_blueprint(self, capability_name: str) -> Dict[str, Any]:

        plan = planner.build_execution_plan(capability_name)

        if not plan:
            logger.warning(
                "SCAFFOLD_PLAN_NOT_FOUND %s",
                capability_name,
            )
            return {}

        blueprint = {
            "models": plan["models"],
            "routes": plan["routes"],
            "agents": plan["agents"],
            "views": plan["views"],
        }

        self.generated_blueprints[capability_name] = blueprint

        logger.warning(
            "SCAFFOLD_BLUEPRINT_READY %s",
            capability_name,
        )

        return blueprint


scaffold_engine = ScaffoldEngine()
