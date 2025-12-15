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


router = APIRouter(prefix="/api/projects", tags=["chat"])

# 간단 MVP라서 "프로젝트별 컨텍스트"를 메모리에 둡니다.
# 서버 재시작하면 사라짐. (나중에 Redis/DB로 확장 가능)
PROJECT_CTX: dict[str, ExecContext] = {}


def project_path(project_id: str) -> Path:
    return CONFIG.storage_dir / "projects" / f"{project_id}.json"


@router.post("/{project_id}/chat", response_model=ChatResponse)
def chat(project_id: str, req: ChatRequest):
    """
    채팅 명령을 실행하는 핵심 엔드포인트.
    """
    path = project_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    state = ProjectState.load(path)

    # 프로젝트별 context 확보
    ctx = PROJECT_CTX.get(project_id)
    if ctx is None:
        ctx = ExecContext()
        PROJECT_CTX[project_id] = ctx

    planner = DummyPlanner()
    plan = planner.make_plan(req.message)

    executor = PlanExecutor()
    messages = executor.execute(state, ctx, plan)

    # 저장
    state.save(path)

    return ChatResponse(
        state=state.to_dict(),
        plan=plan.model_dump(),
        messages=messages,
    )
