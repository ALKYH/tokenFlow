# TokenFlow 接手 Agent 开发说明

## 1. 项目定位与技术栈
- 项目是一个前后端分离的工作流/插件管理系统原型。
- 产品目标：构建面向 Agent 的本地化低代码 SaaS。用户可从云端灵感/模板导入到 DAG 编辑器，编排后交给本地执行端（Harness）执行，再通过路由与市场模块分发结果。
- 前端：`Vue 3 + Vite + TypeScript + Naive UI + UnoCSS`（目录：`web/`）。
- 后端：`FastAPI + SQLAlchemy(Async) + PostgreSQL`（目录：`backend/`）。
- 第三端（执行端）：`Python Runtime Service + GGUF 本地模型推理`（模型目录：`models/`）。
- 模型技术选型：`llama-cpp-python`（本地加载 GGUF）+ FastAPI runtime API；可选配 `Redis` 队列做削峰与异步任务。
- 架构分层：
  - 编排层：前端 DAG 建模，支持社区模板与自定义节点。
  - 执行层：本地 Harness 执行 Python 节点、工具节点、模型节点。
  - 调度层：路由规则 + 队列分发（可扩展 Prompt 驱动和规则匹配）。
  - 管理层：超时、并发、模块锁、任务状态与可观测信息。
- 后端启动时会自动建表并执行种子数据初始化（`backend/app/seed.py`）。

## 2. 接手后的第一步（5 分钟内）
1. 先看这几个文件：`docker-compose.yml`、`backend/app/main.py`、`web/src/service/api/tokenflow.ts`。
2. 明确两套前端接口通道：
   - `web/src/service/request/*`：模板后台接口（默认走 mock / 代理）。
   - `web/src/service/api/tokenflow.ts`：直连 TokenFlow 后端（默认 `http://localhost:8000`）。
3. 明确当前开发端口：
   - 前端 Vite：`9527`
   - 后端 API：`8000`
   - PostgreSQL：`5432`

## 3. 本地启动（推荐流程）
1. 启动数据库与后端（根目录）：
   - `docker compose up -d postgres backend --build`
2. 启动前端（`web/` 目录）：
   - `pnpm install`
   - `pnpm dev`
3. 联调时检查 CORS：
   - 后端 `FRONTEND_ORIGINS` 建议包含 `http://localhost:9527`。
4. 前端可通过环境变量覆盖后端地址：
   - `VITE_TOKENFLOW_API_URL=http://localhost:8000`

## 4. 目录职责速查
- `backend/app/routers/`：API 路由层（auth/profile/plugins/workspaces/routing/inbox）。
- `backend/app/services/`：业务服务层（鉴权、密钥、token 等）。
- `backend/app/models/`：ORM 模型定义。
- `backend/app/schemas/`：请求/响应 schema。
- `backend/app/db/session.py`：数据库连接、建表、运行时 schema 补丁。
- `web/src/views/`：页面。
- `web/src/service/api/tokenflow.ts`：TokenFlow 业务 API 封装。
- `web/src/service/request/`：模板通用 request 封装（code/msg/data 协议）。
- `models/`：本地推理模型目录（仅允许白名单模型名访问）。

## 4.1 第三端执行协议（固定）
1. 前端执行模式：
   - `pyodide`：浏览器本地执行（兼容旧流程）。
   - `runtime`：调用后端 `/api/runtime/execute-node`（第三端）。
2. 节点映射规则（前端 -> Runtime）：
   - `execution_mode`：优先 `python-module`；无 module 时可走 `builtin`/`auto`。
   - `module.source`：由节点代码片段包装成可调用函数（默认 `__tokenflow_node_entry`）。
   - `module.function_name`：必须与 `source` 中函数一致。
   - `module.args/kwargs`：显式参数；节点连线输入放在 `inputs`。
   - `resources`：节点挂载文件转为 `text` 或 `base64_data` 传输。
   - `env`：由编辑器环境变量表序列化传入。
3. Runtime API：
   - `GET /api/runtime/health`
   - `GET /api/runtime/capabilities`
   - `POST /api/runtime/execute-node`
4. 本地模型访问策略：
   - 仅允许 `models/` 目录下白名单文件名（如 `*.gguf`）。
   - 禁止路径穿越（不能带 `/`、`\\`、`..`）。
