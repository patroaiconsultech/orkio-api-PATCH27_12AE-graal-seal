
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app" / "main.py"
MODELS = ROOT / "app" / "models.py"
VERSIONS = ROOT / "alembic" / "versions"

def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)

def ok(msg: str) -> None:
    print(f"OK: {msg}")

def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        fail(f"{label} missing: {needle}")
    ok(label)

def main() -> int:
    if not MAIN.exists() or not MODELS.exists() or not VERSIONS.exists():
        fail("project structure incomplete")

    main_txt = MAIN.read_text(encoding="utf-8", errors="ignore")
    models_txt = MODELS.read_text(encoding="utf-8", errors="ignore")

    # Routes
    require(main_txt, '@app.post("/api/realtime/start")', "route realtime/start")
    require(main_txt, '@app.post("/api/realtime/event")', "route realtime/event")
    require(main_txt, '@app.post("/api/realtime/events:batch")', "route realtime/events:batch")
    require(main_txt, '@app.post("/api/realtime/end")', "route realtime/end")

    # Safety wrappers
    require(main_txt, 'def _audit_realtime_safe', "safe audit wrapper")
    require(main_txt, 'background_tasks.add_task(punctuate_realtime_events, org, [ev.id])', "async punctuate single")
    require(main_txt, 'background_tasks.add_task(punctuate_realtime_events, org, punct_ids)', "async punctuate batch")

    # Models
    for col in [
        'class RealtimeSession(Base):',
        '__tablename__ = "realtime_sessions"',
        'agent_id = Column(String, nullable=True)',
        'agent_name = Column(String, nullable=True)',
        'user_id = Column(String, nullable=True)',
        'user_name = Column(String, nullable=True)',
        'model = Column(String, nullable=True)',
        'voice = Column(String, nullable=True)',
        'meta = Column(Text, nullable=True)',
        'class RealtimeEvent(Base):',
        '__tablename__ = "realtime_events"',
        'transcript_punct = Column(Text, nullable=True)',
        'client_event_id = Column(String, nullable=True)',
        'meta = Column(Text, nullable=True)',
    ]:
        require(models_txt, col, f"models: {col}")

    # Migrations existence
    names = {p.name for p in VERSIONS.glob("*.py")}
    expected = {
        "0016_patch0100_25S_realtime_audit.py",
        "0017_patch0100_27_1B_realtime_transcript_punct.py",
        "0019_patch0100_28_3_idempotency.py",
        "0026_patch_v64_realtime_schema_reconcile.py",
    }
    missing = sorted(expected - names)
    if missing:
        fail(f"missing migrations: {', '.join(missing)}")
    ok("realtime migrations present")

    # down_revision consistency on known problematic files
    rev18 = (VERSIONS / "0018_patch0100_28_summit_hardening_legal.py").read_text(encoding="utf-8", errors="ignore")
    rev20 = (VERSIONS / "0020_patch_v331a_onboarding_profile.py").read_text(encoding="utf-8", errors="ignore")
    require(rev18, 'down_revision = "0017_patch0100_27_1B_realtime_transcript_punct"', "0018 down_revision fixed")
    require(rev20, 'down_revision = "0019"', "0020 down_revision fixed")

    print("PASS: realtime contract + alembic hotfix static verification complete")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
