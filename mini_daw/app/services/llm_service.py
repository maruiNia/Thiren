"""
llm_service.py

Step2에서는 진짜 LLM 대신 "더미 플래너"를 넣습니다.
- 사용자가 치는 명령을 아주 간단히 파싱해서 Plan을 만듭니다.

나중에 여기만 교체하면:
- (message + state_summary) -> LLM -> JSON plan -> Plan 모델로 검증
으로 확장 가능합니다.
"""

from __future__ import annotations

import json
import re
from typing import Optional
from app.core.plan_schema import Plan, PlanAction

RE_TIME = re.compile(r"^\d+:\d+$")          # "bar:step"
RE_PITCH = re.compile(r"^[A-G]#?\d+$")      # "A1", "C#4"
RE_INT = re.compile(r"^[+-]?\d+$")

# ------------------------
# 1) 특수 명령(룰 기반)
# ------------------------
def rule_first_plan(message: str) -> Plan | None:
    m = message.strip()
    low = m.lower()

    # 1) undo
    if low.startswith("undo"):
        parts = low.split()
        steps = 1
        if len(parts) >= 2 and parts[1].isdigit():
            steps = int(parts[1])
        return Plan(summary="rule: undo", actions=[
            PlanAction(tool="undo", args={"steps": steps})
        ])

    # 2) pattern four
    if low in ("pattern four", "pattern 4", "four"):
        return Plan(summary="rule: pattern four", actions=[
            PlanAction(tool="apply_pattern_four", args={"track_id": 1, "drum": "kick", "velocity": 0.95, "overwrite": False})
        ])

    # 3) place bass A1 1:1  (일단 bass만 확정 지원)
    #    필요하면 pad/lead도 같은 방식으로 확장 가능
    parts = low.split()
    if len(parts) == 4 and parts[0] == "place" and parts[1] == "bass":
        pitch = parts[2].upper()
        start = parts[3]
        if RE_PITCH.match(pitch) and RE_TIME.match(start):
            return Plan(summary="rule: place bass", actions=[
                PlanAction(tool="place_note", args={
                    "track_id": 2, "start": start, "duration_tick": 4, "pitch": pitch
                })
            ])

    # 4) move selected +4 / delete selected
    if low.startswith("move selected"):
        mm = re.search(r"([+-]?\d+)", low)
        delta = int(mm.group(1)) if mm else 1
        return Plan(summary="rule: move selected", actions=[
            PlanAction(tool="move_event", args={"event_ref": "last_selected", "delta_tick": delta})
        ])

    if low.startswith("delete selected"):
        return Plan(summary="rule: delete selected", actions=[
            PlanAction(tool="delete_event", args={"event_ref": "last_selected"})
        ])

    # 5) set pitch C4
    if low.startswith("set pitch"):
        p = low.split()
        pitch = p[2].upper() if len(p) >= 3 else "C4"
        if RE_PITCH.match(pitch):
            return Plan(summary="rule: set pitch", actions=[
                PlanAction(tool="set_pitch", args={"event_ref": "last_selected", "pitch": pitch})
            ])

    # 6) transpose +2
    if low.startswith("transpose"):
        mm = re.search(r"([+-]?\d+)", low)
        semi = int(mm.group(1)) if mm else 0
        return Plan(summary="rule: transpose", actions=[
            PlanAction(tool="transpose_event", args={"event_ref": "last_selected", "semitone": semi})
        ])

    return None
# def rule_first_plan(message: str) -> Optional[Plan]:
#     m = message.strip().lower()

#     if m == "pattern four" or m == "pattern 4" or m == "four":
#         plan = Plan(summary="apply four-on-the-floor kick pattern")
#         plan.actions.append(
#             PlanAction(
#                 tool="apply_pattern_four",
#                 args={"track_id": 1, "drum": "kick", "velocity": 0.95, "overwrite": False},
#             )
#         )
#         return plan

#     return None


