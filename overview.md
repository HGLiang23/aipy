# 全部功能闭环：真实模型 + export / collect / assign

把剩余三块「只能看不能点」的缺口全部接成真实功能，并让 AI 写文从桩变真模型。

## 交付内容

### 1. 真实 AI 生成（OpenAI 兼容）
- `src/aipy/modules/llm/__init__.py`：`HttpModelGateway`（openai SDK chat completions，通吃 OpenAI/DeepSeek/通义/智谱/本地 vLLM）+ `select_gateway` 三态选择（有配置→真模型 / local·test 无配置→桩 / 其他环境无配置→显式报错）。
- `src/aipy/shared/config.py`：`LlmSettings`（`AIPY_LLM__BASE_URL/API_KEY/MODEL/TIMEOUT`）+ `AppSettings.llm_configured`。
- `apps/worker/tasks.py`：worker 现在把生成正文写回 `content_run.content`。
- `pyproject.toml`：加 `openai` 依赖。

### 2. content_run 加列 + 两张新表
- `content_run.content`（正文）、`content_run.exported_at`（导出时间）。
- `content_export`（导出产物：markdown 源）、`content_run_material`（采集关联），均带 RLS + 注释。
- 迁移 `migrations/versions/20260925_0008_content_export_collect.py`（离线渲染 + ORM 对称差验证通过）。

### 3. export / collect 动作
- `export`：组装 markdown 落 `content_export` 并写 `exported_at`。
- `collect`：按 brand/title 在 `material` 表检索，去重写入 `content_run_material`（限 10 条）。

### 4. assign 动作 + 成员目录
- `apps/api/routes/organization.py`：`GET /api/v1/organization/members`（受 `member:view`）。
- `assign`：校验 assigneeId 是租户 ACTIVE 成员、OPEN→CLAIMED。

### 5. 副作用动作框架（沿用 ADR-0003）
- `CONTENT_SIDE_EFFECTS={export,collect}`、`REVIEW_SIDE_EFFECTS={assign}`；
  `apply_content_action/apply_human_task_action` 先判副作用再走状态机，同样校验 If-Match + 授权。

### 6. 前端
- 详情页画布去掉 `mockWorkflowNodes`，按真实 `run.status`/`stageLabel` 渲染时间线；`ContentRunSummary` 加 `status`。
- human-tasks 页拉成员、`assign` 渲染下拉 + 确认；`use-actions.run` 透传 `assigneeId`。

## 验证结果
- `ruff` 全绿 · `mypy --strict`（58 文件）clean · `pytest` **97 passed / 1 skipped** · 前端 `tsc --noEmit` 0 错。
- 迁移离线渲染通过；ORM↔alembic 约束名/注释对称差无缺失。

## 已知边界（非本次范围）
- `export` 仅 markdown 源，未做 docx/PDF 与下载端点。
- `collect` 是字符串匹配，非语义检索（真实检索源未接）。
- 真实模型需在 staging/prod 配 `AIPY_LLM__*`，否则启动即报错（符合预期）。
- 端到端浏览器点测需起 Postgres + Redis + API + Worker，本机沙箱无 DB/Redis 未真点。

## 下一步可选
1. 接真实 `AIPY_LLM__*`（让系统真写文）。
2. `export` 出 docx/PDF + 下载端点。
3. `collect` 接语义检索（搜索 API / 向量库）。
