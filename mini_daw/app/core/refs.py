"""
refs.py

사용자가 "방금 넣은 노트" 같은 말을 했을 때,
LLM이 event_id를 정확히 모르는 상황을 해결하기 위한 참조 시스템입니다.

Step2에서는 최소 기능만:
- last_created: 마지막으로 생성된 이벤트
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExecContext:
    """
    실행 컨텍스트(메모리).

    - last_created_event_ids: 최근 생성된 이벤트 id들
    - history_events_stack: undo를 위한 events 스냅샷 스택(최소 구현)
    """
    last_created_event_ids: list[str] = field(default_factory=list)
    history_events_stack: list[list[dict]] = field(default_factory=list)

    def last_created(self) -> str | None:
        return self.last_created_event_ids[-1] if self.last_created_event_ids else None
