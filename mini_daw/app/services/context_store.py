"""
context_store.py

프로젝트별 ExecContext를 공유하기 위한 간단 저장소.
Step6에서는 메모리 딕셔너리로 유지합니다.
"""

from __future__ import annotations
from app.core.refs import ExecContext

PROJECT_CTX: dict[str, ExecContext] = {}


def get_ctx(project_id: str) -> ExecContext:
    ctx = PROJECT_CTX.get(project_id)
    if ctx is None:
        ctx = ExecContext()
        PROJECT_CTX[project_id] = ctx
    return ctx
