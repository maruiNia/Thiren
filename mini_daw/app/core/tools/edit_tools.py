"""
edit_tools.py

ProjectState를 직접 변경하는 "툴" 구현들입니다.
Executor가 PlanAction(tool + args)을 받아서 여기 함수를 호출합니다.

Step2 범위:
- place_drum
- place_note
- move_event
- delete_event
- undo (스냅샷 기반)
"""

from __future__ import annotations

from typing import Optional
from copy import deepcopy

from app.core.state import ProjectState, Event, new_id
from app.core.refs import ExecContext


def _push_undo_snapshot(state: ProjectState, ctx: ExecContext) -> None:
    """
    Undo를 위해 events만 스냅샷으로 저장합니다.
    (나중에 tracks/meta/samples까지 확장 가능)
    """
    ctx.history_events_stack.append(deepcopy([e.__dict__ for e in state.events]))


def undo(state: ProjectState, ctx: ExecContext, steps: int = 1) -> None:
    """
    최근 스냅샷으로 되돌립니다.
    """
    for _ in range(steps):
        if not ctx.history_events_stack:
            return
        snapshot = ctx.history_events_stack.pop()
        # Event 객체로 복원
        state.events = [Event(**d) for d in snapshot]


def place_drum(
    state: ProjectState,
    ctx: ExecContext,
    *,
    track_id: int,
    start: str | int,
    duration_tick: int = 1,
    sample_id: str = "drum_kick_001",
    velocity: float = 0.9,
) -> str:
    """
    드럼 이벤트 생성.

    start는 tick(int) 또는 "bar:step" 문자열을 지원합니다.
    """
    _push_undo_snapshot(state, ctx)

    start_tick = state.clamp_tick(state.parse_time(start))
    dur = max(1, duration_tick)

    eid = new_id("e")
    ev = Event(
        id=eid,
        track_id=track_id,
        start_tick=start_tick,
        duration_tick=dur,
        type="drum",
        sample_id=sample_id,
        velocity=velocity,
        pitch=None,
    )
    state.events.append(ev)
    ctx.last_created_event_ids.append(eid)
    return eid

# Step5 place_note가 “트랙 기본 샘플”을 자동 사용
def place_note(
    state: ProjectState,
    ctx: ExecContext,
    *,
    track_id: int,
    start: str | int,
    duration_tick: int = 4,
    sample_id: str | None = None,   # ✅ 변경
    pitch: str = "A1",
    velocity: float = 0.85,
) -> str:
    """
    멜로딕 노트 이벤트 생성.

    sample_id가 None이면:
    - 해당 트랙의 current_sample_id를 사용
    - 그것도 비어 있으면 fallback으로 "bass_A1_001"
    """
    _push_undo_snapshot(state, ctx)

    start_tick = state.clamp_tick(state.parse_time(start))
    dur = max(1, duration_tick)

    # ✅ 트랙의 기본 샘플 자동 선택
    if sample_id is None:
        tr = next((t for t in state.tracks if t.id == track_id), None)
        sample_id = (tr.current_sample_id if tr and tr.current_sample_id else "bass_A1_001")

    eid = new_id("e")
    ev = Event(
        id=eid,
        track_id=track_id,
        start_tick=start_tick,
        duration_tick=dur,
        type="melodic",
        sample_id=sample_id,
        velocity=velocity,
        pitch=pitch,
    )
    state.events.append(ev)
    ctx.last_created_event_ids.append(eid)
    return eid


def move_event(
    state: ProjectState,
    ctx: ExecContext,
    *,
    event_id: Optional[str] = None,
    event_ref: Optional[str] = None,
    delta_tick: int = 0,
) -> None:
    """
    이벤트 이동.
    - event_id 또는 event_ref("last_created")로 대상을 찾습니다.
    """
    _push_undo_snapshot(state, ctx)

    # Step 6 : last_selected 지원 추가
    target_id = event_id
    if target_id is None:
        if event_ref == "last_created":
            target_id = ctx.last_created()
        elif event_ref == "last_selected":
            target_id = ctx.last_selected()

    if not target_id:
        return

    ev = next((e for e in state.events if e.id == target_id), None)
    if ev is None:
        return

    ev.start_tick = state.clamp_tick(ev.start_tick + int(delta_tick))


def delete_event(
    state: ProjectState,
    ctx: ExecContext,
    *,
    event_id: Optional[str] = None,
    event_ref: Optional[str] = None,
) -> None:
    """
    이벤트 삭제.
    - event_id 또는 event_ref("last_created" | "last_selected")
    """
    _push_undo_snapshot(state, ctx)

    target_id = event_id
    if target_id is None:
        if event_ref == "last_created":
            target_id = ctx.last_created()
        elif event_ref == "last_selected":
            target_id = ctx.last_selected()

    if not target_id:
        return

    state.events = [e for e in state.events if e.id != target_id]


# def place_note(
#     state: ProjectState,
#     ctx: ExecContext,
#     *,
#     track_id: int,
#     start: str | int,
#     duration_tick: int = 4,
#     sample_id: str = "bass_A1_001",
#     pitch: str = "A1",
#     velocity: float = 0.85,
# ) -> str:
#     """
#     멜로딕 노트 이벤트 생성.
#     """
#     _push_undo_snapshot(state, ctx)

#     start_tick = state.clamp_tick(state.parse_time(start))
#     dur = max(1, duration_tick)

#     eid = new_id("e")
#     ev = Event(
#         id=eid,
#         track_id=track_id,
#         start_tick=start_tick,
#         duration_tick=dur,
#         type="melodic",
#         sample_id=sample_id,
#         velocity=velocity,
#         pitch=pitch,
#     )
#     state.events.append(ev)
#     ctx.last_created_event_ids.append(eid)
#     return eid