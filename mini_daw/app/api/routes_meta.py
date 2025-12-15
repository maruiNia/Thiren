from fastapi import APIRouter
from app.core.capabilities import CAPABILITIES

router = APIRouter(tags=["meta"])

@router.get("/api/capabilities")
def get_capabilities():
    """
    LLM이 수행 가능한 tool/action 목록(사양)을 반환.
    """
    return {"tools": CAPABILITIES}
