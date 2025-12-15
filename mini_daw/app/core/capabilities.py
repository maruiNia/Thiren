"""
capabilities.py

LLM이 사용할 수 있는 tool 목록과 args 스펙을 "단일 소스"로 관리.
- 프롬프트에도 이걸 넣고
- API로도 노출해서 UI/테스트에서 확인 가능하게 함
"""

CAPABILITIES = {
    "toggle_drum": {
        "desc": "Toggle drum hit at a specific tick (exists->delete, not exists->create).",
        "args": {
            "track_id": "int (default 1)",
            "start_tick": "int (0..total_ticks)",
            "drum": "'kick'|'snare'|'hihat'",
            "velocity": "float 0..1 (optional)"
        },
        "examples": [
            {"tool": "toggle_drum", "args": {"track_id": 1, "start_tick": 0, "drum": "kick"}}
        ],
    },
    "apply_pattern_four": {
        "desc": "Apply four-on-the-floor kick pattern across bars.",
        "args": {
            "track_id": "int (default 1)",
            "drum": "'kick'|'snare'|'hihat' (default kick)",
            "velocity": "float 0..1",
            "overwrite": "bool"
        },
    },
    "place_note": {
        "desc": "Place a melodic note event.",
        "args": {
            "track_id": "int (2=bass,3=pad,4=lead)",
            "start": "str 'bar:step' or int tick",
            "duration_tick": "int (>=1)",
            "pitch": "str like 'C4','D#3','A1'",
            "velocity": "float 0..1 (optional)",
            "sample_id": "str (optional, if omitted uses track default)"
        },
    },
    "move_event": {
        "desc": "Move an event by delta ticks (uses references).",
        "args": {
            "event_ref": "'last_selected'|'last_created'",
            "delta_tick": "int"
        },
    },
    "delete_event": {
        "desc": "Delete an event by reference.",
        "args": {
            "event_ref": "'last_selected'|'last_created'"
        },
    },
    "set_pitch": {
        "desc": "Set pitch for a melodic event by reference.",
        "args": {
            "event_ref": "'last_selected'|'last_created'",
            "pitch": "str like 'C4','D#3','A1'"
        },
    },
    "transpose_event": {
        "desc": "Transpose selected/created melodic event by semitones.",
        "args": {
            "event_ref": "'last_selected'|'last_created'",
            "semitone": "int"
        },
    },
    "undo": {
        "desc": "Undo previous edits.",
        "args": {"steps": "int (optional, default 1)"},
    },
}
