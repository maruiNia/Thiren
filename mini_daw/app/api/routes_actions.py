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
from typing import Literal

router = APIRouter(prefix="/api/projects", tags=["actions"])
from app.core.tools import drum_tools  # ✅ 추가


def project_path(project_id: str) -> Path:
    return CONFIG.storage_dir / "projects" / f"{project_id}.json"


class SelectRequest(BaseModel):
    event_id: str

class SetStartRequest(BaseModel):
    event_id: str
    start_tick: int

class SetPitchRequest(BaseModel):
    event_id: str
    pitch: str

class ToggleDrumRequest(BaseModel):
    start_tick: int
    drum: Literal["kick", "snare", "hihat"] = "kick"
    velocity: float | None = None
# class ToggleDrumRequest(BaseModel):
#     track_id: int = 1
#     start_tick: int
#     sample_id: str = "drum_kick_001"
#     velocity: float = 0.9

class ApplyPatternRequest(BaseModel):
    pattern: str = "four_on_the_floor"
    bars: int = 1
    base_bar: int = 1


class ToggleDrumRequest(BaseModel):
    start_tick: int
    drum: Literal["kick", "snare", "hihat"] = "kick"
    velocity: float | None = None

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

@router.post("/{project_id}/actions/set_pitch")
def set_pitch_action(project_id: str, req: SetPitchRequest):
    """
    UI에서 event_id의 pitch를 직접 변경.
    """
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    state = ProjectState.load(path)
    ev = next((e for e in state.events if e.id == req.event_id), None)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    if ev.type != "melodic":
        raise HTTPException(status_code=400, detail="Not a melodic event")

    ctx = get_ctx(project_id)

    from app.core.tools import edit_tools
    edit_tools.set_pitch(state, ctx, event_id=req.event_id, pitch=req.pitch)

    state.save(path)
    return {"ok": True, "event_id": req.event_id, "pitch": req.pitch}

@router.post("/{project_id}/actions/toggle_drum")
def toggle_drum(project_id: str, req: ToggleDrumRequest):
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    state = ProjectState.load(path)
    ctx = get_ctx(project_id)

    from app.core.tools import edit_tools
    result = edit_tools.toggle_drum_step(
        state, ctx,
        track_id=1,
        start_tick=req.start_tick,
        # sample_id=req.sample_id,
        velocity=req.velocity,
        duration_tick=1,
        tolerance_tick=0,
    )

    state.save(path)
    return {"ok": True, "result": result, "start_tick": req.start_tick, "drum": req.drum}

@router.post("/{project_id}/actions/apply_drum_pattern")
def apply_drum_pattern(project_id: str, req: ApplyPatternRequest):
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    state = ProjectState.load(path)
    ctx = get_ctx(project_id)

    from app.core.tools import edit_tools
    edit_tools.apply_drum_pattern(
        state, ctx, pattern=req.pattern, bars=req.bars, base_bar=req.base_bar
    )

    state.save(path)
    return {"ok": True, "pattern": req.pattern}

@router.post("/{project_id}/actions/toggle_drum")
def toggle_drum_action(project_id: str, req: ToggleDrumRequest):
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    state = ProjectState.load(path)
    ctx = get_ctx(project_id)

    res = drum_tools.toggle_drum(
        state,
        ctx,
        track_id=1,
        start_tick=req.start_tick,
        drum=req.drum,
        velocity=float(req.velocity) if req.velocity is not None else 0.9,
    )

    state.save(path)
    # return {"ok": True, "result": res, "state": state.to_dict()}
    return {"ok": True, "result": res, "start_tick": req.start_tick, "drum": req.drum, "state": state.to_dict()}
