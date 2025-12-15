"""
state.py

미니 DAW의 '단일 진실(Source of Truth)'인 ProjectState를 정의합니다.
프론트(UI)에서 아무리 클릭/드래그/채팅을 해도,
최종적으로는 이 상태(JSON)가 업데이트되고 저장됩니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional
import json
import uuid


TrackType = Literal["drum", "melodic"]


def new_id(prefix: str) -> str:
    """짧고 충돌 위험이 낮은 ID를 만드는 유틸."""
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@dataclass
class ProjectMeta:
    """
    프로젝트 메타 정보.

    - time_signature: [분자, 분모] (예: [4,4])
    - bpm: 박자 빠르기
    - bars: 마디 수
    - ticks_per_beat: 내부 해상도 (16분 기준 4)
    - ticks_per_bar: 한 마디 tick 수 (4/4면 4beats * ticks_per_beat)
    - swing: 0.0 ~ 0.5 권장 (렌더링에서 오프비트를 뒤로 미루는 용도)
    """
    time_signature: list[int] = field(default_factory=lambda: [4, 4])
    bpm: int = 120
    bars: int = 4
    ticks_per_beat: int = 4
    swing: float = 0.0

    @property
    def ticks_per_bar(self) -> int:
        beats_per_bar = self.time_signature[0]  # 4/4의 4
        return beats_per_bar * self.ticks_per_beat

    @property
    def total_ticks(self) -> int:
        return self.bars * self.ticks_per_bar


@dataclass
class Track:
    """
    트랙 정보.

    - id: 1~4 고정(Drums, Bass, Pad, Lead)
    - type: drum | melodic
    - volume: 0.0~1.0
    - pan: -1.0~1.0 (L~R)
    - mute/solo: UI 토글용
    - sample_name: 현재 대표 샘플 표기(초기엔 UI 표시용 문자열)
    """
    id: int
    name: str
    type: TrackType
    volume: float = 0.8
    pan: float = 0.0
    mute: bool = False
    solo: bool = False
    sample_name: str = ""


@dataclass
class Event:
    """
    타임라인에 배치된 이벤트(노트/드럼/클립).

    - start_tick, duration_tick: 내부 시간 단위(1/16 기준 tick)
    - type: drum | melodic
    - sample_id: 샘플 키(현재는 문자열만 유지, 나중에 실제 wav 경로로 연결)
    - pitch: melodic일 때만 사용(C4 등)
    """
    id: str
    track_id: int
    start_tick: int
    duration_tick: int
    type: TrackType
    sample_id: str
    velocity: float = 0.8
    pitch: Optional[str] = None


@dataclass
class ProjectState:
    """
    프로젝트 상태 전체.

    - meta: ProjectMeta
    - tracks: Track[4]
    - events: Event[]
    - samples: {sample_id: {...}} (Step2에서 확장)
    """
    id: str
    name: str
    meta: ProjectMeta
    tracks: list[Track]
    events: list[Event] = field(default_factory=list)
    samples: dict = field(default_factory=dict)

    # ---------- time parsing ----------
    def parse_time(self, t: str | int) -> int:
        """
        시간 입력을 tick으로 정규화합니다.

        지원:
        - int: 이미 tick
        - "bar:step": bar는 1-based, step은 1..ticks_per_bar(기본 1..16)
          예) "3:1" = 3마디 시작
        """
        if isinstance(t, int):
            return t
        if ":" not in t:
            raise ValueError(f"Invalid time format: {t}")

        bar_s, step_s = t.split(":")
        bar = int(bar_s) - 1
        step = int(step_s) - 1
        tick = bar * self.meta.ticks_per_bar + step
        return tick

    def clamp_tick(self, tick: int) -> int:
        """프로젝트 범위를 넘어가지 않게 tick을 clamp."""
        return max(0, min(tick, self.meta.total_ticks))

    # ---------- serialization ----------
    def to_dict(self) -> dict:
        """JSON 저장/전송용 dict로 변환."""
        return {
            "id": self.id,
            "name": self.name,
            "meta": {
                "time_signature": self.meta.time_signature,
                "bpm": self.meta.bpm,
                "bars": self.meta.bars,
                "ticks_per_beat": self.meta.ticks_per_beat,
                "ticks_per_bar": self.meta.ticks_per_bar,
                "total_ticks": self.meta.total_ticks,
                "swing": self.meta.swing,
            },
            "tracks": [track.__dict__ for track in self.tracks],
            "events": [event.__dict__ for event in self.events],
            "samples": self.samples,
        }

    @staticmethod
    def from_dict(d: dict) -> "ProjectState":
        """dict에서 ProjectState 복원."""
        meta = ProjectMeta(
            time_signature=d["meta"]["time_signature"],
            bpm=d["meta"]["bpm"],
            bars=d["meta"]["bars"],
            ticks_per_beat=d["meta"].get("ticks_per_beat", 4),
            swing=d["meta"].get("swing", 0.0),
        )
        tracks = [Track(**t) for t in d["tracks"]]
        events = [Event(**e) for e in d.get("events", [])]
        return ProjectState(
            id=d["id"],
            name=d["name"],
            meta=meta,
            tracks=tracks,
            events=events,
            samples=d.get("samples", {}),
        )
    
    def recompute_meta(self) -> None:
        """
        meta 값 재계산.
        ProjectMeta.total_ticks가 @property(읽기 전용)인 경우를 지원합니다.

        갱신 대상:
        - ticks_per_beat (없으면 4)
        - ticks_per_bar  (없으면 ticks_per_beat * 4)
        - bars           (이미 바뀐 값 그대로 사용)
        """
        if not getattr(self, "meta", None):
            return

        # 기본값 보정
        if not getattr(self.meta, "ticks_per_beat", None):
            self.meta.ticks_per_beat = 4

        if not getattr(self.meta, "ticks_per_bar", None):
            self.meta.ticks_per_bar = int(self.meta.ticks_per_beat) * 4

        # ✅ total_ticks는 property라서 대입하지 않습니다.
        total = int(self.meta.ticks_per_bar) * int(self.meta.bars)

        # bars를 줄여서 범위 밖이 되면 clamp(또는 삭제)
        for e in self.events:
            if e.start_tick > total:
                e.start_tick = total



    def save(self, path: Path) -> None:
        """프로젝트 상태를 JSON 파일로 저장."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def load(path: Path) -> "ProjectState":
        """JSON 파일에서 프로젝트 상태를 로드."""
        d = json.loads(path.read_text(encoding="utf-8"))
        return ProjectState.from_dict(d)
    