# ------------------------
# 2) Gemma 플래너
# ------------------------
class GemmaPlanner:
    """
    Gemma-2B-IT로 Plan(JSON) 생성하는 플래너.

    출력은 반드시 다음 형태의 JSON만 반환하도록 프롬프트를 강하게 줍니다:
    {
      "summary": "...",
      "actions": [{"tool":"...", "args": {...}}, ...],
      "assumptions": []
    }
    """

    def __init__(self, model_name: str = "google/gemma-2-2b-it"):
        self.model_name = model_name
        self._pipe = None

    def _lazy_load(self):
        if self._pipe is not None:
            return

        from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline

        tok = AutoTokenizer.from_pretrained(self.model_name)
        mdl = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            device_map="auto",
            torch_dtype="auto",
        )
        self._pipe = pipeline(
            "text-generation",
            model=mdl,
            tokenizer=tok,
            max_new_tokens=512,
            do_sample=False,
        )

    def make_plan(self, message: str, state_hint: dict | None = None) -> Plan:
        # 룰 우선
        p = rule_first_plan(message)
        if p:
            return p

        self._lazy_load()

        state_hint = state_hint or {}
        sys = (
            "You are a music DAW command planner.\n"
            "Return ONLY valid JSON for a plan with keys: summary, actions, assumptions.\n"
            "actions is a list of {tool, args}.\n"
            "Allowed tools:\n"
            "- toggle_drum(args: {track_id:int=1, start_tick:int, drum:'kick'|'snare'|'hihat'})\n"
            "- apply_pattern_four(args: {track_id:int=1, drum:'kick'|'snare'|'hihat', velocity:float, overwrite:bool})\n"
            "- place_note(args: {track_id:int, start:'bar:step' or int, duration_tick:int, pitch:str})\n"
            "- move_event(args: {event_ref:'last_selected'|'last_created', delta_tick:int})\n"
            "- delete_event(args: {event_ref:'last_selected'|'last_created'})\n"
            "- set_pitch(args: {event_ref:'last_selected', pitch:str})\n"
            "- transpose_event(args: {event_ref:'last_selected', semitone:int})\n"
            "- undo(args: {steps:int})\n\n"
            "If the user asks for a drum pattern 'pattern four', use apply_pattern_four.\n"
            "If unsure, return an empty actions list.\n"
        )

        user = f"User command: {message}\nState hint: {json.dumps(state_hint, ensure_ascii=False)}\nReturn JSON only."

        out = self._pipe(f"{sys}\n{user}")[0]["generated_text"]

        # 모델이 앞에 문장 섞을 수 있으니 JSON 블록만 추출
        plan_json = self._extract_json(out)
        if plan_json is None:
            # fallback: 아무 것도 안 함
            return Plan(summary="LLM parse failed", actions=[], assumptions=["parse_failed"])

        try:
            return Plan.model_validate(plan_json)
        except Exception:
            return Plan(summary="LLM schema invalid", actions=[], assumptions=["schema_invalid"])

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        # 가장 단순한 JSON 객체 추출
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        chunk = text[start : end + 1]
        try:
            return json.loads(chunk)
        except Exception:
            return None


