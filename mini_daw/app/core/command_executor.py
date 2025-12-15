from app.core.command_schema import Command
from app.core.state import ProjectState


def apply_command(state: ProjectState, cmd: Command):
    if cmd.type == "set_bpm":
        state.meta.bpm = int(cmd.value)

    elif cmd.type == "set_bars":
        state.meta.bars = int(cmd.value)
        state.recompute_meta()

    elif cmd.type == "set_grid":
        state.meta.grid = cmd.value

    elif cmd.type == "set_track_volume":
        tr = _find_track(state, cmd.track)
        if tr:
            tr.volume = float(cmd.value)

    elif cmd.type == "set_track_pan":
        tr = _find_track(state, cmd.track)
        if tr:
            tr.pan = float(cmd.value)

    elif cmd.type == "mute_track":
        tr = _find_track(state, cmd.track)
        if tr:
            tr.mute = True

    elif cmd.type == "solo_track":
        tr = _find_track(state, cmd.track)
        if tr:
            tr.solo = True


def _find_track(state: ProjectState, key: str):
    if not key:
        return None
    for t in state.tracks:
        if t.name.lower().startswith(key):
            return t
    return None
