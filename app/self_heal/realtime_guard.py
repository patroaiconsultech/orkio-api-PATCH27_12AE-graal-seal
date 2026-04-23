from __future__ import annotations

import time
from typing import Dict


class RealtimeDuplicationGuard:
    """Simple in-memory dedupe guard for realtime final commits.

    It prevents multiple final commits from the same session inside a short window.
    Process-local only, which is enough for the current Railway single-process runtime.
    """

    def __init__(self, window_ms: int = 1200):
        self.last_commit_ts: Dict[str, int] = {}
        self.window_ms = int(window_ms)

    def should_commit(self, session_id: str) -> bool:
        if not session_id:
            return True

        now = int(time.time() * 1000)
        last = self.last_commit_ts.get(session_id)

        if last is not None and (now - last) < self.window_ms:
            return False

        self.last_commit_ts[session_id] = now
        return True


guard = RealtimeDuplicationGuard()
