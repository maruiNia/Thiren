"""
render_stub.py

Step4에서 렌더링 파이프라인이 아직 없으므로,
"무음 WAV 생성"으로 렌더/샘플 생성의 전체 흐름을 검증합니다.

나중에 여기 함수들을 실제 믹서/피치시프트/샘플러로 교체하면 됩니다.
"""

from __future__ import annotations

from pathlib import Path
import wave
import struct


def write_silence_wav(path: Path, seconds: float = 2.0, sr: int = 44100) -> None:
    """
    무음 WAV 파일 생성.

    - 16-bit PCM
    - mono
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    nframes = int(seconds * sr)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sr)

        # 무음(0) 샘플을 쭉 씀
        silence_frame = struct.pack("<h", 0)
        wf.writeframes(silence_frame * nframes)
