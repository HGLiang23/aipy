# ADR-0004: 异步工作流执行（ModelGateway + Celery）

- 状态：Accepted
- 日期：2026-09-25

## 背景

ADR-0003 让 `rerun` / `resume` 能同步翻转 `content_run.status`，但翻完状态后**没有任何东西真正执行**——
看板上的「运行中」永远不会变成「已完成」。`apps/worker` 当时没有任何 task，`export` / `collect` /
`assign` 也因缺少副作用后端而返回 400。生成环节需要一个可替换的 LLM 抽象（本地/CI 无需密钥即可跑通），
以及把执行从请求线程卸到 Celery 的机制。

## 决策

### 1. `ModelGateway` 端口 + 桩适配器

- `src/aipy/modules/llm/__init__.py`：`ModelGateway` 协议（`complete(request) -> ModelResult`），
  `StubModelGateway` 返回确定性演示文本、**零网络调用**。
- `select_gateway(settings)`：local/test 返回桩；staging/production 必须配置真实 provider，
  否则显式 `RuntimeError`（避免把演示文案泄露给真实用户）。
- 真实 provider 实现该协议后在此处接入即可，**不引入运行时网络依赖**。

### 2. Celery 任务 `content.run.execute`

- `apps/worker/tasks.py`：`run_content_workflow(run_code, tenant_id, actor_id)`。
- 流程：读状态 → 若缺失/终态则 `not_found` / `skipped_terminal` → 置 RUNNING → 经 gateway 生成 →
  置 COMPLETED；异常则置 FAILED（返回 `failed:<Exc>`，**不让 broker 崩溃**）。
- 每次状态回写都开独立租户会话并提交，复用 state_machine 的 `content_status_label` 写 `status_label` / `tone`，
  与 API 路径展示一致。引擎按进程懒加载复用。

### 3. API 在 (re)start 后入队

- `apps/api/routes/workflow_runs.py`：`rerun` / `resume` 经 `apply_content_action` 同步翻到 RUNNING 后，
  调用 `enqueue_content_run` 把任务交给 Celery。用户点击立即看到「运行中」，真正完成在 worker 上。
- `enqueue_content_run` 对 broker 不可达（如本地无 Redis）**吞掉并告警**，而非把成功的转换变成 500。

## 已知限制

- 状态竞态未处理：入队后若用户在 worker 执行前又 `pause`，worker 仍会把它跑到 COMPLETED。当前为最小闭环，
  后续可在任务开头校验 `status == RUNNING` 再继续。
- `export` / `collect` / `assign` 仍为 `unsupported_action`（400）：需要导出存储、检索源、成员目录等副作用后端，
  不在本次范围内，待对应服务落地后再接 Celery 任务。
- 真实 LLM provider 未实现；桩仅验证链路与状态回写。
