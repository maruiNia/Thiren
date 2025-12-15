from pydantic import BaseModel
from typing import Literal, Optional

CommandType = Literal[
    "set_bpm",
    "set_bars",
    "set_grid",
    "set_track_volume",
    "set_track_pan",
    "mute_track",
    "solo_track",
]

class Command(BaseModel):
    type: CommandType
    track: Optional[Literal["drums", "bass", "pad", "lead"]] = None
    value: Optional[float | int | str] = None
