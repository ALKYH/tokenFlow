# Agent Runtime LangGraph

## 目录
- `dsl.py`: 工作流 DSL v1、最小模板、前端导出归一化
- `compiler.py`: `DSL -> IR -> ExecutablePlan` 编译链
- `graph_types.py`: Graph/Execution 结构、状态和策略类型
- `harness.py`: Harness 抽象、执行上下文、trace/span 结构
- `executors.py`: 内建节点执行器与 Harness 节点适配
- `registry.py`: `node_type -> executor` 注册表
- `engine.py`: 状态机执行引擎
- `state.py`: 运行态构造、trace/span 和错误结构
- `checkpoint.py`: checkpoint / retry / resume 支撑

## 当前能力

### P0 已交付
- 工作流 DSL v1
- IR 中间层
- `DSL -> IR -> ExecutablePlan` 编译链
- 编译期默认值填充、拓扑校验、循环依赖检测
- 编译结果摘要签名 `fingerprint`
- 前端导出格式归一化入口
- 最小模板 `workflow_dsl_template()`

### P1 已交付
- 条件分支
- 动态路由
- 并行分叉 / Join 合流
- 子图调用
- 节点级 retry / timeout
- 工作流级 cancel
- checkpoint / retry / resume
- Harness 抽象
- `ToolExecutor / SkillExecutor / AgentExecutor / FunctionCallExecutor`
- `run_context / node_context / agent_context / shared_memory / scratchpad`
- `trace + span` 双层可观测结构

## Harness 设计

### 统一执行接口
Harness 抽象位于 `harness.py`，核心对象包括：
- `ExecutionContext`
- `ExecutionRequest`
- `ExecutionResult`
- `TraceSpan`
- `ToolExecutor`
- `SkillExecutor`
- `AgentExecutor`
- `FunctionCallExecutor`
- `RuntimeBackendExecutor`

### 默认后端
内建 Harness 注册表默认支持：
- `runtime`: 保留 Python snippet 执行路径
- `tool`: 工具调用适配
- `skill`: 技能调用适配
- `agent`: Agent 调用适配
- `function`: 函数调用适配

当前 `tool/skill/agent/function` 是可运行骨架，便于后续替换成真实后端。

## 使用方式

### 1. 最小模板
```python
from agent.runtime_langgraph.dsl import workflow_dsl_template

workflow = workflow_dsl_template("wf_template")
```

### 2. Harness 节点
```python
from agent.runtime_langgraph.dsl import WorkflowDSL, WorkflowEdgeDSL, WorkflowNodeDSL

workflow = WorkflowDSL(
    version="1.0",
    workflow_id="wf_harness",
    nodes=[
        WorkflowNodeDSL(node_id="const_1", node_type="const", config={"value": "hello"}),
        WorkflowNodeDSL(
            node_id="tool_1",
            node_type="tool",
            config={
                "backend": "tool",
                "payload": {"tool_name": "search", "value": "query"},
            },
        ),
    ],
    edges=[WorkflowEdgeDSL(source="const_1", target="tool_1")],
    entrypoint="const_1",
)
```

### 3. Runtime 后端仍可用
```python
WorkflowNodeDSL(
    node_id="runtime_1",
    node_type="tool",
    config={
        "backend": "runtime",
        "source": (
            "def __tokenflow_node_entry(value, context, resources):\n"
            "    return str(value).upper()\n"
        ),
        "function_name": "__tokenflow_node_entry",
    },
)
```

## 运行结果字段
- `result`: 当前链路最终输出
- `context.node_outputs`: 每个节点的输出快照
- `context.logs`: `print` 节点聚合日志
- `context.backend_results`: Harness 后端输出摘要
- `trace`: 节点生命周期轨迹
- `spans`: Harness 调用层 span 记录
- `error`: 结构化错误
- `workflow_id`: 当前工作流标识
- `workflow_version`: 当前工作流 DSL 版本
- `execution.status`: 工作流执行状态
- `execution.node_statuses`: 节点状态表
- `execution.retry_counts`: 节点重试次数
- `execution.checkpoints`: 已保存的 checkpoint 摘要

## 测试
```bash
python -m pytest agent/tests/test_runtime_langgraph.py -q -p no:cacheprovider
```
