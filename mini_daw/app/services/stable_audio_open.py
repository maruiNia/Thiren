"""
Stable Audio Open 1.0 (diffusers StableAudioPipeline) 래퍼

- gated 모델이라 HF 토큰이 필요할 수 있음
- torch / diffusers / transformers / soundfile 필요
- GPU 권장(cuda). CPU도 가능하지만 매우 느림
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import torch
import soundfile as sf
from diffusers import StableAudioPipeline


@dataclass
class StableAudioGenConfig:
    repo_id: str = "stabilityai/stable-audio-open-1.0"
    torch_dtype: torch.dtype = torch.float16
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
    negative_prompt: str = "Low quality, average quality, noisy, distorted"
    steps: int = 120
    guidance_scale: float = 7.0


class StableAudioOpenGenerator:
    """
    StableAudioPipeline lazy-loader.
    앱 시작 시 무겁게 로딩하지 않고, 실제 생성 요청이 올 때 로딩합니다.
    """

    def __init__(self, cfg: StableAudioGenConfig | None = None):
        self.cfg = cfg or StableAudioGenConfig()
        self._pipe: Optional[StableAudioPipeline] = None

    def _ensure_pipe(self) -> StableAudioPipeline:
        if self._pipe is not None:
            return self._pipe

        # HF 토큰(선택) - gated 모델 접근이면 필요
        # 환경변수: HF_TOKEN
        token = os.getenv("HF_TOKEN")
        kwargs = {"torch_dtype": self.cfg.torch_dtype}
        if token:
            # diffusers는 token 인자로 전달 가능
            kwargs["token"] = token

        pipe = StableAudioPipeline.from_pretrained(self.cfg.repo_id, **kwargs)
        pipe = pipe.to(self.cfg.device)

        # 메모리 아끼기 옵션(필요하면)
        try:
            pipe.enable_vae_slicing()
        except Exception:
            pass

        self._pipe = pipe
        return pipe

    @torch.inference_mode()
    def generate_to_wav(
        self,
        *,
        prompt: str,
        out_wav_path: Path,
        seconds: float = 2.0,
        seed: Optional[int] = None,
    ) -> dict:
        """
        prompt -> wav 파일 생성
        반환: {"wav_path": str, "sampling_rate": int, "seconds": float}
        """
        pipe = self._ensure_pipe()

        # seconds 제한: Stable Audio Open은 최대 ~47s
        seconds = float(max(0.1, min(seconds, 47.0)))

        gen = None
        if seed is not None:
            gen = torch.Generator(pipe.device).manual_seed(int(seed))

        audios = pipe(
            prompt,
            negative_prompt=self.cfg.negative_prompt,
            num_inference_steps=int(self.cfg.steps),
            guidance_scale=float(self.cfg.guidance_scale),
            audio_end_in_s=seconds,
            num_waveforms_per_prompt=1,
            generator=gen,
        ).audios

        # audios: shape (B, C, T) 텐서 형태일 수 있음
        audio0 = audios[0]              # (channels, time)
        output = audio0.T.float().cpu().numpy()  # (time, channels)

        out_wav_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_wav_path), output, pipe.vae.sampling_rate)

        return {
            "wav_path": str(out_wav_path),
            "sampling_rate": int(pipe.vae.sampling_rate),
            "seconds": seconds,
        }