#Step5 : 선택된 샘플” 필드 추가
@dataclass
class Track:
    """
    트랙 정보.

    - current_sample_id: 이 트랙에서 기본으로 사용할 샘플 id
      (UI에서 샘플을 클릭하면 여기로 할당됨)
    """
    id: int
    name: str
    type: TrackType
    volume: float = 0.8
    pan: float = 0.0
    mute: bool = False
    solo: bool = False
    sample_name: str = ""
    current_sample_id: str = ""   # ✅ 추가



def create_default_project(name: str, bpm: int, bars: int, ticks_per_beat: int) -> ProjectState:
    """
    새 프로젝트를 만들 때 기본 트랙 4개를 생성합니다.
    """
    pid = new_id("proj")
    meta = ProjectMeta(bpm=bpm, bars=bars, ticks_per_beat=ticks_per_beat)

    # tracks = [
    #     Track(id=1, name="Drums", type="drum", volume=0.75, pan=0.0, sample_name="Acoustic Kit 01"),
    #     Track(id=2, name="Bass", type="melodic", volume=0.80, pan=0.0, sample_name="Sub Bass 808"),
    #     Track(id=3, name="Pad", type="melodic", volume=0.60, pan=0.0, sample_name="Warm Pad A"),
    #     Track(id=4, name="Lead", type="melodic", volume=0.70, pan=0.0, sample_name="Pluck Synth C"),
    # ]
    tracks = [
        Track(id=1, name="Drums", type="drum", volume=0.75, pan=0.0,
            sample_name="Acoustic Kit 01", current_sample_id="drum_kick_001"),
        Track(id=2, name="Bass", type="melodic", volume=0.80, pan=0.0,
            sample_name="Sub Bass 808", current_sample_id="bass_A1_001"),
        Track(id=3, name="Pad", type="melodic", volume=0.60, pan=0.0,
            sample_name="Warm Pad A", current_sample_id="pad_A1_001"),
        Track(id=4, name="Lead", type="melodic", volume=0.70, pan=0.0,
            sample_name="Pluck Synth C", current_sample_id="lead_A1_001"),
    ]

    return ProjectState(id=pid, name=name, meta=meta, tracks=tracks)
