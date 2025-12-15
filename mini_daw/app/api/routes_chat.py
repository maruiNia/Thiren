"""
routes_chat.py

채팅 입력을 받아:
- (rule) 설정 명령은 즉시 적용
- (chat-generate) sample: ... 이면 Stable Audio Open으로 생성 후 samples에 추가
- (LLM) 나머지는 GemmaPlanner로 Plan 생성 -> Executor 실행
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pathlib import Path

from app.config import CONFIG
from app.core.state import ProjectState, new_id
from app.core.plan_schema import ChatRequest, ChatResponse
from app.core.executor import PlanExecutor

from app.services.context_store import get_ctx
from app.services.llm_service import GemmaPlanner
from app.services.nl_rule_parser import parse_rule_command
from app.core.command_executor import apply_command
from app.utils.command_logger import log_command_source

from app.services.stable_audio_service import StableAudioOpenService, StableAudioGenParams


router = APIRouter(prefix="/api/projects", tags=["chat"])


def project_path(project_id: str) -> Path:
    return CONFIG.storage_dir / "projects" / f"{project_id}.json"


def sample_out_path(project_id: str, sample_id: str) -> Path:
    # 파일 저장은 CONFIG.storage_dir 밑으로만
    return CONFIG.storage_dir / "samples" / project_id / f"{sample_id}.wav"


def _try_parse_chat_generate_sample(msg: str):
    """
    예시:
      - "sample: warm bass pluck"
      - "샘플 생성: punchy kick"
      - "generate sample: airy pad chord"
    """
    m = msg.strip()
    low = m.lower()
    if low.startswith("sample:") or low.startswith("generate sample:") or m.startswith("샘플 생성:"):
        prompt = m.split(":", 1)[1].strip()
        if not prompt:
            return None
        return {"prompt": prompt, "seconds": 1.5}
    return None


@router.post("/{project_id}/chat", response_model=ChatResponse)
def chat(project_id: str, req: ChatRequest):
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    state = ProjectState.load(path)
    ctx = get_ctx(project_id)

    # 1) 룰 기반 먼저
    cmd = parse_rule_command(req.message)
    if cmd:
        apply_command(state, cmd)
        state.save(path)

        log_command_source(
            project_id=project_id,
            message=req.message,
            source="RULE",
            detail=cmd.type,
        )

        return ChatResponse(
            state=state.to_dict(),
            plan={"summary": "rule-based command", "actions": [], "assumptions": []},
            messages=[f"Applied command: {cmd.type}"],
        )

    # 2) 채팅 기반 샘플 생성 (LLM 전에!)
    gen_req = _try_parse_chat_generate_sample(req.message)
    if gen_req:
        prompt = gen_req["prompt"]
        seconds = float(gen_req.get("seconds", 1.5))

        sample_id = new_id("s")  # 예: s_ab12...
        out = sample_out_path(project_id, sample_id)
        out.parent.mkdir(parents=True, exist_ok=True)

        # Stable Audio Open 생성
        service = StableAudioOpenService()
        params = StableAudioGenParams(
            prompt=prompt,
            seconds=seconds,
            seed=None,
            num_inference_steps=40,
            guidance_scale=7.0,
        )
        service.generate_to_wav(params, out)

        # samples 등록
        state.samples[sample_id] = {
            "kind": "melodic",
            "instrument": "custom",
            "base_pitch": "A1",
            "prompt": prompt,
            "path": f"/files/samples/{project_id}/{sample_id}.wav",
        }
        state.save(path)

        log_command_source(
            project_id=project_id,
            message=req.message,
            source="RULE",
            detail="chat-generate-sample",
        )

        return ChatResponse(
            state=state.to_dict(),
            plan={"summary": "chat-generate-sample", "actions": [], "assumptions": []},
            messages=[f"Generated sample added: {sample_id}"],
        )

    # 3) LLM 기반 Plan
    planner = GemmaPlanner(model_name="google/gemma-2-2b-it")

    state_hint = {
        "bpm": state.meta.bpm,
        "bars": state.meta.bars,
        "ticks_per_bar": state.meta.ticks_per_bar,
        "ticks_per_beat": state.meta.ticks_per_beat,
        "total_ticks": state.meta.total_ticks,
    }

    plan = planner.make_plan(req.message, state_hint=state_hint)

    executor = PlanExecutor()
    messages = executor.execute(state, ctx, plan)

    log_command_source(
        project_id=project_id,
        message=req.message,
        source="LLM" if plan.actions else "NONE",
        detail=plan.summary,
    )

    state.save(path)
    return ChatResponse(
        state=state.to_dict(),
        plan=plan.model_dump(),
        messages=messages,
    )