class DummyPlanner:
    """
    더미 플래너(규칙 기반).

    지원하는 명령 예:
    - "kick 1" -> 1마디 1스텝에 킥 추가
    - "snare 2" -> 1마디 5스텝(2박 시작) 위치에 스네어 추가(간단 처리)
    - "place bass A1 2:1" -> 2마디 1스텝에 베이스 A1 추가
    - "move last +2" -> 마지막 생성 이벤트를 오른쪽 2tick 이동
    - "delete last" -> 마지막 생성 이벤트 삭제
    - "undo" / "undo 2"
    """

    def make_plan(self, message: str) -> Plan:
        m = message.strip().lower()
        plan = Plan(summary=f"dummy plan for: {message}")

        # undo
        if m.startswith("undo"):
            parts = m.split()
            steps = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
            plan.actions.append(PlanAction(tool="undo", args={"steps": steps}))
            return plan

        # move last
        if m.startswith("move last"):
            # ex) "move last +2"
            delta = 1
            mm = re.search(r"([+-]?\d+)", m)
            if mm:
                delta = int(mm.group(1))
            plan.actions.append(
                PlanAction(tool="move_event", args={"event_ref": "last_created", "delta_tick": delta})
            )
            return plan

        # delete last
        if m.startswith("delete last"):
            plan.actions.append(PlanAction(tool="delete_event", args={"event_ref": "last_created"}))
            return plan

        # very simple drum shortcuts
        if "kick" in m:
            # default: track 1, start 1:1
            plan.actions.append(
                PlanAction(tool="place_drum", args={
                    "track_id": 1, "start": "1:1", "duration_tick": 1,
                    "sample_id": "drum_kick_001", "velocity": 0.95
                })
            )
            return plan

        if "snare" in m:
            plan.actions.append(
                PlanAction(tool="place_drum", args={
                    "track_id": 1, "start": "1:5", "duration_tick": 1,  # 2박 시작(대충)
                    "sample_id": "drum_snare_001", "velocity": 0.85
                })
            )
            return plan

        # place bass A1 2:1
        if m.startswith("place bass"):
            # "place bass a1 2:1"
            parts = m.split()
            pitch = parts[2].upper() if len(parts) >= 3 else "A1"
            start = parts[3] if len(parts) >= 4 else "1:1"
            plan.actions.append(
                PlanAction(tool="place_note", args={
                    "track_id": 2, "start": start, "duration_tick": 4,
                    # "sample_id": "bass_A1_001", 
                    "pitch": pitch, "velocity": 0.85
                })
            )
            return plan
        
        # move selected
        if m.startswith("move selected"):
            # ex) "move selected +2"
            delta = 1
            mm = re.search(r"([+-]?\d+)", m)
            if mm:
                delta = int(mm.group(1))
            plan.actions.append(
                PlanAction(tool="move_event", args={"event_ref": "last_selected", "delta_tick": delta})
            )
            return plan

        # delete selected
        if m.startswith("delete selected"):
            plan.actions.append(PlanAction(tool="delete_event", args={"event_ref": "last_selected"}))
            return plan
        
        '''
        set pitch D#4
        transpose +2
        transpose -12
        이런 게 됩니다.
        '''
        # set pitch (applies to last_selected by default)
        if m.startswith("set pitch"):
            # ex) "set pitch C4"
            parts = m.split()
            pitch = parts[2].upper() if len(parts) >= 3 else "C4"
            plan.actions.append(
                PlanAction(tool="set_pitch", args={"event_ref": "last_selected", "pitch": pitch})
            )
            return plan

        # transpose
        if m.startswith("transpose"):
            # ex) "transpose +2"
            delta = 0
            mm = re.search(r"([+-]?\d+)", m)
            if mm:
                delta = int(mm.group(1))
            plan.actions.append(
                PlanAction(tool="transpose_event", args={"event_ref": "last_selected", "semitone": delta})
            )
            return plan
        
        # DummyPlanner 규칙만 추가
        if m.startswith("pattern"):
            # ex) pattern four / pattern backbeat / pattern hat8
            if "four" in m:
                plan.actions.append(PlanAction(tool="apply_drum_pattern", args={"pattern": "four_on_the_floor", "bars": 1, "base_bar": 1}))
            elif "back" in m:
                plan.actions.append(PlanAction(tool="apply_drum_pattern", args={"pattern": "backbeat", "bars": 1, "base_bar": 1}))
            elif "hat" in m:
                plan.actions.append(PlanAction(tool="apply_drum_pattern", args={"pattern": "hihat_8th", "bars": 1, "base_bar": 1}))
            return plan


        # default fallback: do nothing
        plan.assumptions.append("No recognized command. No actions executed.")
        return plan
    

