from fastapi import APIRouter

router = APIRouter(prefix="/api/internal/manus", tags=["manus-internal"])

@router.get("/health")
def manus_health():
    return {"ok": True, "service": "manus_internal"}
