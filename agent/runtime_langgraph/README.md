# Agent LangGraph Week 1 Skeleton

## 目录
- `types.py`: `GraphState` / `GraphNode` / `GraphPlan` 定义
- `executors.py`: 节点生命周期实现（`prepare -> run -> postprocess -> on_error`）
- `registry.py`: `node_type` 到执行器的注册机制
- `engine.py`: LangGraph 编排与运行器
- `demo_week1.py`: 最小链路 `const -> python_snippet -> print` 演示

## 本地运行
```bash
pip install -r agent/requirements.txt
python -m agent.runtime_langgraph.demo_week1
python -m pytest agent/tests/test_runtime_langgraph.py -q -p no:cacheprovider
```

