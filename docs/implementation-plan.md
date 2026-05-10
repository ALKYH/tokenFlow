# TokenFlow 实施整理与改进计划

## 1. 当前定位与目标差距

### 1.1 当前项目更接近的状态
- 可视化节点编辑器与本地工作台
- 基于 LangGraph 的轻量运行时骨架
- 单节点 Runtime 执行能力
- 初步 RAG 检索与路由能力
- 基础调试、日志与状态展示

### 1.2 目标状态
- 面向 Agent 的本地化工作流编排与执行引擎
- 支持前端可视化 DAG 编排
- 支持 DSL 驱动的工作流建模与执行
- 支持多 Agent 协作任务
- 支持本地高并发、异步解耦、重试恢复、动态路由与模块级可观测性

### 1.3 主要差距
- 缺少正式的工作流 DSL 定义与版本治理
- 缺少 `DSL -> AST/IR -> 状态机执行流` 编译链
- DAG 语义不完整，条件分支、动态路由、并行 Join、子流程尚不完整
- 当前执行抽象更偏“Python 片段执行”，不是完整的 Agent Harness
- 并发控制尚未落到 Redis 队列、分布式锁、背压、多级队列
- Router 还不是“向量召回 + 规则兜底 + TopK 路由决策”的完整形态
- 可观测性还缺少工作流实例、节点实例、恢复点与回放能力
- 仓库内已有中文乱码，需要纳入工程治理

## 2. 实施任务清单

### P0：编排模型与核心主链

#### 2.1 工作流 DSL
- [x] 定义工作流 DSL v1
- [x] 明确 `nodes`、`edges`、`entrypoint`、`conditions`、`router`、`retry`、`timeout`、`subgraph`、`version`
- [x] 约束前端导出格式，避免直接传 UI 临时状态
- [x] 为 DSL 编写示例与最小模板

#### 2.2 DSL 校验与版本治理
- [x] 增加 DSL schema 校验
- [x] 增加非法 DAG 检查
- [x] 增加节点引用、悬空边、重复节点、循环依赖检测
- [x] 设计 DSL 版本号与迁移入口

#### 2.3 AST / IR 中间层
- [x] 设计 `WorkflowIR`
- [x] 设计 `NodeIR`
- [x] 设计 `EdgeIR`
- [x] 设计 `BranchIR`
- [x] 设计 `RetryPolicy`、`TimeoutPolicy`、`RoutePolicy`
- [x] 区分“编辑态结构”和“执行态结构”

#### 2.4 编译链
- [x] 实现 `DSL -> AST/IR`
- [x] 实现 `AST/IR -> ExecutablePlan`
- [x] 编译期完成默认值填充、拓扑校验、分支展开
- [x] 为编译结果增加缓存与摘要签名

### P1：DAG 执行语义补齐

#### 2.5 运行图模型扩展
- [x] 支持条件分支
- [x] 支持动态路由
- [x] 支持并行分叉
- [x] 支持 Join 合流
- [x] 支持子流程 / 子图调用

#### 2.6 状态机执行引擎
- [x] 重构 LangGraph 执行引擎，使其从线性执行升级为状态驱动调度
- [x] 统一节点状态：`pending`、`running`、`success`、`failed`、`timeout`、`retrying`、`skipped`、`cancelled`
- [x] 支持节点级 retry / backoff
- [x] 支持工作流级中断与取消

#### 2.7 checkpoint 与恢复
- [x] 保存 workflow run 中间状态
- [x] 保存 node run 中间状态
- [x] 支持失败节点恢复
- [x] 支持从指定节点重跑

### P1：Harness 与多 Agent 执行抽象

#### 2.8 统一执行接口
- [x] 定义 `ToolExecutor`
- [x] 定义 `SkillExecutor`
- [x] 定义 `AgentExecutor`
- [x] 定义 `FunctionCallExecutor`

#### 2.9 执行后端可插拔
- [x] 将 Runtime 执行能力抽象为一种后端
- [x] 保留 Python snippet 执行路径
- [x] 预留 LLM Agent / ToolChain / 外部服务执行适配层

#### 2.10 多级调用链
- [x] 统一 `LLM -> Tool -> Subtask -> LLM` 调用链模型
- [x] 统一 trace/span 结构
- [x] 支持分层日志、分层错误与分层超时

#### 2.11 上下文隔离
- [x] 区分 `run_context`
- [x] 区分 `node_context`
- [x] 区分 `agent_context`
- [x] 区分 `shared_memory`
- [x] 区分 `scratchpad`
- [x] 防止多任务上下文污染

### P1：并发、流量控制与调度

#### 2.12 Redis 队列底座
- [x] 引入 Redis 作为正式调度队列
- [x] 保留当前服务接口，替换底层实现
- [x] 支持 worker 横向扩展

#### 2.13 多级队列
- [x] 实时任务队列
- [x] 延迟/重试队列
- [x] cron 定时队列
- [x] 死信队列

#### 2.14 分布式锁与幂等
- [x] 基于 `SETNX + TTL` 实现工作流实例锁
- [x] 基于 `SETNX + TTL` 实现节点执行锁
- [x] 防止重复消费
- [x] 防止重复执行

#### 2.15 背压与限流
- [x] 队列长度阈值控制
- [x] worker 并发上限控制
- [x] 节点超时与取消
- [x] 超载降级与拒绝策略

#### 2.16 调度能力
- [x] 支持 cron 触发工作流
- [x] 支持任务超时中断
- [x] 支持僵尸任务清理

