"""
job_queue.py

아주 단순한 Job(백그라운드 작업) 실행/진행률 저장 시스템.
Step4에서는 Redis/Celery 없이 "메모리 딕셔너리 + 백그라운드 스레드"로 구현합니다.

장점:
- 구현이 간단하고 동작 확인이 쉬움

주의:
- 서버 재시작하면 job 정보가 사라집니다.
- 멀티 프로세스/다중 워커 환경에서는 공유되지 않습니다.
  (나중에 Redis 기반으로 바꾸면 해결됨)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any, Optional
from threading import Thread, Lock
import time
import uuid


def new_job_id() -> str:
    return f"job_{uuid.uuid4().hex[:12]}"


@dataclass
class Job:
    """
    Job 상태를 저장하는 데이터 구조.

    - status: queued | running | done | failed
    - progress: 0~100
    - message: 진행 상태 텍스트
    - result: 결과(예: 생성된 파일 경로, sample_id 등)
    - error: 실패 시 에러 문자열
    """
    id: str
    type: str
    status: str = "queued"
    progress: int = 0
    message: str = "queued"
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)


class JobQueue:
    """
    Job를 생성하고 백그라운드에서 실행하는 큐.

    사용법:
        job_id = JOBS.create("render_preview", fn=callable, args=..., kwargs=...)
        GET /api/jobs/{job_id} 로 상태 조회
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def create(self, job_type: str, fn: Callable[..., dict[str, Any]], *args, **kwargs) -> str:
        job_id = new_job_id()
        job = Job(id=job_id, type=job_type)

        with self._lock:
            self._jobs[job_id] = job

        # 백그라운드 스레드로 실행
        t = Thread(target=self._run_job, args=(job_id, fn, args, kwargs), daemon=True)
        t.start()
        return job_id

    def update(self, job_id: str, *, progress: int | None = None, message: str | None = None) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if progress is not None:
                job.progress = max(0, min(int(progress), 100))
            if message is not None:
                job.message = message

    def _run_job(self, job_id: str, fn: Callable[..., dict[str, Any]], args: tuple, kwargs: dict) -> None:
        # running으로 전환
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = "running"
            job.progress = 1
            job.message = "running"

        try:
            result = fn(job_id, *args, **kwargs)

            with self._lock:
                job = self._jobs[job_id]
                job.status = "done"
                job.progress = 100
                job.message = "done"
                job.result = result

        except Exception as e:
            with self._lock:
                job = self._jobs[job_id]
                job.status = "failed"
                job.message = "failed"
                job.error = str(e)


# 전역 큐(간단 MVP용)
JOBS = JobQueue()
