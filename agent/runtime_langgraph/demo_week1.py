from __future__ import annotations

import json

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