5. 安全与资源限制：
   - 源码长度、资源大小、输出大小上限。
   - 超时控制 + 并发限制。
   - 限制危险调用（如 `eval/exec/open/__import__`）与非白名单 import。
   - 环境变量与错误信息脱敏（`api_key/token/secret/password`）。

## 4.2 执行协议 Schema（Week 1 冻结版）
1. 协议版本：
   - 当前版本：`protocol_version = "1.0.0"`。
   - 兼容策略：
     - `major` 变更（如 `2.x.x`）：允许不兼容字段调整，前后端需要同步升级。
     - `minor` 变更（如 `1.1.x`）：仅新增可选字段，旧客户端可继续使用。
     - `patch` 变更（如 `1.0.1`）：仅修正文档与实现细节，不改字段语义。
   - 后端收到不支持的 `major` 版本时，返回 `status=failed` + `error.code=UNSUPPORTED_PROTOCOL_VERSION`。

2. 请求 Schema（`NodeExecutionRequest`）：
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "NodeExecutionRequest",
  "type": "object",
  "required": ["protocol_version", "node_id", "node_type", "execution_mode", "module"],
  "properties": {
    "protocol_version": { "type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$" },
    "request_id": { "type": "string", "minLength": 1, "maxLength": 120 },
    "node_id": { "type": "string", "minLength": 1, "maxLength": 120 },
    "node_type": { "type": "string", "minLength": 1, "maxLength": 80 },
    "execution_mode": { "type": "string", "enum": ["python-module", "builtin", "auto"] },
    "module": {
      "type": "object",
      "required": ["source", "function_name"],
      "properties": {
        "source": { "type": "string", "minLength": 1, "maxLength": 200000 },
        "function_name": { "type": "string", "minLength": 1, "maxLength": 120 },
        "args": { "type": "array", "default": [] },
        "kwargs": { "type": "object", "default": {} }
      },
      "additionalProperties": false
    },
    "inputs": { "type": "array", "default": [] },
    "resources": {
      "type": "array",
      "default": [],
      "items": {
        "type": "object",
        "required": ["name", "kind"],
        "properties": {
          "name": { "type": "string", "minLength": 1, "maxLength": 255 },
          "kind": { "type": "string", "enum": ["text", "base64_data"] },
          "text": { "type": "string" },
          "base64_data": { "type": "string" },
          "mime_type": { "type": "string" }
        },
        "additionalProperties": false
      }
    },
    "env": {
      "type": "object",
      "default": {},
      "additionalProperties": { "type": "string" }
    },
    "runtime": {
      "type": "object",
      "properties": {
        "timeout_ms": { "type": "integer", "minimum": 1, "maximum": 120000 },
        "max_output_bytes": { "type": "integer", "minimum": 1024, "maximum": 5242880 }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

3. 响应 Schema（`NodeExecutionResponse`）：
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "NodeExecutionResponse",
  "type": "object",
  "required": ["protocol_version", "status", "output", "logs", "error", "metrics", "trace"],
  "properties": {
    "protocol_version": { "type": "string" },
    "request_id": { "type": "string" },
    "status": { "type": "string", "enum": ["ok", "failed"] },
    "output": {},
    "logs": { "type": "array", "items": { "type": "string" } },
    "error": {
      "oneOf": [
        { "type": "null" },
        {
          "type": "object",
          "required": ["code", "message"],
          "properties": {
            "code": { "type": "string" },
            "message": { "type": "string" },
            "detail": {}
          },
          "additionalProperties": true
        }
      ]
    },
    "metrics": {
      "type": "object",
      "required": ["duration_ms"],
      "properties": {
        "duration_ms": { "type": "number" },
        "cpu_ms": { "type": "number" },
        "memory_peak_mb": { "type": "number" }
      },
      "additionalProperties": true
    },
    "trace": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["node_id", "phase", "status"],
        "properties": {
          "node_id": { "type": "string" },
          "phase": { "type": "string" },
          "status": { "type": "string" },
          "detail": { "type": "string" }
        },
        "additionalProperties": true
      }
    }
  },
  "additionalProperties": false
}
```

4. 错误对象 Schema（`ExecutionError`）：
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ExecutionError",
  "type": "object",
  "required": ["code", "message"],
  "properties": {
    "code": {
      "type": "string",
      "enum": [
        "INVALID_REQUEST",
        "UNSUPPORTED_PROTOCOL_VERSION",
        "UNSAFE_CODE",
        "TIMEOUT",
        "RUNTIME_EXCEPTION",
        "MODEL_NOT_ALLOWED"
      ]
    },
    "message": { "type": "string", "minLength": 1 },
    "detail": {},
    "traceback": { "type": "string" }
  },
  "additionalProperties": true
}
```

