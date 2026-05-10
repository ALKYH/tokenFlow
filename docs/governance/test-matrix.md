# TokenFlow 测试矩阵

Date: 2026-05-09
Status: Active

## Scope
- 记录当前仓库内已经落地的核心测试入口
- 为后续 agent 补测试提供统一索引

## Matrix

| Area | Layer | Scenario | Automated | File / Script |
| --- | --- | --- | --- | --- |
| Runtime LangGraph | unit/service | DSL 编译、状态机、分支、路由、子图、retry、resume、Harness | yes | `agent/tests/test_runtime_langgraph.py` |
| Runtime Queue | service | memory/inline backend、retry、duplicate reject、zombie cleanup noop | yes | `backend/tests/test_runtime_queue_service.py` |
| Routing Queue | service | memory/inline backend、error propagation、queue full、zombie cleanup noop | yes | `backend/tests/test_routing_queue_service.py` |
| Scheduler | service | delayed job、cron-like job、cancel | yes | `backend/tests/test_scheduler_service.py` |
| Runtime E2E | e2e | runtime chain compatibility | yes | `backend/tests/test_runtime_week5_e2e.py`, `scripts/week5_runtime_e2e.py` |
| RAG | service/eval | retrieval, ingest, eval report | yes | `backend/tests/test_rag_service.py`, `scripts/week6_rag_eval.py` |
| Encoding Governance | governance | UTF-8 audit and mojibake detection | yes | `scripts/week7_encoding_audit.py` |

## Coverage Notes
- 当前已覆盖 P0、P1 主链的核心实现路径。
- 队列的 Redis 真正联通验证尚未纳入自动化矩阵。
- Router/RAG 的高阶解释性与容量行为仍需后续补测。

## Follow-ups
- 增补 Redis backend 集成测试
- 增补 scheduler 与队列联动测试
- 增补 Router TopK / explainability 测试
- 增补工程治理模板使用示例
