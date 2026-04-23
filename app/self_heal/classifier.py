from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ClassifiedIssue:
    code: str
    severity: str
    category: str
    source: str
    details: dict[str, Any]


class SelfHealClassifier:
    VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

    def __init__(self, logger=None):
        self.logger = logger

    def classify(self, findings: list[dict[str, Any]]) -> list[ClassifiedIssue]:
        out: list[ClassifiedIssue] = []

        for item in findings:
            hint = str(item.get("severity_hint", "LOW")).upper()
            severity = hint if hint in self.VALID_SEVERITIES else "LOW"

            code = str(item.get("code", "UNKNOWN"))
            source = str(item.get("source", "unknown"))

            category = self._infer_category(code=code, source=source)

            out.append(
                ClassifiedIssue(
                    code=code,
                    severity=severity,
                    category=category,
                    source=source,
                    details=item.get("details", {}),
                )
            )

        return out

    def _infer_category(self, code: str, source: str) -> str:
        raw = f"{code}:{source}".lower()

        if "schema" in raw or "table" in raw or "column" in raw or "index" in raw:
            return "schema"
        if "realtime" in raw or "sse" in raw or "stream" in raw:
            return "realtime"
        if "endpoint" in raw or "contract" in raw:
            return "contract"
        return "runtime"
