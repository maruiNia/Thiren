"""
routes_chat.py

채팅 입력을 받아:
- (Step2) DummyPlanner로 Plan 생성
- Executor로 Plan 실행
- 저장 후 state 반환
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pathlib import Path

from app.config import CONFIG
from app.core.state import ProjectState
from app.core.plan_schema import ChatRequest, ChatResponse
from app.core.executor import PlanExecutor
from app.core.refs import ExecContext
from app.services.llm_service import DummyPlanner
from app.services.context_store import get_ctx
from app.services.llm_service import GemmaPlanner
from app.services.nl_rule_parser import parse_rule_command
from app.core.command_executor import apply_command
from app.services.nl_command_planner import parse_with_llm
from app.utils.command_logger import log_command_source


router = APIRouter(prefix="/api/projects", tags=["chat"])

# 간단 MVP라서 "프로젝트별 컨텍스트"를 메모리에 둡니다.
# 서버 재시작하면 사라짐. (나중에 Redis/DB로 확장 가능)
# PROJECT_CTX: dict[str, ExecContext] = {}



def project_path(project_id: str) -> Path:
    return CONFIG.storage_dir / "projects" / f"{project_id}.json"


@router.post("/{project_id}/chat", response_model=ChatResponse)
@router.post("/{project_id}/chat", response_model=ChatResponse)
def chat(project_id: str, req: ChatRequest):
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    state = ProjectState.load(path)
    ctx = get_ctx(project_id)

    # 1️⃣ 룰 기반 먼저
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

    # 2️⃣ LLM 기반
    planner = GemmaPlanner(model_name="google/gemma-2-2b-it")

    state_hint = {
        "bpm": state.meta.bpm,
        "bars": state.meta.bars,
        "ticks_per_bar": state.meta.ticks_per_bar,
        "ticks_per_beat": state.meta.ticks_per_beat,
        "total_ticks": state.meta.total_ticks,
    }
    
    plan = planner.make_plan(
        req.message,
        state_hint=state_hint
    )

    executor = PlanExecutor()
    messages = executor.execute(state, ctx, plan)
    state.save(path)

    log_command_source(
        project_id=project_id,
        message=req.message,
        source="LLM" if plan.actions else "NONE",
        detail=plan.summary,
    )

    return ChatResponse(
        state=state.to_dict(),
        plan=plan.model_dump(),
        messages=messages,
    )

