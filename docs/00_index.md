# PPT Agent 开发文档索引

> 建筑设计方案 PPT 专用 AI Agent — 详细开发文档

---

## 文档目录

| 编号 | 文档名 | 内容摘要 |
|------|-------|---------|
| 01 | [项目结构与环境规范](./01_project_structure.md) | 目录结构、依赖版本、环境变量、Docker Compose |
| 02 | [数据库表设计](./02_database_schema.md) | 所有核心表 DDL、索引策略、触发器 |
| 03 | [Pydantic 数据模型](./03_pydantic_models.md) | 所有 Schema 定义、枚举、LangGraph 状态模型 |
| 04 | [FastAPI 接口定义](./04_api_definition.md) | 全部 API 端点、请求/响应格式、路由注册 |
| 05 | [Agent 状态流转](./05_agent_state_machine.md) | 项目级/页面级状态机、LangGraph 节点定义、路由逻辑 |
| 06 | [异步任务队列](./06_async_tasks.md) | Celery 配置、队列划分、资产/渲染/导出任务实现 |
| 07 | [Prompt 模板](./07_prompt_templates.md) | 所有 Agent 的 System Prompt、版本管理约定 |
| 08 | [LLM 调用规范](./08_llm_spec.md) | 模型选型、统一调用封装、限流、成本估算 |
| 09 | [Tool 接口规范](./09_tool_spec.md) | 所有 Tool 的函数签名、输入输出 Schema、超时设置 |
| 10 | [HTML 模板规范](./10_html_templates.md) | 设计 Token、各模板 HTML/CSS、SlideSpec→HTML 映射 |
| 11 | [审查规则表](./11_review_rules.md) | 三层审查规则、规则实现代码、修复执行器 |
| 12 | [错误码与异常](./12_error_codes.md) | 错误码枚举、异常类定义、全局处理器、前端约定 |
| 13 | [外部 API 集成](./13_external_apis.md) | 高德地图、Anthropic、OSS、pgvector、Playwright |
| 14 | [案例库数据规范](./14_case_library.md) | 字段定义、标签体系、图片规范、Embedding 生成、种子脚本 |
| 15 | [测试策略](./15_testing_strategy.md) | 单元/集成/E2E 测试、Fixture、CI 配置、覆盖率目标 |

---

## 推荐阅读顺序

**新成员上手：**
```
01（目录结构）→ 03（数据模型）→ 05（状态机）→ 04（API）→ 07（Prompt）
```

**开始编码前：**
```
02（建表）→ 09（Tool规范）→ 08（LLM规范）→ 06（异步任务）
```

**质量保障：**
```
11（审查规则）→ 12（错误码）→ 15（测试）
```

---

## 开发阶段对应文档

| Phase | 核心文档 |
|-------|---------|
| Phase 1 基础闭环 | 01 / 02 / 03 / 04 / 05 / 07 / 09 / 10 |
| Phase 2 质量增强 | 06 / 11 / 12 / 15 |
| Phase 3 高级能力 | 08（多模态部分）/ 13（Playwright/PPTX）|
---

## 新增文档

- [20 素材包驱动的 PPT 生成流程改造开发文档](./20_material_package_integration.md)

- [21 素材包改造实施附录](./21_material_package_implementation_appendix.md)

- [21 material package implementation appendix](./21_material_package_implementation_appendix.md)

- [22 session handoff 2026-04-05](./22_session_handoff_20260405.md)

- [26 素材包到 PDF 全流程说明](./26_pipeline_flow_overview.md)
