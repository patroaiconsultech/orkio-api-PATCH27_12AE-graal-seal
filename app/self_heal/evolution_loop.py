from __future__ import annotations

import asyncio
import os
import hashlib
import time

from sqlalchemy import select

from app.models import EvolutionProposal
from app.self_heal.frontend_guard import guard as frontend_guard
from app.self_heal.capability_planner import planner
from app.self_heal.scaffold_engine import scaffold_engine
from app.self_heal.code_emitter import code_emitter
from app.self_heal.github_bridge_executor import GitHubBridgeExecutor
from app.self_heal.github_pr_writer import pr_writer
from app.self_heal.governance import run_governed_scan_cycle
from app.self_heal.policy import SelfHealPolicy
import app.self_heal.capabilities_bootstrap  # noqa: F401

github_bridge = GitHubBridgeExecutor()


def _env_true(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default)) or str(default)).strip())
    except Exception:
        return int(default)


def _new_trace_id() -> str:
    raw = f"eloop:{time.time_ns()}"
    return "trace_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class EvolutionLoop:
    def __init__(self, db_factory, logger):
        self.db_factory = db_factory
        self.logger = logger
        self.interval = int(os.getenv("EVOLUTION_LOOP_INTERVAL", "60"))
        self.enabled = _env_true("ENABLE_EVOLUTION_LOOP", "false") or _env_true("FORCE_ENABLE_EVOLUTION_LOOP", "false")
        self.allow_bridge_execute = False
        self.allow_pr_write = False
        self.legacy_capability_autogen = False
        self.legacy_bridge_requested = _env_true("AUTO_PR_EXECUTION_ENABLED", "false")
        self.legacy_writer_requested = _env_true("AUTO_PR_WRITE_ENABLED", "false")
        self.legacy_capability_requested = _env_true("ENABLE_LEGACY_EVOLUTION_AUTOGEN", "false")
        self.min_interval = max(15, _env_int("EVOLUTION_LOOP_MIN_INTERVAL_SECONDS", 20))
        self.max_interval = max(self.min_interval, _env_int("EVOLUTION_LOOP_MAX_INTERVAL_SECONDS", 300))

    def _compute_next_interval(self, db, scan_result: dict | None = None) -> int:
        base = max(self.min_interval, min(self.max_interval, int(self.interval or 60)))
        suggested = int((scan_result or {}).get("next_interval_suggested_seconds") or 0)
        if db is None:
            return max(self.min_interval, min(self.max_interval, suggested or base))
        rows = db.execute(select(EvolutionProposal)).scalars().all()
        policy = SelfHealPolicy()
        pending_priorities = []
        cadence_hints = []
        for row in rows:
            if str(getattr(row, "status", "") or "").lower() not in {"awaiting_master_approval", "approved"}:
                continue
            priority = int(getattr(row, "last_priority_score", 0) or 0)
            if priority <= 0:
                priority = int(policy.decide(
                    severity=getattr(row, "severity", None),
                    category=getattr(row, "category", None),
                    code=getattr(row, "code", None),
                    detected_count=getattr(row, "detected_count", 1),
                    domain_scope=getattr(row, "domain_scope", None) or "general",
                    recurrence_window_count=getattr(row, "recurrence_window_count", 1),
                    blast_radius_accumulated=getattr(row, "blast_radius_accumulated", 0),
                    security_accumulated=getattr(row, "security_accumulated", 0),
                ).priority_score)
            pending_priorities.append(priority)
            cadence_hint = int(getattr(row, "last_cadence_seconds", 0) or 0)
            if cadence_hint > 0:
                cadence_hints.append(cadence_hint)
        max_pending_priority = max(pending_priorities) if pending_priorities else 0
        created = int((scan_result or {}).get("proposals_created") or 0)
        touched = int((scan_result or {}).get("proposals_touched") or 0)
        suppressed = int((scan_result or {}).get("proposals_suppressed") or 0)
        if suggested > 0:
            return max(self.min_interval, min(self.max_interval, suggested))
        if cadence_hints:
            return max(self.min_interval, min(self.max_interval, min(cadence_hints)))
        if max_pending_priority >= 85:
            return self.min_interval
        if max_pending_priority >= 70:
            return max(self.min_interval, min(base, 30))
        if max_pending_priority >= 45:
            return max(self.min_interval, min(self.max_interval, 60))
        if created > 0:
            return max(self.min_interval, min(self.max_interval, 75))
        if touched > 0 and suppressed == 0:
            return max(self.min_interval, min(self.max_interval, 90))
        if suppressed > 0 and created == 0 and touched == 0:
            return max(self.min_interval, min(self.max_interval, base * 3))
        return max(self.min_interval, min(self.max_interval, base * 2))

    async def run(self):
        try:
            self.logger.warning("EVOLUTION_LOOP_CONFIG interval=%s min=%s max=%s", self.interval, self.min_interval, self.max_interval)
        except Exception:
            pass
        if not self.enabled:
            try:
                self.logger.warning("EVOLUTION_LOOP_DISABLED approval_gate=env")
            except Exception:
                pass
            return
        try:
            self.logger.warning("EVOLUTION_LOOP_STARTED")
        except Exception:
            pass

        while True:
            db = None
            trace_id = _new_trace_id()
            next_interval = self.interval
            try:
                self.logger.warning("SELF_HEAL_DETECTOR_READY trace_id=%s", trace_id)
                self.logger.warning("SELF_HEAL_CLASSIFIER_READY trace_id=%s", trace_id)
                self.logger.warning("SELF_HEAL_POLICY_READY trace_id=%s", trace_id)
                self.logger.warning("SELF_HEAL_VALIDATOR_READY trace_id=%s", trace_id)
                try:
                    frontend_guard.analyze_contract_mismatch(
                        endpoint="realtime_stream",
                        expected_schema={"transcript": "string"},
                        received_schema={"transcript": "string"},
                    )
                except Exception:
                    pass

                db = self.db_factory() if self.db_factory else None
                result = None
                if db is not None:
                    result = await run_governed_scan_cycle(db, logger=self.logger, trace_id=trace_id)
                    try:
                        db.commit()
                    except Exception:
                        pass
                    next_interval = self._compute_next_interval(db, result)
                    try:
                        self.logger.warning(
                            "EVOLUTION_LOOP_SCAN_DONE trace_id=%s findings=%s proposals_created=%s proposals_touched=%s proposals_suppressed=%s next_interval=%s",
                            trace_id,
                            result.get("findings"),
                            result.get("proposals_created"),
                            result.get("proposals_touched"),
                            result.get("proposals_suppressed"),
                            next_interval,
                        )
                    except Exception:
                        pass

                if self.legacy_capability_requested or self.legacy_bridge_requested or self.legacy_writer_requested:
                    try:
                        self.logger.warning(
                            "EVOLUTION_LOOP_LEGACY_AUTOGEN_BLOCKED capability=%s bridge=%s writer=%s",
                            self.legacy_capability_requested,
                            self.legacy_bridge_requested,
                            self.legacy_writer_requested,
                        )
                    except Exception:
                        pass
            except Exception as exc:
                if db is not None:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                try:
                    self.logger.exception("EVOLUTION_LOOP_CYCLE_FAIL trace_id=%s error=%s", trace_id, exc)
                except Exception:
                    pass
                next_interval = max(self.min_interval, min(self.max_interval, int(self.interval or 60)))
            finally:
                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass
            await asyncio.sleep(next_interval)


async def start_evolution_loop(db_factory, logger):
    loop = EvolutionLoop(db_factory, logger)
    if not loop.enabled:
        try:
            logger.warning("EVOLUTION_LOOP_START_SKIPPED approval_gate=env")
        except Exception:
            pass
        return
    asyncio.create_task(loop.run())
