# ADR-0005: 真实模型接入与 export/collect/assign 动作闭环

- 状态：已采纳（Accepted）
- 日期：2026-09-25
- 取代：无（衔接 ADR-0003 的写动作框架）

## 背景

ADR-0003 之后，写动作只覆盖状态机转换（pause/resume/rerun/cancel、
claim/reassign/submit/approve/reject）。三块动作仍是 400：

- `export` / `collect`（内容任务）——缺导出产物与采集后端；
- `assign`（人工任务）——缺成员目录与分派逻辑；
- 真实 AI 生成——`ModelGateway` 仅为 `StubModelGateway`，跑出来是演示文案。

用户要求「实现全部功能」，并按最小真实实现 + OpenAI 兼容接口的方向落地。

## 决策

### 1. 真实模型：`HttpModelGateway`（OpenAI 兼容）

- `ModelGateway` 新增 `HttpModelGateway`，用 `openai` SDK 的 chat completions
  接口，通吃 OpenAI / DeepSeek / 通义 / 智谱 / 本地 vLLM。
- `select_gateway(settings)`：
  - `settings.llm_configured`（base_url + api_key + model 三者齐备）→ `HttpModelGateway`；
  - 否则 local/test → 回退 `StubModelGateway`（CI / 本地无密钥也能跑）；
  - 否则 staging/production → 显式 `RuntimeError`，避免演示文案泄露到生产。
- 配置项：`AIPY_LLM__BASE_URL` / `AIPY_LLM__API_KEY` / `AIPY_LLM__MODEL` /
  `AIPY_LLM__TIMEOUT`。`openai` 依赖加入 `pyproject`。
- worker 任务 `content.run.execute` 现在把生成正文写回 `content_run.content`。

### 2. 非状态机副作用动作（export / collect / assign）

沿用 ADR-0003 的「写动作 = 状态机 + 乐观锁 + 授权」框架，但新增一类
**副作用动作**：改变资源但不走状态转换。

- `repositories.CONTENT_SIDE_EFFECTS = {export, collect}`、
  `REVIEW_SIDE_EFFECTS = {assign}`。
- `apply_content_action` / `apply_human_task_action` 先判副作用动作，命中则走
  专属分支；否则仍进 `ensure_supported` 状态机路径。
- 副作用动作同样校验 `If-Match`（乐观锁）与 `AuthorizationService` 权限。

### 3. export

- `content_run` 新增 `content`（生成正文）、`exported_at`（导出时间）两列。
- 新增 `content_export` 表（tenant 隔离 + RLS）：每次导出落一条 markdown 成品
  （`format`/`title`/`payload`），并写 `run.exported_at`。
- 当前仅 markdown 源；docx 等二进制格式留作后续（payload 已是结构化文本，
  易扩展）。

### 4. collect

- 新增 `content_run_material` 关联表（tenant 隔离 + RLS + 复合 FK）。
- 动作按 `brand` / `title` 在 `material` 表中 ILIKE 检索，去重后写入关联
  （限 10 条）。素材表无 brand 列，故用标题/摘要包含品牌或任务标题匹配——
  这是最小真实实现，非语义化检索。

### 5. assign + 成员目录

- 新增 `GET /api/v1/organization/members`：返回租户 ACTIVE 成员
  （id / displayName / roleLabel），受 `member:view` 保护。
- `assign` 动作：校验 `assigneeId` 是租户 ACTIVE 成员；写入 `human_task.assignee_id`；
  若任务为 OPEN 则转 CLAIMED。需 `review:assign` 权限。
- 权限补齐：`content:collect`、`review:assign`、`member:view` 加入 EDITOR；
  ADMIN 经 `*EDITOR` 自动继承。

### 6. 前端

- 详情页工作流画布去掉 `mockWorkflowNodes`，改为按真实 `run.status`/`stageLabel`
  渲染时间线（状态驱动，非假数据）；`ContentRunSummary` 新增 `status` 字段。
- `human-tasks` 页拉取成员列表，`assign` 按钮渲染成员下拉 + 确认；
  `use-actions.run` 支持透传 `assigneeId`。
- `export` / `collect` 按钮随 `allowed_actions` 自动出现。

## 已知取舍 / 后续

- `collect` 是字符串匹配，不是语义检索；真实检索源（搜索 API / 向量库）未接。
- `export` 仅 markdown，未做 docx/PDF；未暴露下载端点（仅落库记录）。
- 真实模型需在 staging/production 配 `AIPY_LLM__*`，否则启动即报错（符合预期）。
- 端到端仍需 Postgres + Redis + API + Worker 同时起，本机沙箱无 DB/Redis 未点测。

## 质量门

- `ruff` 全绿、`mypy --strict`（58 文件）全绿、`pytest` 97 passed / 1 skipped。
- 迁移 `20260925_0008` 离线渲染通过；ORM↔alembic 约束名/注释对称差无缺失。
- 前端 `tsc --noEmit` 全绿。
