"""
routes_project.py

프로젝트 생성/조회/메타 수정/트랙 설정을 담당하는 REST API 라우터입니다.
UI는 여기 API를 호출해서 상태를 갱신합니다.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path

from app.config import CONFIG
from app.core.state import ProjectState, create_default_project


router = APIRouter(prefix="/api/projects", tags=["projects"])


def project_path(project_id: str) -> Path:
    """프로젝트 JSON 저장 경로."""
    return CONFIG.storage_dir / "projects" / f"{project_id}.json"


class CreateProjectRequest(BaseModel):
    """프로젝트 생성 요청 바디."""
    name: str = Field(default="My Project")
    bpm: int = Field(default=CONFIG.default_bpm, ge=40, le=240)
    bars: int = Field(default=CONFIG.default_bars, ge=1, le=64)


class UpdateMetaRequest(BaseModel):
    """메타 수정 요청 바디."""
    bpm: int | None = Field(default=None, ge=40, le=240)
    bars: int | None = Field(default=None, ge=1, le=64)
    swing: float | None = Field(default=None, ge=0.0, le=0.5)


class UpdateTrackRequest(BaseModel):
    """트랙 제어(볼륨/팬/뮤트/솔로) 요청 바디."""
    volume: float | None = Field(default=None, ge=0.0, le=1.0)
    pan: float | None = Field(default=None, ge=-1.0, le=1.0)
    mute: bool | None = None
    solo: bool | None = None


@router.post("")
def create_project(req: CreateProjectRequest):
    """
    새 프로젝트 생성.

    반환값: ProjectState(JSON)
    """
    proj = create_default_project(req.name, req.bpm, req.bars, CONFIG.ticks_per_beat)
    proj.save(project_path(proj.id))
    return {"state": proj.to_dict()}


@router.get("/{project_id}")
def get_project(project_id: str):
    """
    프로젝트 상태 조회.
    """
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    proj = ProjectState.load(path)
    return {"state": proj.to_dict()}


@router.patch("/{project_id}/meta")
def update_meta(project_id: str, req: UpdateMetaRequest):
    """
    BPM/Bars/Swing 같은 메타 정보를 수정합니다.
    """
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    proj = ProjectState.load(path)
    if req.bpm is not None:
        proj.meta.bpm = req.bpm
    if req.bars is not None:
        proj.meta.bars = req.bars
    if req.swing is not None:
        proj.meta.swing = req.swing

    # 마디가 줄어들면 이벤트가 프로젝트 범위를 넘어갈 수 있으니 clamp
    for e in proj.events:
        e.start_tick = proj.clamp_tick(e.start_tick)
        e.duration_tick = max(1, min(e.duration_tick, proj.meta.ticks_per_bar))

    proj.save(path)
    return {"state": proj.to_dict()}


@router.patch("/{project_id}/tracks/{track_id}")
def update_track(project_id: str, track_id: int, req: UpdateTrackRequest):
    """
    트랙 볼륨/팬/뮤트/솔로를 수정합니다.
    """
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    proj = ProjectState.load(path)
    track = next((t for t in proj.tracks if t.id == track_id), None)
    if track is None:
        raise HTTPException(status_code=404, detail="Track not found")

    if req.volume is not None:
        track.volume = req.volume
    if req.pan is not None:
        track.pan = req.pan
    if req.mute is not None:
        track.mute = req.mute
    if req.solo is not None:
        track.solo = req.solo

    proj.save(path)
    return {"state": proj.to_dict()}
