import asyncio

from agent.runtime_langgraph.compiler import compile_workflow_dsl
from agent.runtime_langgraph.dsl import WorkflowDSL, WorkflowEdgeDSL, WorkflowNodeDSL
from agent.runtime_langgraph.engine import LangGraphRuntime

from backend.app.services.runtime_observability_service import (
    cancel_workflow_execution,
    get_workflow_timeline,
    persist_runtime_state,
    register_runtime_execution,
    retry_workflow_node,
)


def _build_workflow() -> WorkflowDSL:
    return WorkflowDSL(
        version="1.0",
        workflow_id="wf_observe",
        nodes=[
            WorkflowNodeDSL(node_id="const_1", node_type="const", config={"value": "hello"}),
            WorkflowNodeDSL(node_id="print_1", node_type="print", config={"prefix": "[obs] "}),
        ],
        edges=[WorkflowEdgeDSL(source="const_1", target="print_1")],
        entrypoint="const_1",
    )


def test_runtime_observability_persists_timeline_and_cancel():
    async def scenario():
        runtime = LangGraphRuntime()
        workflow = _build_workflow()
        plan = compile_workflow_dsl(workflow)
        state = runtime.run_workflow(
            workflow,
            initial_state={"input": {}, "context": {}, "resources": {}, "trace": [], "spans": []},
        )
        execution_id = state["execution"]["execution_id"]
        register_runtime_execution(execution_id, runtime, plan, state)
        await persist_runtime_state(state)

        timeline = await get_workflow_timeline(execution_id)
        assert timeline is not None
        assert timeline.execution_id == execution_id
        assert timeline.status == "success"
        assert any(item.node_id == "const_1" for item in timeline.node_runs)

        cancelled = await cancel_workflow_execution(execution_id)
        assert cancelled["execution"]["cancel_requested"] is True

    asyncio.run(scenario())


def test_runtime_observability_retry_registered_execution():
    async def scenario():
        runtime = LangGraphRuntime()
        source = (
            "def __tokenflow_node_entry(value, context, resources):\n"
            "    if context.get('fail_once'):\n"
            "        context['fail_once'] = False\n"
            "        raise RuntimeError('boom')\n"
            "    return value\n"
        )
        workflow = WorkflowDSL(
            version="1.0",
            workflow_id="wf_retry_observe",
            nodes=[
                WorkflowNodeDSL(node_id="const_1", node_type="const", config={"value": "hello"}),
                WorkflowNodeDSL(
                    node_id="py_1",
                    node_type="python_snippet",
                    config={"source": source, "function_name": "__tokenflow_node_entry"},
                ),
            ],
            edges=[WorkflowEdgeDSL(source="const_1", target="py_1")],
            entrypoint="const_1",
        )
        plan = compile_workflow_dsl(workflow)
        state = runtime.run_workflow(
            workflow,
            initial_state={"input": {}, "context": {"fail_once": True}, "resources": {}, "trace": [], "spans": []},
        )
        execution_id = state["execution"]["execution_id"]
        register_runtime_execution(execution_id, runtime, plan, state)
        await persist_runtime_state(state)

        retried = await retry_workflow_node(execution_id, "py_1")
        assert retried["execution"]["status"] == "success"

    asyncio.run(scenario())
