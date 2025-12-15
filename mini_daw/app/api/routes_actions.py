"""
routes_actions.py

UI에서 발생한 편집 액션(선택/이동/삭제)을 서버에 전달하는 API.
Step6에서는 최소로 "select"만 구현합니다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path

from app.config import CONFIG
from app.core.state import ProjectState
from app.services.context_store import get_ctx


router = APIRouter(prefix="/api/projects", tags=["actions"])


def project_path(project_id: str) -> Path:
    return CONFIG.storage_dir / "projects" / f"{project_id}.json"


class SelectRequest(BaseModel):
    event_id: str

class SetStartRequest(BaseModel):
    event_id: str
    start_tick: int

@router.post("/{project_id}/actions/select")
def select_event(project_id: str, req: SelectRequest):
    """
    UI에서 클릭한 event_id를 서버 컨텍스트(last_selected)에 저장합니다.
    """
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    state = ProjectState.load(path)
    exists = any(e.id == req.event_id for e in state.events)
    if not exists:
        raise HTTPException(status_code=404, detail="Event not found")

    ctx = get_ctx(project_id)
    ctx.set_selected(req.event_id)

    return {"selected": req.event_id}

@router.post("/{project_id}/actions/set_start")
def set_start(project_id: str, req: SetStartRequest):
    """
    event_id의 start_tick을 서버에서 갱신(드래그 이동 최종 확정).
    """
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    state = ProjectState.load(path)
    exists = any(e.id == req.event_id for e in state.events)
    if not exists:
        raise HTTPException(status_code=404, detail="Event not found")

    ctx = get_ctx(project_id)

    from app.core.tools import edit_tools
    edit_tools.set_event_start(state, ctx, event_id=req.event_id, start_tick=req.start_tick)

    state.save(path)
    return {"ok": True, "event_id": req.event_id, "start_tick": req.start_tick}
