"""
command_logger.py

채팅 명령이
- rule-based 로 처리됐는지
- LLM 기반으로 처리됐는지
를 명확히 로그로 남기는 유틸리티
"""

from typing import Literal, Optional
from datetime import datetime

CommandSource = Literal["RULE", "LLM", "NONE"]


def log_command_source(
    *,
    project_id: str,
    message: str,
    source: CommandSource,
    detail: Optional[str] = None,
):
    """
    명령 처리 출처 로그 출력.

    source:
      - RULE : 사전 정의 명령
      - LLM  : LLM 플래너 사용
      - NONE : 아무 액션도 안 함

    detail:
      - rule type, plan summary, 실패 이유 등
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(
        f"[COMMAND][{ts}] "
        f"project={project_id} "
        f"source={source} "
        f"message='{message}' "
        + (f"detail={detail}" if detail else "")
    )
