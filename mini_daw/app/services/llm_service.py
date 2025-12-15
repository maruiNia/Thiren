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
import torch

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
            device_map="cuda",
            torch_dtype=torch.float16,
        )
        self._pipe = pipeline(
            "text-generation",
            model=mdl,
            tokenizer=tok,
            max_new_tokens=512,
            do_sample=False,
            return_full_text=False,
        )

    def make_plan(self, message: str, state_hint: dict | None = None) -> Plan:
        # 룰 우선
        p = rule_first_plan(message)
        if p:
            return p

        self._lazy_load()

        state_hint = state_hint or {}
        sys = """
            You are a music DAW command planner.

            OUTPUT FORMAT (STRICT):
            - Return ONLY a single valid JSON object. No extra text. No markdown. No code fences.
            - The JSON object MUST have exactly these keys: "summary", "actions", "assumptions".
            - "assumptions" MUST be a JSON array ([]) even if empty.
            - "actions" MUST be a JSON array of objects, each object has:
            - "tool": one of the allowed tools
            - "args": a JSON object of arguments for that tool

            ALLOWED TOOLS:
            1) toggle_drum(args: {track_id:int=1, start_tick:int, drum:"kick"|"snare"|"hihat", velocity?:float})
            2) apply_pattern_four(args: {track_id:int=1, drum:"kick"|"snare"|"hihat", velocity:float, overwrite:bool})
            3) place_note(args: {track_id:int, start:"bar:step" OR int, duration_tick:int>=1, pitch:"C4"|"D#3"|"A1", velocity?:float, sample_id?:str})
            4) move_event(args: {event_ref:"last_selected"|"last_created", delta_tick:int})
            5) delete_event(args: {event_ref:"last_selected"|"last_created"})
            6) set_pitch(args: {event_ref:"last_selected"|"last_created", pitch:"C4"|"D#3"|"A1"})
            7) transpose_event(args: {event_ref:"last_selected"|"last_created", semitone:int})
            8) undo(args: {steps:int})   # steps default 1

            CRITICAL RULES:
            - If the user asks for undo/cancel/go back (e.g., "undo", "되돌려줘", "취소"), you MUST output an undo action.
            - If the user asks for a drum pattern "pattern four" / "four on the floor" / "4 on the floor", you MUST output apply_pattern_four.
            - If the user asks to "move" something but does not specify which event, use event_ref="last_selected" if possible, otherwise "last_created".
            - If the user asks to "delete/remove" something but does not specify which event, use event_ref="last_selected" if possible, otherwise "last_created".
            - If the user requests a musical action (place/move/delete/set pitch/transpose/toggle drum/pattern/undo), you MUST output at least ONE action.
            - Only output empty actions [] if the message is purely conversational and contains no actionable intent.

            TIME/TICK CONVENTIONS:
            - start can be "bar:step" where bar starts at 1.
            - step starts at 1 and corresponds to 1/16 ticks (step 1..16 in a bar).
            - Example: "1:1" is the first 16th note of bar 1.
            - "2:5" means bar 2, step 5 (beat 2 start if ticks_per_beat=4).
            - If user specifies "1박/2박/3박/4박" in 4/4, you can map it to steps:
            - 1박 -> step 1
            - 2박 -> step 5
            - 3박 -> step 9
            - 4박 -> step 13

            EXAMPLES (FOLLOW THESE PATTERNS EXACTLY):

            UNDO EXAMPLES:
            User: "undo"
            {"summary":"undo last action","actions":[{"tool":"undo","args":{"steps":1}}],"assumptions":[]}

            User: "되돌려줘"
            {"summary":"undo last action","actions":[{"tool":"undo","args":{"steps":1}}],"assumptions":[]}

            PATTERN EXAMPLES:
            User: "pattern four"
            {"summary":"apply four-on-the-floor kick pattern","actions":[{"tool":"apply_pattern_four","args":{"track_id":1,"drum":"kick","velocity":0.95,"overwrite":false}}],"assumptions":[]}

            User: "4 on the floor"
            {"summary":"apply four-on-the-floor kick pattern","actions":[{"tool":"apply_pattern_four","args":{"track_id":1,"drum":"kick","velocity":0.95,"overwrite":false}}],"assumptions":[]}

            TOGGLE DRUM EXAMPLES:
            User: "kick at bar 1 beat 1"
            {"summary":"toggle kick at bar 1 beat 1","actions":[{"tool":"toggle_drum","args":{"track_id":1,"start_tick":0,"drum":"kick","velocity":0.95}}],"assumptions":["Assume 4/4, ticks_per_bar=16, beat 1 start_tick=0"]}

            User: "스네어 2박에 찍어"
            {"summary":"toggle snare at beat 2","actions":[{"tool":"toggle_drum","args":{"track_id":1,"start_tick":4,"drum":"snare","velocity":0.9}}],"assumptions":["Assume 4/4, beat 2 start_tick=4"]}

            User: "하이햇 8분으로 1마디에 깔아"
            {"summary":"place hihat on 8th notes for bar 1","actions":[
            {"tool":"toggle_drum","args":{"track_id":1,"start_tick":0,"drum":"hihat","velocity":0.7}},
            {"tool":"toggle_drum","args":{"track_id":1,"start_tick":2,"drum":"hihat","velocity":0.7}},
            {"tool":"toggle_drum","args":{"track_id":1,"start_tick":4,"drum":"hihat","velocity":0.7}},
            {"tool":"toggle_drum","args":{"track_id":1,"start_tick":6,"drum":"hihat","velocity":0.7}},
            {"tool":"toggle_drum","args":{"track_id":1,"start_tick":8,"drum":"hihat","velocity":0.7}},
            {"tool":"toggle_drum","args":{"track_id":1,"start_tick":10,"drum":"hihat","velocity":0.7}},
            {"tool":"toggle_drum","args":{"track_id":1,"start_tick":12,"drum":"hihat","velocity":0.7}},
            {"tool":"toggle_drum","args":{"track_id":1,"start_tick":14,"drum":"hihat","velocity":0.7}}
            ],"assumptions":["Assume ticks_per_bar=16, 8th note step=2 ticks"]}

            PLACE NOTE EXAMPLES:
            User: "베이스 A1을 1마디 1박에 넣어"
            {"summary":"place bass note A1 at bar 1 beat 1","actions":[{"tool":"place_note","args":{"track_id":2,"start":"1:1","duration_tick":4,"pitch":"A1","velocity":0.85}}],"assumptions":[]}

            User: "리드 C4를 2마디 3박에 짧게"
            {"summary":"place lead note C4 at bar 2 beat 3 short","actions":[{"tool":"place_note","args":{"track_id":4,"start":"2:9","duration_tick":2,"pitch":"C4","velocity":0.9}}],"assumptions":["Assume '짧게' means duration_tick=2"]}

            MOVE/DELETE EXAMPLES:
            User: "방금 만든 거 오른쪽으로 한 박"
            {"summary":"move last created event by one beat","actions":[{"tool":"move_event","args":{"event_ref":"last_created","delta_tick":4}}],"assumptions":["Assume one beat = 4 ticks"]}

            User: "선택한 거 왼쪽으로 두 칸"
            {"summary":"move selected event left by 2 ticks","actions":[{"tool":"move_event","args":{"event_ref":"last_selected","delta_tick":-2}}],"assumptions":[]}

            User: "선택한 거 삭제"
            {"summary":"delete selected event","actions":[{"tool":"delete_event","args":{"event_ref":"last_selected"}}],"assumptions":[]}

            PITCH EDIT EXAMPLES:
            User: "선택한 노트 피치 D#3로"
            {"summary":"set pitch of selected melodic event","actions":[{"tool":"set_pitch","args":{"event_ref":"last_selected","pitch":"D#3"}}],"assumptions":[]}

            User: "선택한 노트 두 반음 올려"
            {"summary":"transpose selected melodic event up 2 semitones","actions":[{"tool":"transpose_event","args":{"event_ref":"last_selected","semitone":2}}],"assumptions":[]}

            NOW, given the user's message, output ONLY the JSON plan.
            """

        # sys = (
        #     "You are a music DAW command planner.\n"
        #     "Return ONLY valid JSON for a plan with keys: summary, actions, assumptions.\n"
        #     "No markdown. No ``` fences. JSON only.\n"
        #     "assumptions MUST be a JSON array [].\n"
        #     "actions MUST be a JSON array of objects {tool, args}.\n\n"
        #     "Allowed tools:\n"
        #     "- toggle_drum(args: {track_id:int=1, start_tick:int, drum:'kick'|'snare'|'hihat'})\n"
        #     "- apply_pattern_four(args: {track_id:int=1, drum:'kick'|'snare'|'hihat', velocity:float, overwrite:bool})\n"
        #     "- place_note(args: {track_id:int, start:'bar:step' or int, duration_tick:int, pitch:str})\n"
        #     "- move_event(args: {event_ref:'last_selected'|'last_created', delta_tick:int})\n"
        #     "- delete_event(args: {event_ref:'last_selected'|'last_created'})\n"
        #     "- set_pitch(args: {event_ref:'last_selected', pitch:str})\n"
        #     "- transpose_event(args: {event_ref:'last_selected', semitone:int})\n"
        #     "- undo(args: {steps:int})\n\n"
        #     "If the user asks for a drum pattern 'pattern four', use apply_pattern_four.\n"
        #     "If user asks to go back/undo (e.g., 'undo', '되돌려줘', '취소'), you MUST output an undo action.\n\n"
        #     "UNDO EXAMPLE:\n"
        #     "{"
        #     "\"summary\":\"undo last action\","
        #     "\"actions\":[{\"tool\":\"undo\",\"args\":{\"steps\":1}}],"
        #     "\"assumptions\":[]"
        #     "}\n"
        # )

        user = (
            f"User command: {message}\n"
            f"State hint: {json.dumps(state_hint, ensure_ascii=False)}\n"
            "Return JSON only. Do not use markdown fences.\n"
        )

        out = self._pipe(f"{sys}\n{user}")[0]["generated_text"]

        print("\n===== [LLM RAW OUTPUT] =====")
        print(out)
        print("===== [END RAW OUTPUT] =====\n")

        plan_json = self._extract_json(out)

        print("===== [EXTRACTED PLAN_JSON] =====")
        print(plan_json)
        print("===== [END PLAN_JSON] =====\n")

        if plan_json is None:
            return Plan(summary="LLM parse failed", actions=[], assumptions=["parse_failed"])

        # ✅ 여기서 보정(repair) 추가
        plan_json = self._repair_plan_json(plan_json, message)

        print("===== [REPAIRED PLAN_JSON] =====")
        print(plan_json)
        print("===== [END REPAIRED PLAN_JSON] =====\n")

        try:
            return Plan.model_validate(plan_json)
        except Exception as e:
            print("!!!!! [PLAN VALIDATION ERROR] !!!!!")
            print(e)
            return Plan(summary="LLM schema invalid", actions=[], assumptions=["schema_invalid"])

        
    def _repair_plan_json(self, plan_json: dict, message: str) -> dict:
        # 1) assumptions: dict -> list 로 보정
        if isinstance(plan_json.get("assumptions"), dict):
            plan_json["assumptions"] = []

        # 2) actions 누락/None -> 빈 리스트
        if "actions" not in plan_json or plan_json["actions"] is None:
            plan_json["actions"] = []

        # 3) summary가 str이 아니면 보정
        if not isinstance(plan_json.get("summary"), str):
            plan_json["summary"] = str(plan_json.get("summary", ""))

        # 4) undo 의도인데 actions가 비어있으면 자동 생성
        msg = message.strip().lower()
        summ = plan_json["summary"].lower()

        undo_intent = (
            "undo" in summ
            or "되돌" in msg
            or "뒤로" in msg
            or "취소" in msg
            or "되감" in msg
        )

        if undo_intent and len(plan_json["actions"]) == 0:
            # "2번" 같은 횟수 파싱(없으면 1)
            import re
            steps = 1
            m = re.search(r"(\d+)\s*번", msg)
            if m:
                steps = int(m.group(1))
            elif "두" in msg:
                steps = 2
            elif "세" in msg:
                steps = 3

            plan_json["actions"] = [{"tool": "undo", "args": {"steps": steps}}]
            plan_json.setdefault("assumptions", [])
            plan_json["assumptions"].append("auto_filled_undo_action")

        return plan_json


    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        # 1) ```json ... ``` 코드펜스 우선 추출
        m = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            try:
                return json.loads(candidate)
            except Exception:
                pass

        # 2) 일반 { ... } 블록 추출(가장 바깥 JSON)
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None

        candidate = m.group(0).strip()
        try:
            return json.loads(candidate)
        except Exception:
            return None
    # def _extract_json(text: str) -> Optional[dict]:
    #     # 가장 단순한 JSON 객체 추출
    #     start = text.find("{")
    #     end = text.rfind("}")
    #     if start == -1 or end == -1 or end <= start:
    #         return None
    #     chunk = text[start : end + 1]
    #     try:
    #         return json.loads(chunk)
    #     except Exception:
    #         return None


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
    

