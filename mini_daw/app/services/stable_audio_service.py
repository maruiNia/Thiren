"""
stable_audio_service.py

Stable Audio Open 모델 호출 스켈레톤.
- 모델은 게이트(repo access)일 수 있으니 HF 토큰/권한 필요
- 환경에 따라 diffusers/torch 오디오 처리 구성 필요

Step8 성공 상태에서 "일단 붙일 자리"만 안정적으로 제공
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

class StableAudioOpenService:
    def __init__(self, model_id: str = "stabilityai/stable-audio-open-1.0", hf_token: Optional[str] = None):
        self.model_id = model_id
        self.hf_token = hf_token
        self._pipe = None

    def _lazy_load(self):
        if self._pipe is not None:
            return

        # ⚠️ 실제 사용 시 diffusers 버전/파이프라인 클래스가 환경에 맞아야 합니다.
        # 환경이 다를 수 있어서 "자리"만 제공합니다.
        from huggingface_hub import login
        if self.hf_token:
            login(self.hf_token)

        # 예시(환경에 따라 다를 수 있음):
        # from diffusers import StableAudioPipeline
        # self._pipe = StableAudioPipeline.from_pretrained(self.model_id, torch_dtype="auto").to("cuda")
        self._pipe = None  # 여기서 실제 파이프라인을 구성하세요.

    def generate(self, prompt: str, seconds: float, out_wav: Path) -> None:
        """
        prompt로 오디오 생성 후 out_wav로 저장.
        """
        self._lazy_load()
        if self._pipe is None:
            raise RuntimeError("StableAudio pipeline is not configured yet. Set up diffusers pipeline in _lazy_load().")

        # 실제 생성/저장 로직은 환경별로 달라서 여기서 구현
        # 예: waveform = self._pipe(prompt=prompt, audio_length_in_s=seconds).audios[0]
        # 저장: soundfile.write(out_wav, waveform, samplerate=44100)
        raise NotImplementedError
