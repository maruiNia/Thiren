"""
refs.py

사용자가 "방금 넣은 노트" 같은 말을 했을 때,
LLM이 event_id를 정확히 모르는 상황을 해결하기 위한 참조 시스템입니다.

Step2에서는 최소 기능만:
- last_created: 마지막으로 생성된 이벤트

Step6: last_selected 지원 추가
"""

from __future__ import annotations

from dataclasses import dataclass, field

@dataclass
class ExecContext:
    """
    실행 컨텍스트(프로젝트별 메모리).

    - last_created_event_ids: 최근 생성 이벤트들
    - last_selected_event_ids: 최근 선택 이벤트들 (UI에서 클릭)
    - history_events_stack: undo용 events 스냅샷
    """
    last_created_event_ids: list[str] = field(default_factory=list)
    last_selected_event_ids: list[str] = field(default_factory=list)
    history_events_stack: list[list[dict]] = field(default_factory=list)

    def last_created(self) -> str | None:
        return self.last_created_event_ids[-1] if self.last_created_event_ids else None

    def last_selected(self) -> str | None:
        return self.last_selected_event_ids[-1] if self.last_selected_event_ids else None

    def set_selected(self, event_id: str) -> None:
        # 중복이 쌓이는 게 싫으면: 같은 거면 append 안 하게 처리
        if self.last_selected_event_ids and self.last_selected_event_ids[-1] == event_id:
            return
        self.last_selected_event_ids.append(event_id)