5. 协议示例：
   - 示例 A（最小执行）：
```json
{
  "protocol_version": "1.0.0",
  "request_id": "req_min_001",
  "node_id": "python_snippet_1",
  "node_type": "python_snippet",
  "execution_mode": "python-module",
  "module": {
    "source": "def __tokenflow_node_entry(value, context, resources):\n    return str(value).upper()",
    "function_name": "__tokenflow_node_entry",
    "args": ["hello week1"],
    "kwargs": {}
  },
  "inputs": [],
  "resources": [],
  "env": {}
}
```
   - 示例 B（含资源注入）：
```json
{
  "protocol_version": "1.0.0",
  "request_id": "req_res_001",
  "node_id": "resource_reader_1",
  "node_type": "python_snippet",
  "execution_mode": "python-module",
  "module": {
    "source": "def __tokenflow_node_entry(value, context, resources):\n    first = resources[0][\"text\"] if resources else \"\"\n    return {\"chars\": len(first)}",
    "function_name": "__tokenflow_node_entry"
  },
  "inputs": [],
  "resources": [
    {
      "name": "doc.txt",
      "kind": "text",
      "text": "TokenFlow runtime resource sample"
    }
  ],
  "env": {
    "WORKSPACE_ID": "ws_local_001"
  }
}
```
   - 示例 C（错误回传）：
```json
{
  "protocol_version": "1.0.0",
  "request_id": "req_err_001",
  "status": "failed",
  "output": null,
  "logs": [],
  "error": {
    "code": "RUNTIME_EXCEPTION",
    "message": "division by zero",
    "detail": {
      "node_id": "python_snippet_1",
      "phase": "run"
    }
  },
  "metrics": {
    "duration_ms": 14.3
  },
  "trace": [
    { "node_id": "python_snippet_1", "phase": "prepare", "status": "ok" },
    { "node_id": "python_snippet_1", "phase": "run", "status": "error", "detail": "ZeroDivisionError" }
  ]
}
```

## 5. 开发规则（接手 Agent 必遵守）
1. 不要破坏兼容登录接口：
   - 后端同时保留 `/api/auth/*` 与 `/auth/*`（前端兼容接口依赖 `/auth/*`）。
2. 改数据库结构时优先“增量兼容”：
   - 参考 `ensure_runtime_schema()` 的做法，避免直接做破坏性变更。
3. 新增后端接口时：
   - 先补 schema，再写 router/service，再补前端 `tokenflow.ts` 调用。
4. 改前端业务页时：
   - 优先复用已有 API 封装，不要把 `fetch` 直接散落到 `views`。
5. 涉及密钥字段时：
   - 必须走 `encrypt_secret/decrypt_secret`，不要明文落库。

## 6. 中文防乱码规范（重点）
1. 所有文本文件统一 `UTF-8`（建议 `UTF-8 without BOM`）+ `LF`。
2. 在 PowerShell 中处理中文文件前，先确保终端编码为 UTF-8。
3. 读写文件时显式指定 UTF-8，避免系统默认编码（GBK/ANSI）污染。
4. 提交前抽查含中文文件，尤其是：
   - `web/src/locales/langs/zh-cn.ts`
   - `.md` 文档
   - `.json/.ts/.vue` 中的中文文案
5. 当前仓库已有历史乱码痕迹（例如 `zh-cn.ts`），未被明确要求时不要顺手大规模重编码；若要修复，请单独提交、单独验证。

## 7. 提交前最小验证清单
1. 前端（`web/`）：
   - `pnpm typecheck`
   - `pnpm lint`
   - `pnpm fmt`
   - `pnpm build`
2. 后端（`backend/`）：
   - 服务可启动，`GET /health` 返回 `{"ok": true}`
   - 核心流程至少手测一遍：登录/获取个人信息/工作区读写
3. 联调：
   - 前端关键页面可打开：`/home`、`/marketplace`、`/routing`、`/inbox`、`/blank`

## 8. 交接输出模板（给下一位 Agent）
- 本次改动范围：文件列表 + 模块说明
- API/数据结构变化：是否兼容、是否需要补环境变量
- 手动验证结果：通过项/未覆盖项
- 风险与后续建议：最多 3 条，明确优先级
