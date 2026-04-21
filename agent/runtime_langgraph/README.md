# Agent LangGraph Week 1 Skeleton

## 目录
- `graph_types.py`: `GraphState` / `GraphNode` / `GraphPlan` 定义
- `executors.py`: 节点生命周期实现（`prepare -> run -> postprocess -> on_error`）
- `registry.py`: `node_type` 到执行器的注册机制
- `engine.py`: LangGraph 编排与运行器
- `demo.py`: 最小链路 `const -> python_snippet -> print` 演示
- `demo_week1.py`: 兼容入口（转发到 `demo.py`）

## 使用指南
### 1) 安装依赖
```bash
pip install -r agent/requirements.txt
```

### 2) 运行最小链路 Demo
```bash
python -m agent.runtime_langgraph.demo
python -m agent.runtime_langgraph.demo_week1
```

### 3) 运行测试
```bash
python -m pytest agent/tests/test_runtime_langgraph.py -q -p no:cacheprovider
```

### 4) 输出结果怎么看
- `result`: 当前链路最终输出值。
- `context.node_outputs`: 每个节点的输出快照（按 `node_id` 索引）。
- `context.logs`: `print` 节点聚合的日志。
- `trace`: 节点生命周期轨迹（`prepare/run/postprocess/on_error`）。
- `error`: 结构化错误（包含 `node_id/phase/error_type/message/traceback`）。

## 调试指南
### 1) 先看 `trace` 再看 `error`
- 若某节点失败，后续节点会记录 `prepare + skipped`，`detail=previous node failed`。
- 失败节点会记录 `on_error + error`，优先定位该节点。

### 2) 常用单测命令
```bash
# 全量
python -m pytest agent/tests/test_runtime_langgraph.py -q -p no:cacheprovider

# 仅看异常分支
python -m pytest agent/tests/test_runtime_langgraph.py -k error -q -p no:cacheprovider

# 仅看并发隔离
python -m pytest agent/tests/test_runtime_langgraph.py -k parallel -q -p no:cacheprovider
```

### 3) 常见报错与定位
- `python_snippet 节点缺少 module.source`:
  检查 `GraphNode.config["source"]` 是否为空。
- `module.function_name 未在 source 中定义`:
  检查 `config["function_name"]` 和源码函数名一致。
- `python_snippet 含有不允许的调用`:
  命中黑名单（如 `open(` / `exec(` / `eval(` / `import os`）。
- `未注册的 node_type`:
  该类型未在 `create_default_registry()` 注册。
- `GraphPlan 存在重复 node_id` 或 `边引用了不存在节点`:
  先检查 `nodes`、`edges` 的一致性。

### 4) 最小自定义调试示例
```python
from agent.runtime_langgraph.engine import LangGraphRuntime
from agent.runtime_langgraph.types import GraphNode, GraphPlan

plan = GraphPlan(
    nodes=[
        GraphNode(node_id="const_1", node_type="const", config={"value": "hello"}),
        GraphNode(
            node_id="py_1",
            node_type="python_snippet",
            config={
                "source": "def __tokenflow_node_entry(value, context, resources):\n    return str(value).upper()",
                "function_name": "__tokenflow_node_entry",
            },
        ),
        GraphNode(node_id="print_1", node_type="print", config={"prefix": "[dbg] "}),
    ],
    edges=[("const_1", "py_1"), ("py_1", "print_1")],
    entrypoint="const_1",
)

runtime = LangGraphRuntime()
state = runtime.run(plan, initial_state={"input": {}, "context": {}, "resources": {}, "trace": []})
print(state["result"])
print(state["trace"])
```

## 扩展指南（新增节点类型）
1. 在 `executors.py` 新增执行器类（继承 `BaseNodeExecutor`，实现 `run`）。
2. 在 `registry.py` 的 `create_default_registry()` 注册新 `node_type`。
3. 在 `agent/tests/test_runtime_langgraph.py` 增加成功/失败/并发用例。
4. 用上面的最小示例先跑通，再接入完整 DAG。
