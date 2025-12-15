"""
plan_schema.py

LLM(또는 규칙 기반 플래너)이 반환하는 "편집 계획(Plan)"의 스키마.
현재 Step2에서는 LLM 대신 더미 플래너가 Plan을 생성하지만,
나중에 그대로 LLM 출력(JSON) 검증에도 사용합니다.
"""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


ToolName = Literal[
    "place_drum",
    "place_note",
    "move_event",
    "delete_event",
    "undo",
]


class PlanAction(BaseModel):
    """
    하나의 툴 호출(액션)을 표현합니다.

    - tool: 호출할 툴 이름
    - args: 툴에 전달할 인자들(키-값 딕셔너리)
    """
    tool: ToolName
    args: dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    """
    편집 계획 전체.

    - summary: 사람이 읽을 요약(디버깅/로그용)
    - actions: 툴 호출 리스트
    - assumptions: (선택) 플래너가 가정한 것들(짧게)
    """
    summary: str = ""
    actions: list[PlanAction] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    """
    /chat 요청 바디.
    """
    message: str
    # UI가 필요하면 힌트를 추가할 수 있지만 Step2에서는 안 씀
    client_state_hint: Optional[dict[str, Any]] = None


class ChatResponse(BaseModel):
    """
    /chat 응답 바디.
    """
    state: dict[str, Any]
    plan: dict[str, Any]
    messages: list[str] = Field(default_factory=list)
