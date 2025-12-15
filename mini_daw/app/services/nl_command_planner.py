from app.services.llm_service import GemmaPlanner
from app.core.command_schema import Command

planner = GemmaPlanner()

def parse_with_llm(text: str, state_hint: dict) -> list[Command]:
    plan = planner.make_plan(text, state_hint)
    cmds = []

    for act in plan.actions:
        if act.tool == "set_bpm":
            cmds.append(Command(type="set_bpm", value=act.args.get("bpm")))
        # 필요하면 계속 확장

    return cmds
