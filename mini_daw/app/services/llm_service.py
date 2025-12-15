"""
llm_service.py

Step2에서는 진짜 LLM 대신 "더미 플래너"를 넣습니다.
- 사용자가 치는 명령을 아주 간단히 파싱해서 Plan을 만듭니다.

나중에 여기만 교체하면:
- (message + state_summary) -> LLM -> JSON plan -> Plan 모델로 검증
으로 확장 가능합니다.
"""

from __future__ import annotations

import re
from app.core.plan_schema import Plan, PlanAction


class DummyPlanner:
    """
    더미 플래너(규칙 기반).

    지원하는 명령 예:
    - "kick 1" -> 1마디 1스텝에 킥 추가
    - "snare 2" -> 1마디 5스텝(2박 시작) 위치에 스네어 추가(간단 처리)
    - "place bass A1 2:1" -> 2마디 1스텝에 베이스 A1 추가
    - "move last +2" -> 마지막 생성 이벤트를 오른쪽 2tick 이동
    - "delete last" -> 마지막 생성 이벤트 삭제
    - "undo" / "undo 2"
    """

    def make_plan(self, message: str) -> Plan:
        m = message.strip().lower()
        plan = Plan(summary=f"dummy plan for: {message}")

        # undo
        if m.startswith("undo"):
            parts = m.split()
            steps = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
            plan.actions.append(PlanAction(tool="undo", args={"steps": steps}))
            return plan

        # move last
        if m.startswith("move last"):
            # ex) "move last +2"
            delta = 1
            mm = re.search(r"([+-]?\d+)", m)
            if mm:
                delta = int(mm.group(1))
            plan.actions.append(
                PlanAction(tool="move_event", args={"event_ref": "last_created", "delta_tick": delta})
            )
            return plan

        # delete last
        if m.startswith("delete last"):
            plan.actions.append(PlanAction(tool="delete_event", args={"event_ref": "last_created"}))
            return plan

        # very simple drum shortcuts
        if "kick" in m:
            # default: track 1, start 1:1
            plan.actions.append(
                PlanAction(tool="place_drum", args={
                    "track_id": 1, "start": "1:1", "duration_tick": 1,
                    "sample_id": "drum_kick_001", "velocity": 0.95
                })
            )
            return plan

        if "snare" in m:
            plan.actions.append(
                PlanAction(tool="place_drum", args={
                    "track_id": 1, "start": "1:5", "duration_tick": 1,  # 2박 시작(대충)
                    "sample_id": "drum_snare_001", "velocity": 0.85
                })
            )
            return plan

        # place bass A1 2:1
        if m.startswith("place bass"):
            # "place bass a1 2:1"
            parts = m.split()
            pitch = parts[2].upper() if len(parts) >= 3 else "A1"
            start = parts[3] if len(parts) >= 4 else "1:1"
            plan.actions.append(
                PlanAction(tool="place_note", args={
                    "track_id": 2, "start": start, "duration_tick": 4,
                    # "sample_id": "bass_A1_001", 
                    "pitch": pitch, "velocity": 0.85
                })
            )
            return plan
        
        # move selected
        if m.startswith("move selected"):
            # ex) "move selected +2"
            delta = 1
            mm = re.search(r"([+-]?\d+)", m)
            if mm:
                delta = int(mm.group(1))
            plan.actions.append(
                PlanAction(tool="move_event", args={"event_ref": "last_selected", "delta_tick": delta})
            )
            return plan

        # delete selected
        if m.startswith("delete selected"):
            plan.actions.append(PlanAction(tool="delete_event", args={"event_ref": "last_selected"}))
            return plan

        # default fallback: do nothing
        plan.assumptions.append("No recognized command. No actions executed.")
        return plan
