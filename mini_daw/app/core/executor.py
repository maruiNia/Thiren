"""
executor.py

Plan(툴 호출 리스트)을 받아서:
- 액션 검증/정규화(간단)
- 툴 디스패치
- 컨텍스트 업데이트(최소: last_created)
를 수행합니다.

Step2: 최소 버전.
"""

from __future__ import annotations

from typing import Any

from app.core.state import ProjectState
from app.core.plan_schema import Plan, PlanAction
from app.core.refs import ExecContext
from app.core.tools import edit_tools
from app.core.tools import drum_tools


class PlanExecutor:
    """
    Plan 실행기.

    사용 예:
        executor = PlanExecutor()
        ctx = ExecContext()
        executor.execute(state, ctx, plan)
    """

    def execute(self, state: ProjectState, ctx: ExecContext, plan: Plan) -> list[str]:
        """
        plan의 actions를 순서대로 실행합니다.

        반환:
            messages: 실행 로그(디버깅/채팅 출력에 사용 가능)
        """
        messages: list[str] = []

        for action in plan.actions:
            msg = self._dispatch(state, ctx, action)
            if msg:
                messages.append(msg)

        return messages

    def _dispatch(self, state: ProjectState, ctx: ExecContext, action: PlanAction) -> str:
        """
        tool 이름에 따라 edit_tools 함수를 호출합니다.
        """
        tool = action.tool
        args: dict[str, Any] = action.args or {}

        if tool == "place_drum":
            eid = edit_tools.place_drum(state, ctx, **args)
            return f"placed drum event {eid}"

        if tool == "place_note":
            eid = edit_tools.place_note(state, ctx, **args)
            return f"placed note event {eid}"

        if tool == "move_event":
            edit_tools.move_event(state, ctx, **args)
            return "moved event"

        if tool == "delete_event":
            edit_tools.delete_event(state, ctx, **args)
            return "deleted event"

        if tool == "undo":
            steps = int(args.get("steps", 1))
            edit_tools.undo(state, ctx, steps=steps)
            return f"undo {steps}"
        
        if tool == "set_pitch":
            edit_tools.set_pitch(state, ctx, **args)
            return "set pitch"

        if tool == "transpose_event":
            edit_tools.transpose_event(state, ctx, **args)
            return "transposed event"
        
        if tool == "apply_drum_pattern":
            edit_tools.apply_drum_pattern(state, ctx, **args)
            return "applied drum pattern"
        
        if tool == "toggle_drum":
            res = drum_tools.toggle_drum(state, ctx, **args)
            return f"toggle drum: {res}"

        if tool == "apply_pattern_four":
            n = drum_tools.apply_pattern_four(state, ctx, **args)
            return f"pattern four applied: {n} events"



        return ""
