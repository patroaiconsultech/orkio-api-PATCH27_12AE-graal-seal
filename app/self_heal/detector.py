from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from sqlalchemy import text


@dataclass
class Detection:
    code: str
    severity_hint: str
    source: str
    details: dict[str, Any]


class SelfHealDetector:
    def __init__(self, db=None, logger=None):
        self.db = db
        self.logger = logger

    async def scan(self) -> list[Detection]:
        findings: list[Detection] = []

        findings.extend(await self._scan_schema_health())
        findings.extend(await self._scan_runtime_health())
        findings.extend(await self._scan_realtime_health())
        findings.extend(await self._scan_endpoint_health())

        return findings

    async def _scan_schema_health(self) -> list[Detection]:
        findings: list[Detection] = []
        if self.db is None:
            return findings

        critical_tables = [
            "users",
            "threads",
            "messages",
            "agents",
            "realtime_sessions",
            "realtime_events",
        ]

        expected_columns = {
            "messages": ["id", "org_slug", "thread_id", "role", "content", "created_at"],
            "realtime_sessions": ["id", "thread_id", "started_at", "status"],
            "realtime_events": ["id", "session_id", "event_type", "created_at"],
            "users": ["id", "email", "name"],
        }

        try:
            for table_name in critical_tables:
                exists = self._table_exists(table_name)
                if not exists:
                    findings.append(
                        Detection(
                            code="SCHEMA_MISSING_TABLE",
                            severity_hint="HIGH",
                            source="schema",
                            details={"table": table_name},
                        )
                    )

            for table_name, cols in expected_columns.items():
                if not self._table_exists(table_name):
                    continue
                actual_cols = self._get_columns(table_name)
                for col in cols:
                    if col not in actual_cols:
                        findings.append(
                            Detection(
                                code="SCHEMA_MISSING_COLUMN",
                                severity_hint="HIGH",
                                source="schema",
                                details={"table": table_name, "column": col},
                            )
                        )
        except Exception as exc:
            findings.append(
                Detection(
                    code="SCHEMA_SCAN_ERROR",
                    severity_hint="MEDIUM",
                    source="schema",
                    details={"error": repr(exc)},
                )
            )

        return findings

    async def _scan_runtime_health(self) -> list[Detection]:
        findings: list[Detection] = []

        # Package 02 ainda não faz log mining nem stack signature real.
        # Deixamos preparado para Package 03.
        return findings

    async def _scan_realtime_health(self) -> list[Detection]:
        findings: list[Detection] = []
        if self.db is None:
            return findings

        try:
            if self._table_exists("realtime_events"):
                cols = self._get_columns("realtime_events")

                expected_realtime_cols = {"session_id", "event_type", "created_at"}
                missing = sorted(list(expected_realtime_cols - cols))
                if missing:
                    findings.append(
                        Detection(
                            code="REALTIME_SCHEMA_INCOMPLETE",
                            severity_hint="HIGH",
                            source="realtime",
                            details={"missing_columns": missing},
                        )
                    )

                # heuristic: if table exists but lacks any event identity/dedup field candidates,
                # raise duplication risk as medium severity (non-blocking)
                dedup_candidates = {"event_id", "client_event_id", "item_id"}
                if cols.isdisjoint(dedup_candidates):
                    findings.append(
                        Detection(
                            code="REALTIME_DUPLICATION_RISK",
                            severity_hint="MEDIUM",
                            source="realtime",
                            details={
                                "reason": "missing_dedup_identity_columns",
                                "table": "realtime_events",
                                "candidates": sorted(list(dedup_candidates)),
                            },
                        )
                    )
        except Exception as exc:
            findings.append(
                Detection(
                    code="REALTIME_SCAN_ERROR",
                    severity_hint="MEDIUM",
                    source="realtime",
                    details={"error": repr(exc)},
                )
            )

        return findings

    async def _scan_endpoint_health(self) -> list[Detection]:
        findings: list[Detection] = []

        # Package 02 mantém health estrutural, sem chamar HTTP real.
        expected = [
            "/api/auth/register",
            "/api/realtime/start",
            "/api/realtime/end",
            "/api/internal/evolution/propose-schema-patch",
        ]

        for path in expected:
            findings.append(
                Detection(
                    code="ENDPOINT_CONTRACT_DECLARED",
                    severity_hint="LOW",
                    source="contract",
                    details={"path": path},
                )
            )

        return findings

    def serialize(self, findings: list[Detection]) -> list[dict[str, Any]]:
        return [asdict(f) for f in findings]

    def _table_exists(self, table_name: str) -> bool:
        row = self.db.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                )
                """
            ),
            {"table_name": table_name},
        ).scalar()
        return bool(row)

    def _get_columns(self, table_name: str) -> set[str]:
        rows = self.db.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).fetchall()
        return {str(r[0]) for r in rows if r and r[0]}
