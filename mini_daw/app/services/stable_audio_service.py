"""
stable_audio_service.py

Stable Audio Open 모델 호출 스켈레톤.
- 모델은 게이트(repo access)일 수 있으니 HF 토큰/권한 필요
- 환경에 따라 diffusers/torch 오디오 처리 구성 필요

Step8 성공 상태에서 "일단 붙일 자리"만 안정적으로 제공
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

# class StableAudioOpenService:
#     def __init__(self, model_id: str = "stabilityai/stable-audio-open-1.0", hf_token: Optional[str] = None):
#         self.model_id = model_id
#         self.hf_token = hf_token
#         self._pipe = None

#     def _lazy_load(self):
#         if self._pipe is not None:
#             return

#         # ⚠️ 실제 사용 시 diffusers 버전/파이프라인 클래스가 환경에 맞아야 합니다.
#         # 환경이 다를 수 있어서 "자리"만 제공합니다.
#         from huggingface_hub import login
#         if self.hf_token:
#             login(self.hf_token)

#         # 예시(환경에 따라 다를 수 있음):
#         # from diffusers import StableAudioPipeline
#         # self._pipe = StableAudioPipeline.from_pretrained(self.model_id, torch_dtype="auto").to("cuda")
#         self._pipe = None  # 여기서 실제 파이프라인을 구성하세요.

#     def generate(self, prompt: str, seconds: float, out_wav: Path) -> None:
#         """
#         prompt로 오디오 생성 후 out_wav로 저장.
#         """
#         self._lazy_load()
#         if self._pipe is None:
#             raise RuntimeError("StableAudio pipeline is not configured yet. Set up diffusers pipeline in _lazy_load().")

#         # 실제 생성/저장 로직은 환경별로 달라서 여기서 구현
#         # 예: waveform = self._pipe(prompt=prompt, audio_length_in_s=seconds).audios[0]
#         # 저장: soundfile.write(out_wav, waveform, samplerate=44100)
#         raise NotImplementedError


@dataclass
class StableAudioGenParams:
    prompt: str
    seconds: float = 1.5
    negative_prompt: str = "low quality, noisy, distorted"
    seed: Optional[int] = None
    num_inference_steps: int = 50
    guidance_scale: float = 7.0


class StableAudioOpenService:
    """
    Stable Audio Open 1.0 생성 서비스.

    - diffusers StableAudioPipeline 사용
    - gated model이면 HF_TOKEN 및 모델 접근 승인 필요
    - 결과는 44.1kHz stereo float32 -> wav 저장
    """

    def __init__(
        self,
        model_id: str = "stabilityai/stable-audio-open-1.0",
        hf_token: Optional[str] = None,
        device: Optional[str] = None,
    ):
        self.model_id = model_id
        self.hf_token = hf_token or os.getenv("HF_TOKEN")
        self.device = device  # "cuda" / "cpu" / None(auto)
        self._pipe = None

    def _lazy_load(self):
        if self._pipe is not None:
            return

        import torch
        from diffusers import StableAudioPipeline

        # device 선택
        if self.device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        dtype = torch.float16 if (self.device == "cuda") else torch.float32

        # gated 모델이면 token 필요
        # (diffusers 내부에서 HF hub auth 사용)
        kwargs = {"torch_dtype": dtype}
        if self.hf_token:
            kwargs["token"] = self.hf_token

        pipe = StableAudioPipeline.from_pretrained(self.model_id, **kwargs)

        pipe = pipe.to(self.device)
        self._pipe = pipe

    def generate_to_wav(self, params: StableAudioGenParams, out_wav: Path) -> None:
        """
        prompt 기반으로 오디오 생성 후 wav로 저장.
        """
        self._lazy_load()

        import torch

        out_wav.parent.mkdir(parents=True, exist_ok=True)

        gen = None
        if params.seed is not None:
            gen = torch.Generator(device=self.device).manual_seed(int(params.seed))

        # Stable Audio Open은 최대 길이 제한이 있음(대략 47s)
        seconds = float(params.seconds)
        seconds = max(0.2, min(seconds, 47.0))

        # diffusers pipeline 출력
        result = self._pipe(
            params.prompt,  # prompt는 positional로 넣어도 됨
            negative_prompt=params.negative_prompt,
            num_inference_steps=int(params.num_inference_steps),
            guidance_scale=float(params.guidance_scale),
            audio_start_in_s=0.0,
            audio_end_in_s=float(seconds),
            generator=gen,
            # num_waveforms_per_prompt=1,  # 필요하면 추가
        )
        # result = self._pipe(
        #     prompt=params.prompt,
        #     negative_prompt=params.negative_prompt,
        #     audio_length_in_s=seconds,
        #     num_inference_steps=int(params.num_inference_steps),
        #     guidance_scale=float(params.guidance_scale),
        #     generator=gen,
        # )

        # result.audios: (batch, channels, samples) 또는 (batch, samples, channels) 형태가 환경에 따라 다를 수 있어 안전 처리
        audio = result.audios[0]
        # torch Tensor → numpy (GPU → CPU 이동 필수)
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        else:
            audio = np.array(audio)

        # shape 정규화: (samples, channels)
        if audio.ndim == 2:
            # (channels, samples)면 transpose
            if audio.shape[0] in (1, 2) and audio.shape[1] > audio.shape[0]:
                audio = audio.T
        elif audio.ndim == 1:
            audio = audio.reshape(-1, 1)

        # 44.1kHz로 저장(모델 스펙)
        sr = int(getattr(self._pipe.vae, "sampling_rate", 44100))
        sf.write(str(out_wav), audio.astype(np.float32), sr)

