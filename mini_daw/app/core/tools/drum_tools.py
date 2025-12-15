"""
drum_tools.py

드럼 트랙(Track 1)에 대해:
- 특정 tick에 킥/스네어/하이햇 이벤트를 토글(있으면 삭제, 없으면 생성)
- 패턴 four(4-on-the-floor) 적용

주의:
- Step8 기준 ProjectState / Event 구조를 그대로 사용
"""

from __future__ import annotations

from typing import Literal
from app.core.state import ProjectState, Event, new_id
from app.core.refs import ExecContext
from app.core.tools.edit_tools import _push_undo_snapshot

DrumName = Literal["kick", "snare", "hihat"]

DRUM_SAMPLE_ID = {
    "kick": "drum_kick_001",
    "snare": "drum_snare_001",
    "hihat": "drum_hihat_001",
}


def toggle_drum(
    state: ProjectState,
    ctx: ExecContext,
    *,
    track_id: int = 1,
    start_tick: int,
    drum: DrumName = "kick",
    duration_tick: int = 1,
    velocity: float = 0.9,
) -> str:
    """
    드럼 이벤트 토글:
    - 동일 track_id + start_tick + sample_id가 존재하면 삭제
    - 없으면 생성

    반환:
    - "deleted" 또는 생성된 event_id
    """
    _push_undo_snapshot(state, ctx)

    start_tick = state.clamp_tick(int(start_tick))
    sample_id = DRUM_SAMPLE_ID[drum]

    # 동일 위치/악기 이벤트 찾기
    idx = None
    for i, e in enumerate(state.events):
        if (
            e.track_id == track_id
            and e.type == "drum"
            and e.start_tick == start_tick
            and e.sample_id == sample_id
        ):
            idx = i
            break

    if idx is not None:
        del state.events[idx]
        return "deleted"

    eid = new_id("e")
    ev = Event(
        id=eid,
        track_id=track_id,
        start_tick=start_tick,
        duration_tick=max(1, int(duration_tick)),
        type="drum",
        sample_id=sample_id,
        velocity=float(velocity),
        pitch=None,
    )
    state.events.append(ev)
    ctx.last_created_event_ids.append(eid)
    return eid


def apply_pattern_four(
    state: ProjectState,
    ctx: ExecContext,
    *,
    track_id: int = 1,
    drum: DrumName = "kick",
    velocity: float = 0.95,
    overwrite: bool = False,
) -> int:
    """
    pattern four:
    - 4/4 기준 1,2,3,4박에 킥을 깔아줌
    - 프로젝트 전체 bars에 대해 반복 적용
    - overwrite=True이면 기존 같은 악기(sample_id)의 동일 박 위치는 먼저 삭제하고 다시 생성
    반환: 생성된 이벤트 개수
    """
    _push_undo_snapshot(state, ctx)

    ticks_per_bar = state.meta.ticks_per_bar
    bars = state.meta.bars

    # 1,2,3,4박 시작 tick (16분 tick 기준이면 0,4,8,12)
    beat_starts = [0, state.meta.ticks_per_beat, 2 * state.meta.ticks_per_beat, 3 * state.meta.ticks_per_beat]
    sample_id = DRUM_SAMPLE_ID[drum]

    created = 0

    # overwrite면 먼저 제거
    if overwrite:
        keep = []
        for e in state.events:
            if e.track_id == track_id and e.type == "drum" and e.sample_id == sample_id:
                # beat 위치에 해당하는 것만 제거
                in_any = False
                for b in range(bars):
                    base = b * ticks_per_bar
                    if e.start_tick in [base + s for s in beat_starts]:
                        in_any = True
                        break
                if in_any:
                    continue
            keep.append(e)
        state.events = keep

    # 생성
    for b in range(bars):
        base = b * ticks_per_bar
        for s in beat_starts:
            start_tick = base + s

            # 이미 있으면 스킵(토글이 아니라 패턴이니까)
            exists = any(
                (e.track_id == track_id and e.type == "drum" and e.start_tick == start_tick and e.sample_id == sample_id)
                for e in state.events
            )
            if exists:
                continue

            eid = new_id("e")
            state.events.append(
                Event(
                    id=eid,
                    track_id=track_id,
                    start_tick=start_tick,
                    duration_tick=1,
                    type="drum",
                    sample_id=sample_id,
                    velocity=float(velocity),
                    pitch=None,
                )
            )
            ctx.last_created_event_ids.append(eid)
            created += 1

    return created
