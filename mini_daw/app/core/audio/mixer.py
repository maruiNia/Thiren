# app/core/audio/mixer.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from app.core.state import ProjectState


@dataclass
class RenderRegion:
    """
    렌더 구간(마디 기반).
    - bar_start: 1부터 시작
    - bars: 렌더할 마디 수
    """
    bar_start: int = 1
    bars: int = 2


def _ticks_to_seconds(ticks: int, bpm: float, ticks_per_beat: int) -> float:
    sec_per_beat = 60.0 / float(bpm)
    return (ticks / float(ticks_per_beat)) * sec_per_beat


def _load_wav(path: Path, target_sr: int = 44100) -> tuple[np.ndarray, int]:
    """
    WAV 로드 후 float32, shape=(samples, channels)로 정규화.
    """
    audio, sr = sf.read(str(path), always_2d=True, dtype="float32")
    if sr != target_sr:
        # 채널별 리샘플
        g = np.gcd(sr, target_sr)
        up = target_sr // g
        down = sr // g
        audio = np.stack([resample_poly(audio[:, c], up, down) for c in range(audio.shape[1])], axis=1).astype(np.float32)
        sr = target_sr
    return audio, sr


def _ensure_stereo(audio: np.ndarray) -> np.ndarray:
    if audio.shape[1] == 1:
        return np.repeat(audio, 2, axis=1)
    if audio.shape[1] >= 2:
        return audio[:, :2]
    return np.zeros((len(audio), 2), dtype=np.float32)


def _apply_pan_stereo(stereo: np.ndarray, pan: float) -> np.ndarray:
    """
    pan: -1(left) ~ 1(right)
    간단 constant-power pan.
    """
    pan = float(np.clip(pan, -1.0, 1.0))
    # constant-power
    left = np.cos((pan + 1) * np.pi / 4)   # pan=-1 => cos(0)=1, pan=+1=>cos(pi/2)=0
    right = np.sin((pan + 1) * np.pi / 4)  # pan=-1 => sin(0)=0, pan=+1=>sin(pi/2)=1
    out = stereo.copy()
    out[:, 0] *= left
    out[:, 1] *= right
    return out


def _find_sample_path(state: ProjectState, sample_id: str, storage_dir: Path, preset_dir: Optional[Path]) -> Optional[Path]:
    """
    sample_id -> 실제 wav 파일 경로 추적.
    우선순위:
      1) state.samples[sample_id]["path"] 가 /files/... 이면 storage_dir 기준으로 변환
      2) preset_dir에서 sample_id.wav 찾기(있으면)
    """
    s = state.samples.get(sample_id)
    if s and isinstance(s, dict):
        p = s.get("path")
        if isinstance(p, str):
            # 예: /files/samples/{project_id}/{sid}.wav  -> storage/samples/{project_id}/{sid}.wav
            if p.startswith("/files/"):
                local = storage_dir / p.replace("/files/", "")
                if local.exists():
                    return local
            # 로컬 경로가 들어올 수도 있음
            lp = Path(p)
            if lp.exists():
                return lp

    if preset_dir:
        cand = preset_dir / f"{sample_id}.wav"
        if cand.exists():
            return cand

    return None


def render_mix_to_wav(
    state: ProjectState,
    *,
    out_wav: Path,
    storage_dir: Path,
    preset_dir: Optional[Path] = None,
    region: Optional[RenderRegion] = None,
    sr: int = 44100,
) -> None:
    """
    프로젝트 state를 읽어 합친 오디오를 out_wav로 렌더.

    - track volume/pan/mute/solo 반영
    - region 지정 시 해당 구간만 렌더 (preview)
    """
    bpm = state.meta.bpm
    tpb = state.meta.ticks_per_beat
    tbar = state.meta.ticks_per_bar

    if region is None:
        # 전체
        start_tick = 0
        end_tick = state.meta.total_ticks
    else:
        bar0 = max(1, int(region.bar_start)) - 1
        bars = max(1, int(region.bars))
        start_tick = bar0 * tbar
        end_tick = min(state.meta.total_ticks, start_tick + bars * tbar)

    # 소로/뮤트 계산
    solo_on = any(t.solo for t in state.tracks)
    def track_active(track_id: int) -> bool:
        t = next((x for x in state.tracks if x.id == track_id), None)
        if not t:
            return False
        if solo_on:
            return t.solo
        return not t.mute

    # 렌더 길이(초)
    region_ticks = max(0, end_tick - start_tick)
    total_sec = _ticks_to_seconds(region_ticks, bpm, tpb)
    total_samples = int(np.ceil(total_sec * sr)) + 1
    master = np.zeros((total_samples, 2), dtype=np.float32)

    # 트랙 파라미터 dict
    track_map = {t.id: t for t in state.tracks}

    for ev in state.events:
        if ev.start_tick < start_tick or ev.start_tick >= end_tick:
            continue
        if not track_active(ev.track_id):
            continue

        tr = track_map.get(ev.track_id)
        if tr is None:
            continue

        # sample path
        sp = _find_sample_path(state, ev.sample_id, storage_dir=storage_dir, preset_dir=preset_dir)
        if sp is None or not sp.exists():
            # 샘플이 없으면 그냥 스킵(렌더는 계속)
            continue

        audio, _ = _load_wav(sp, target_sr=sr)
        audio = _ensure_stereo(audio)

        # 이벤트 길이(초) — duration_tick 기준으로 자르기/패딩
        dur_ticks = max(1, int(ev.duration_tick))
        ev_sec = _ticks_to_seconds(dur_ticks, bpm, tpb)
        ev_len = int(np.ceil(ev_sec * sr))

        if len(audio) > ev_len:
            audio = audio[:ev_len, :]
        elif len(audio) < ev_len:
            pad = np.zeros((ev_len - len(audio), 2), dtype=np.float32)
            audio = np.vstack([audio, pad])

        # gain: velocity * track.volume
        vel = float(getattr(ev, "velocity", 1.0) or 1.0)
        gain = float(tr.volume) * vel
        audio = audio * gain

        # pan
        audio = _apply_pan_stereo(audio, float(tr.pan))

        # 시작 위치(샘플 인덱스)
        local_start_tick = ev.start_tick - start_tick
        start_sec = _ticks_to_seconds(local_start_tick, bpm, tpb)
        start_i = int(np.round(start_sec * sr))
        end_i = min(total_samples, start_i + len(audio))
        if start_i >= total_samples:
            continue

        master[start_i:end_i, :] += audio[: (end_i - start_i), :]

    # 간단 리미팅/클리핑 방지
    peak = float(np.max(np.abs(master))) if master.size else 0.0
    if peak > 0.98:
        master *= (0.98 / peak)

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_wav), master, sr)
