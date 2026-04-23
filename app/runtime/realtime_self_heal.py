from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, Optional


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _clean_text(value: Optional[str]) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    lowered = text.lower()
    lowered = lowered.replace("’", "'").replace("“", '"').replace("”", '"')
    return lowered.strip()


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


@dataclass
class FinalEvent:
    session_id: str
    source: str
    event_type: str
    text: str
    clean_text: str
    text_hash: str
    created_at: float


class RealtimeSelfHeal:
    def __init__(
        self,
        *,
        ttl_seconds: int = 20,
        duplicate_window_seconds: float = 4.0,
        similarity_threshold: float = 0.90,
        canonical_source: str = "text",
    ) -> None:
        self.ttl_seconds = int(ttl_seconds)
        self.duplicate_window_seconds = float(duplicate_window_seconds)
        self.similarity_threshold = float(similarity_threshold)
        self.canonical_source = canonical_source
        self._lock = threading.Lock()
        self._last_final_by_session: Dict[str, FinalEvent] = {}

    def _prune(self, now_value: float) -> None:
        expired = [
            session_id
            for session_id, evt in self._last_final_by_session.items()
            if (now_value - evt.created_at) > self.ttl_seconds
        ]
        for session_id in expired:
            self._last_final_by_session.pop(session_id, None)

    def analyze(
        self,
        *,
        session_id: str,
        text: str,
        source: str,
        event_type: str,
        now_value: Optional[float] = None,
    ) -> Dict[str, Any]:
        now_ts = float(now_value or time.time())
        clean_text = _clean_text(text)

        if not session_id:
            return {"commit": True, "reason": "missing_session_id", "canonical_source": self.canonical_source}

        if not clean_text:
            return {"commit": False, "reason": "empty_text", "canonical_source": self.canonical_source}

        incoming = FinalEvent(
            session_id=session_id,
            source=(source or "").strip().lower() or "unknown",
            event_type=(event_type or "").strip().lower() or "unknown",
            text=text,
            clean_text=clean_text,
            text_hash=_text_hash(clean_text),
            created_at=now_ts,
        )

        with self._lock:
            self._prune(now_ts)
            previous = self._last_final_by_session.get(session_id)

            if previous is None:
                self._last_final_by_session[session_id] = incoming
                return {
                    "commit": True,
                    "reason": "first_final_for_session",
                    "canonical_source": self.canonical_source,
                    "session_id": session_id,
                    "source": incoming.source,
                    "event_type": incoming.event_type,
                }

            delta = now_ts - previous.created_at
            similarity = _similarity(previous.clean_text, incoming.clean_text)
            same_hash = previous.text_hash == incoming.text_hash

            if delta <= self.duplicate_window_seconds and (same_hash or similarity >= self.similarity_threshold):
                if previous.source == self.canonical_source and incoming.source != self.canonical_source:
                    return {
                        "commit": False,
                        "reason": "duplicate_suppressed_canonical_already_committed",
                        "session_id": session_id,
                        "existing_source": previous.source,
                        "incoming_source": incoming.source,
                        "delta_seconds": round(delta, 3),
                        "similarity": round(similarity, 4),
                    }

                if incoming.source == self.canonical_source and previous.source != self.canonical_source:
                    self._last_final_by_session[session_id] = incoming
                    return {
                        "commit": False,
                        "reason": "duplicate_suppressed_canonical_replaces_audio",
                        "session_id": session_id,
                        "existing_source": previous.source,
                        "incoming_source": incoming.source,
                        "delta_seconds": round(delta, 3),
                        "similarity": round(similarity, 4),
                    }

                return {
                    "commit": False,
                    "reason": "duplicate_suppressed_same_session",
                    "session_id": session_id,
                    "existing_source": previous.source,
                    "incoming_source": incoming.source,
                    "delta_seconds": round(delta, 3),
                    "similarity": round(similarity, 4),
                }

            self._last_final_by_session[session_id] = incoming
            return {
                "commit": True,
                "reason": "new_distinct_final",
                "session_id": session_id,
                "source": incoming.source,
                "event_type": incoming.event_type,
                "delta_seconds_from_previous": round(delta, 3),
                "similarity": round(similarity, 4),
            }


_REALTIME_SELF_HEAL_ENABLED = _env_flag("REALTIME_SELF_HEAL_ENABLED", True)

realtime_self_heal = RealtimeSelfHeal(
    ttl_seconds=int(os.getenv("REALTIME_SELF_HEAL_TTL_SECONDS", "20")),
    duplicate_window_seconds=float(os.getenv("REALTIME_SELF_HEAL_WINDOW_SECONDS", "4.0")),
    similarity_threshold=float(os.getenv("REALTIME_SELF_HEAL_SIMILARITY", "0.90")),
    canonical_source=os.getenv("REALTIME_SELF_HEAL_CANONICAL_SOURCE", "text").strip().lower() or "text",
)


def should_commit_realtime_final(
    *,
    session_id: str,
    text: str,
    source: str,
    event_type: str,
) -> Dict[str, Any]:
    if not _REALTIME_SELF_HEAL_ENABLED:
        return {"commit": True, "reason": "self_heal_disabled"}
    return realtime_self_heal.analyze(
        session_id=session_id,
        text=text,
        source=source,
        event_type=event_type,
    )


def build_realtime_self_heal_incident(
    *,
    session_id: str,
    text: str,
    source: str,
    event_type: str,
) -> Dict[str, Any]:
    decision = should_commit_realtime_final(
        session_id=session_id,
        text=text,
        source=source,
        event_type=event_type,
    )
    return {
        "kind": "realtime_duplicate_final_guard",
        "session_id": session_id,
        "source": source,
        "event_type": event_type,
        "decision": decision,
        "text_preview": (text or "")[:200],
        "created_at": int(time.time()),
    }
