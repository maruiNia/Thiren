import re
from typing import Optional
from app.core.command_schema import Command


def parse_rule_command(text: str) -> Optional[Command]:
    t = text.lower().strip()

    # BPM
    m = re.search(r"bpm\s*(\d+)", t)
    if m:
        return Command(type="set_bpm", value=int(m.group(1)))

    # bars
    m = re.search(r"(\d+)\s*마디", t)
    if m:
        return Command(type="set_bars", value=int(m.group(1)))

    # grid
    if "16분" in t:
        return Command(type="set_grid", value="1/16")
    if "8분" in t:
        return Command(type="set_grid", value="1/8")
    if "4분" in t:
        return Command(type="set_grid", value="1/4")

    # track volume
    for tr in ["드럼", "베이스", "패드", "리드"]:
        if tr in t and ("볼륨" in t or "소리" in t):
            if "줄" in t or "낮" in t:
                return Command(type="set_track_volume", track=_map_track(tr), value=0.6)
            if "올" in t or "크" in t:
                return Command(type="set_track_volume", track=_map_track(tr), value=0.9)

    # pan
    if "왼쪽" in t or "좌측" in t:
        return Command(type="set_track_pan", track=_guess_track(t), value=-0.5)
    if "오른쪽" in t or "우측" in t:
        return Command(type="set_track_pan", track=_guess_track(t), value=0.5)

    # mute / solo
    if "뮤트" in t:
        return Command(type="mute_track", track=_guess_track(t), value=True)
    if "솔로" in t:
        return Command(type="solo_track", track=_guess_track(t), value=True)

    return None


def _map_track(korean: str):
    return {
        "드럼": "drums",
        "베이스": "bass",
        "패드": "pad",
        "리드": "lead",
    }.get(korean)


def _guess_track(text: str):
    if "드럼" in text:
        return "drums"
    if "베이스" in text:
        return "bass"
    if "패드" in text:
        return "pad"
    if "리드" in text:
        return "lead"
    return None
