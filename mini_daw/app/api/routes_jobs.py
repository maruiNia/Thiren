"""
routes_jobs.py

렌더/샘플 생성 같은 "무거운 작업"을 job으로 실행하는 API.
Step4에서는 진행률을 폴링(GET /api/jobs/{job_id})로 확인합니다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path
import time

from app.config import CONFIG
from app.core.state import ProjectState, new_id
from app.services.job_queue import JOBS
from app.core.audio.render_stub import write_silence_wav


router = APIRouter(tags=["jobs"])


def project_path(project_id: str) -> Path:
    return CONFIG.storage_dir / "projects" / f"{project_id}.json"


def render_path(project_id: str, kind: str) -> Path:
    # kind: preview | mixdown
    return CONFIG.storage_dir / "renders" / project_id / f"{kind}.wav"


def sample_path(project_id: str, sample_id: str) -> Path:
    return CONFIG.storage_dir / "samples" / project_id / f"{sample_id}.wav"


class JobResponse(BaseModel):
    job_id: str


class GenerateSampleRequest(BaseModel):
    instrument: str = Field(default="bass")
    base_pitch: str = Field(default="A1")
    prompt: str = Field(default="")
    seconds: float = Field(default=1.5, ge=0.2, le=30.0)


class RenderRequest(BaseModel):
    bar_start: int = Field(default=1, ge=1, le=64)
    bars: int = Field(default=2, ge=1, le=64)
    seconds: float = Field(default=2.0, ge=0.2, le=60.0)


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    """
    Job 상태 조회(폴링용).
    """
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "result": job.result,
        "error": job.error,
    }


@router.post("/api/projects/{project_id}/jobs/render_preview", response_model=JobResponse)
def create_render_preview(project_id: str, req: RenderRequest):
    """
    프리뷰 렌더 job 생성.

    Step4에서는 무음 wav를 생성합니다.
    """
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    # 작업 함수(백그라운드)
    def _task(job_id: str) -> dict:
        JOBS.update(job_id, progress=5, message="loading project")
        state = ProjectState.load(path)

        # 진행률 시뮬레이션
        JOBS.update(job_id, progress=25, message="rendering preview (stub)")
        time.sleep(0.3)

        out = render_path(project_id, "preview")
        # 길이는 req.seconds (UI 검증용)
        write_silence_wav(out, seconds=req.seconds)
        JOBS.update(job_id, progress=80, message="writing wav")
        time.sleep(0.2)

        # 결과는 프론트에서 접근 가능한 URL로 반환
        return {"wav_url": f"/files/renders/{project_id}/preview.wav", "meta": state.meta.__dict__}

    job_id = JOBS.create("render_preview", _task)
    return JobResponse(job_id=job_id)


@router.post("/api/projects/{project_id}/jobs/render_mixdown", response_model=JobResponse)
def create_render_mixdown(project_id: str, req: RenderRequest):
    """
    믹스다운 렌더 job 생성.

    Step4에서는 무음 wav를 생성합니다.
    """
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    def _task(job_id: str) -> dict:
        JOBS.update(job_id, progress=5, message="loading project")
        state = ProjectState.load(path)

        JOBS.update(job_id, progress=30, message="mixdown rendering (stub)")
        time.sleep(0.5)

        out = render_path(project_id, "mixdown")
        write_silence_wav(out, seconds=max(req.seconds, 4.0))  # 믹스다운은 좀 길게
        JOBS.update(job_id, progress=85, message="finalizing")
        time.sleep(0.2)

        return {"wav_url": f"/files/renders/{project_id}/mixdown.wav", "meta": state.meta.__dict__}

    job_id = JOBS.create("render_mixdown", _task)
    return JobResponse(job_id=job_id)


@router.post("/api/projects/{project_id}/jobs/generate_sample", response_model=JobResponse)
def create_generate_sample(project_id: str, req: GenerateSampleRequest):
    """
    샘플 생성 job.

    Step4에서는 stable audio 대신 무음 wav를 만들고,
    project_state.samples에 sample 메타를 등록합니다.
    """
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    def _task(job_id: str) -> dict:
        JOBS.update(job_id, progress=10, message="preparing generation (stub)")
        time.sleep(0.3)

        state = ProjectState.load(path)

        JOBS.update(job_id, progress=45, message="generating audio (stub)")
        time.sleep(0.5)

        sid = new_id(f"{req.instrument}_{req.base_pitch}")
        out = sample_path(project_id, sid)
        write_silence_wav(out, seconds=req.seconds)

        # state에 sample 등록(나중에 실제 모델 결과/피치보정 정보도 여기에)
        state.samples[sid] = {
            "kind": "melodic" if req.instrument != "drums" else "drum",
            "instrument": req.instrument,
            "base_pitch": req.base_pitch,
            "prompt": req.prompt,
            "path": f"/files/samples/{project_id}/{sid}.wav",
        }
        state.save(path)

        JOBS.update(job_id, progress=90, message="saving sample metadata")
        time.sleep(0.2)

        return {"sample_id": sid, "wav_url": state.samples[sid]["path"]}

    job_id = JOBS.create("generate_sample", _task)
    return JobResponse(job_id=job_id)
