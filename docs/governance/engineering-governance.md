# TokenFlow 工程治理规范

Date: 2026-05-09
Status: Active
Scope: `docs/`, `backend/`, `agent/`, `scripts/`, `.github/`

## 1. 目标

本规范用于统一 TokenFlow 仓库中的：
- 编码与文本安全
- 文档结构
- 测试组织
- 报告输出
- ADR 决策记录
- 后续 agent 扩充方式

原则：
- 优先复用现有目录与范式，不新增平行体系
- 文档、脚本、报告默认使用 UTF-8
- 机器产物与人工文档分离
- 所有新增治理项都应可被后续 agent 自动读取、补充、延续

## 2. 编码规范

### 2.1 文本编码
- 所有文本文件默认使用 `UTF-8`
- 换行默认使用 `LF`
- Markdown 允许保留行尾空格关闭，其他文本默认移除尾随空格
- 中文内容必须显式按 UTF-8 写入，避免本地默认编码导致乱码

### 2.2 仓库基线
- `.editorconfig` 是编辑器基线
- `.gitattributes` 是行尾与二进制基线
- `scripts/week7_encoding_audit.py` 是编码审计基线
- `.github/workflows/encoding-check.yml` 是 CI 守护基线

### 2.3 审计要求
- 新增或重写跨目录文档后，应运行：

```bash
python scripts/week7_encoding_audit.py --output output/week7/encoding-audit-report.json
```

- 需要强制校验时，运行：

```bash
python scripts/week7_encoding_audit.py --fail-on-issues
```

## 3. 文档范式

### 3.1 目录职责
- `docs/implementation-plan.md`
  作为路线图与任务清单，维护阶段目标和完成状态
- `docs/adr/`
  记录关键技术决策，只写“为什么这样做”
- `docs/reports/`
  记录阶段性交付、验证结果、复盘总结
- `docs/governance/`
  记录仓库级规范、模板、扩充指引
- `docs/templates/`
  存放后续 agent 可复用的模板

### 3.2 文档命名
- ADR: `0001-topic-name.md`
- 报告: `weekN-topic-name.md` 或 `YYYYMMDD-topic-name.md`
- 治理文档: `area-name.md`
- 模板: `template-name.md`

### 3.3 文档最小结构

#### ADR 最小结构
- Title
- Status
- Date
- Context
- Decision
- Consequences
- Follow-ups

#### 报告最小结构
- Title
- Date
- Scope
- Implemented Items
- Validation
- Risks / Residual Gaps

#### 治理文档最小结构
- Title
- Status
- Scope
- Rules
- Required Inputs / Outputs
- Agent Expansion Guidance

## 4. 测试范式

### 4.1 测试层次
- 单元测试：验证单一模块行为
- 服务测试：验证服务级逻辑与错误路径
- 端到端脚本：验证多模块链路与输出产物

### 4.2 目录约定
- `agent/tests/`
  存放 runtime / DSL / 编译 / 执行语义测试
- `backend/tests/`
  存放 API / service / queue / scheduler / security 测试
- `scripts/`
  存放需要产出报告文件的验证脚本

### 4.3 测试文件命名
- 单元或服务测试：`test_<area>.py`
- 周次或阶段回归：`test_<area>_weekN_<topic>.py`

### 4.4 测试编写规则
- 一个测试只验证一个清晰行为
- 测试名必须表达结果，而不是动作
- 错误路径必须显式断言错误类型或错误码
- 有队列、调度、超时逻辑时，优先用短延时和可控事件，不依赖长 sleep
- 涉及中文输出的断言，保持 UTF-8 文本直接比较，不做本地编码转换

## 5. 报告范式

### 5.1 报告类型
- 治理报告：如编码治理、CI 治理
- 能力报告：如 runtime、RAG、queue、scheduler
- 验证报告：如 e2e、兼容性、回归测试

### 5.2 报告与产物分离
- 报告正文进入 `docs/reports/`
- 机器输出进入 `output/<topic>/`
- 报告中必须引用机器产物路径

### 5.3 机器产物要求
- 默认使用 JSON
- 必须使用 `ensure_ascii=False`
- 必须显式写入 `encoding="utf-8"`
- 顶层至少包含：
  - `generated_at`
  - `summary`
  - `status` 或等价状态字段

## 6. Agent 扩充指引

### 6.1 优先级
后续 agent 在新增文档或报告时，必须按以下优先级复用：
1. 现有目录
2. 现有命名模式
3. 现有模板
4. 现有脚本产物结构

### 6.2 新增文档时必须做的事
- 选择正确目录：`adr/`, `reports/`, `governance/`, `templates/`
- 保持 UTF-8
- 沿用本规范中的最小结构
- 如涉及验证结果，补充机器产物路径
- 如涉及新规范，回链到本文件

### 6.3 新增测试时必须做的事
- 放在 `agent/tests/` 或 `backend/tests/`
- 命名遵循 `test_<area>.py`
- 对应新增能力至少包含成功路径和失败路径
- 如涉及调度/队列/重试，优先补 service 级测试

### 6.4 新增报告时必须做的事
- 写明日期、范围、实施项、验证、残余风险
- 如果存在脚本输出，必须在报告中引用 `output/...`
- 如果报告推动了治理变更，应同步更新 `docs/implementation-plan.md`

## 7. 当前已落地项
- `.editorconfig`
- `.gitattributes`
- `scripts/week7_encoding_audit.py`
- `.github/workflows/encoding-check.yml`
- `docs/reports/week7-encoding-governance.md`

## 8. 待后续持续扩充
- 测试矩阵总表
- 执行引擎时序图规范
- 队列 / 锁 / 重试设计文档模板
- Router / RAG 设计说明模板