### P2：Router + RAG 动态路径选择

#### 2.17 路由模型升级
- [x] 从关键词匹配升级为“向量召回 + 规则兜底”
- [x] 路由结果返回 TopK 候选路径
- [x] 支持路由到 `workflow / agent / toolchain`

#### 2.18 RAG 与 Router 解耦
- [x] RAG 负责召回候选上下文
- [x] Router 负责路径选择
- [x] 解耦检索、评分、路由决策逻辑

#### 2.19 路由可解释性
- [x] 输出命中规则
- [x] 输出召回分数
- [x] 输出最终选择原因

### P2：可观测性、重试与恢复

#### 2.20 运行实例模型
- [x] 设计 `workflow_runs`
- [x] 设计 `node_runs`
- [x] 设计 `agent_runs`
- [x] 设计 `retry_records`

#### 2.21 观测指标
- [x] 记录节点耗时
- [x] 记录队列等待耗时
- [x] 记录重试次数
- [x] 记录超时率、失败率、命中率

#### 2.22 调试面板升级
- [x] 展示工作流执行时间线
- [x] 展示节点状态流转
- [x] 支持失败节点重放
- [x] 支持查看输入/输出摘要

#### 2.23 恢复能力
- [x] 支持人工重试
- [x] 支持断点恢复
- [x] 支持取消运行与资源清理

### P2：工程治理

#### 2.24 编码治理
- [x] 统一 UTF-8 编码
- [x] 修复已有乱码文件
- [x] 增加编码检查与 CI 守护

#### 2.25 测试矩阵
- [x] DSL 编译测试
- [x] 执行状态机测试
- [x] 并发与幂等测试
- [x] 路由选择测试
- [x] 故障恢复测试

#### 2.26 文档补齐
- [x] DSL 设计说明
- [ ] 执行引擎时序图
- [x] 队列/锁/重试设计文档
- [ ] Router/RAG 设计说明

## 3. 性能提升方向

### 3.1 执行链路性能
- 为编译后的工作流计划增加缓存，避免重复构图
- 对内建轻量节点走进程内快速路径，减少 Runtime 序列化与网络开销
- 将“解释执行”和“编译执行”分层，开发期强调易调试，运行期强调吞吐

### 3.2 并发性能
- 将当前进程内并发逐步升级为 worker 化架构
- 按节点类型拆分 worker 池
- 将 CPU 型、I/O 型、LLM 型、RAG 型任务分流
- 避免重任务阻塞轻任务

### 3.3 RAG 性能
- 对向量化、写库、召回做批处理
- 对高频 query 做短 TTL 缓存
- 对 TopK 候选路径做命中缓存
- 将召回、rerank、路由评分拆为独立可优化阶段

### 3.4 状态存储性能
- 运行主表只保存摘要字段
- 输入/输出/详细日志拆到明细表
- 避免大字段拖慢状态查询

### 3.5 前端 DAG 编辑器性能
- 降低大图下的深度响应式成本
- 对节点、边、hover 状态做局部更新
- 将边路径与布局计算做增量化
- 为大图场景预留虚拟化或分层渲染方案

## 4. 额外可用的重构思路

### 4.1 目录分层重构
建议逐步拆分为：

```text
agent/runtime_langgraph/
  dsl/
  compiler/
  engine/
  executors/
  state/
  observability/

backend/app/services/
  workflow_service.py
  scheduler_service.py
  queue_service.py
  lock_service.py
  router_service.py
  rag_service.py
```

目标：
- 把执行引擎与业务接口服务分离
- 把编译逻辑与运行逻辑分离
- 降低模块耦合

### 4.2 统一状态模型
- 前端执行状态、后端运行状态、路由状态统一为一套枚举
- 统一事件名称与 trace/span 结构
- 避免前后端状态语义不一致

### 4.3 执行器注册机制升级
- 让节点注册从 demo 级 factory 升级为插件式注册
- 一个节点类型至少包含：
  - spec
  - input/output schema
  - executor factory
  - retry policy
  - observability hooks

### 4.4 引入事件总线
- 将关键运行事件统一发成事件流
- 便于接 UI、日志、告警、审计与指标平台

### 4.5 前后端契约先行
- 在技术栈演进前，先冻结 DSL、Run API、Observability API 契约
- 保证 React / Vue 或多端演进时不影响执行主链

### 4.6 解释执行与编译执行双模式
- 调试模式使用解释执行
- 正式运行模式使用编译执行
- 兼顾开发效率与运行性能

## 5. 推荐排期

### 阶段一
- DSL
- IR
- 编译链
- 基础状态机执行

### 阶段二
- Redis 队列 / 锁 / 背压
- 多 Agent Harness
- checkpoint / retry / resume

### 阶段三
- Router + RAG 动态路由
- 可观测性
- 性能优化
- 前端编辑器收敛

## 6. 建议的近期产出顺序

### 第一批
- 工作流 DSL v1
- IR 设计
- `DSL -> ExecutablePlan` 编译链
- 基础执行状态机

### 第二批
- Redis 队列
- 分布式锁
- worker 调度
- checkpoint / retry / resume

### 第三批
- Agent Harness
- Router + RAG 路由升级
- 运行实例与调试面板升级

## 7. 备注
- 当前仓库内部分中文文件已有乱码，后续文档、日志、节点描述与前后端传输都应统一采用 UTF-8。
- 本文档偏“实施路线图”，适合作为后续拆 issue、排迭代、补 ADR 的上层入口文档。
