# TokenFlow Agent 扩充指引

Date: 2026-05-09
Status: Active

本文件面向后续 agent，规定在本仓库内如何继续扩充文档、测试、报告与治理材料。

## 1. 入口文件

后续 agent 在扩充治理相关内容前，必须先读取：
- `docs/governance/engineering-governance.md`
- `docs/implementation-plan.md`
- 当前目标领域的最近一份报告或 ADR

如果任务涉及中文文档写入，还必须遵守仓库根部的约束：中文文本按 UTF-8 输出。

## 2. 扩充顺序

### 文档扩充
1. 判断属于 `adr / reports / governance / templates` 哪一类
2. 复用同类最近文件的结构
3. 保持标题、日期、状态字段一致
4. 补到 `docs/implementation-plan.md` 的对应任务状态

### 测试扩充
1. 先补最小单元或服务测试
2. 再考虑是否需要脚本级验证
3. 失败路径优先级不低于成功路径
4. 如引入新队列/调度行为，必须补健康或清理路径测试

### 报告扩充
1. 先有实现与验证结果
2. 再写报告
3. 报告必须引用实际输出文件或测试文件

## 3. 禁止事项
- 不要新建与 `docs/reports/` 平行的“report”、“analysis”、“notes”目录
- 不要把机器输出 JSON 直接放进 `docs/`
- 不要新增未说明用途的命名模式
- 不要写只描述“做了什么”但没有“验证结果”的报告
- 不要用本地默认编码写中文文件

## 4. 推荐模板来源
- ADR 模板：`docs/templates/adr-template.md`
- 报告模板：`docs/templates/report-template.md`
- 测试矩阵模板：`docs/templates/test-matrix-template.md`

## 5. 更新完成后的最小检查
- 编码检查：

```bash
python scripts/week7_encoding_audit.py --output output/week7/encoding-audit-report.json
```

- 相关测试：
  运行与你新增内容直接相关的最小测试集

- 计划同步：
  更新 `docs/implementation-plan.md` 中对应条目状态
