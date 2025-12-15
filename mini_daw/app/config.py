"""
config.py

프로젝트 전체 설정(경로/기본값)을 한 곳에 모아두는 파일입니다.
환경변수로 바꾸고 싶으면 여기만 수정하면 돼요.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """
    애플리케이션 설정값 모음.

    - storage_dir: 프로젝트/샘플/렌더 파일을 저장할 루트 폴더
    - default_bpm: 새 프로젝트 생성 시 기본 BPM
    - default_bars: 새 프로젝트 생성 시 기본 마디 수
    - ticks_per_beat: 내부 tick 해상도(16분 기준이면 4)
    """
    storage_dir: Path = Path("storage")
    default_bpm: int = 120
    default_bars: int = 4
    ticks_per_beat: int = 4


CONFIG = AppConfig()
