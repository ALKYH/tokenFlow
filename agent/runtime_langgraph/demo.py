from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)
    from agent.runtime_langgraph.engine import LangGraphRuntime, build_minimal_chain_plan
else:
    from .engine import LangGraphRuntime, build_minimal_chain_plan


def run_demo() -> None:
    runtime = LangGraphRuntime()
    plan = build_minimal_chain_plan()
    result = runtime.run(
        plan,
        initial_state={
            "input": {},
            "context": {},
            "resources": {},
            "result": None,
            "error": None,
            "trace": [],
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_demo()
