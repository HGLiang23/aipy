# ADR-0003: 写动作、状态字段与乐观锁闭环

- 状态：Accepted
- 日期：2026-09-25

## 背景

看板之前只有三个 GET 接口，`etag` / `row_version` / `allowed_actions` 已就位却没有任何写路径：
按钮是装饰，乐观锁没有用武之地。`docs/02` 第 8 节要求「所有转换 API 必须携带 `expected_version`」，
但表里只有中文 `status_label`，没有机器可读状态可以作为转换的事实源。

## 决策

### 1. 状态成为事实源（迁移 0007）

- `content_run.status`：`DRAFT / RUNNING / WAITING_HUMAN / PAUSED / FAILED / COMPLETED / CANCELLED`，带 check 约束。
- `human_task.status`：`OPEN / CLAIMED / COMPLETED / CANCELLED / EXPIRED`；新增 `decision`、
  `assignee_id`、`lease_expires_at`。
- `status_label` / `tone` 降级为展示字段，由状态机在转换时同步写入，前端契约不变。
- 存量行按 `status_label`（以及 `owner = '已分配给你'`）回填。

### 2. 状态机是纯模块

`aipy/modules/content/state_machine.py` 只做「动作 + 当前状态 → 新状态 + 展示字段」，
不碰数据库，因此整张转换矩阵可以无库单测。转换表遵循 `docs/02` 4.2 / 8.1：

| 对象 | 动作 | 允许起始状态 | 目标 |
|---|---|---|---|
| content_run | pause | RUNNING, WAITING_HUMAN | PAUSED |
| content_run | resume | PAUSED | RUNNING |
| content_run | rerun | FAILED, COMPLETED | RUNNING |
| content_run | cancel | 非终态 | CANCELLED |
| human_task | claim | OPEN | CLAIMED（写 assignee + 2 小时租约） |
| human_task | reassign | OPEN, CLAIMED | OPEN |
| human_task | submit / approve / reject | OPEN, CLAIMED | COMPLETED（写 decision） |

### 3. 错误码分明

| 场景 | 状态码 | code |
|---|---|---|
| 缺 `If-Match` | 428 | `precondition_required` |
| `If-Match` 版本落后 | 412 | `version_conflict` |
| `If-Match` 格式非法 | 400 | `invalid_precondition` |
| 动作不在转换表（export/collect 等需要异步副作用） | 400 | `unsupported_action` |
| 当前状态不允许该动作 | 409 | `illegal_transition` |
| 授权拒绝 | 403 | 服务返回的拒绝原因（`permission_missing` / `separation_of_duties` / …） |
| 并发落库时版本已被改 | 409 | `version_conflict` |

`ActionError` 携带 `code`，`main.py` 的 HTTPException 处理器支持 dict detail，
因此 `ProblemDetails.code` 能把这个 code 透给前端。

### 4. 授权上下文暂不带 workflow_state

`AuthorizationService._workflow_state_allowed` 的语义是：某权限若没有配置状态规则，
则资源**不得**携带 `workflow_state`（否则拒绝）。当前没有任何策略源填充
`workflow_state_policies`，写接口若传状态会导致「按钮显示可执行、点下去 403」。
因此写接口与列表接口保持一致，暂不传该字段，**状态合法性由状态机守卫**；
等 `workflow_state_policies` 有真实来源后再启用。

## 影响

- 前端 `HumanTaskSummary` 新增 `statusLabel`（mock 数据与 seed 已同步）。
- `api-client.ts` 新增 `runContentAction` / `runHumanTaskAction`，自动带 `If-Match`。

### 5. 按钮由行级 `allowed_actions` 渲染（前端接线）

页面不再用 `PermissionGate` + 会话级权限去「猜」能做什么，而是直接渲染每行
`allowed_actions`——它本身就是授权引擎按「角色 + 租户/成员状态 + 数据范围 + SoD」算出来的，
因此**列表说能点，接口就一定允许点**。

- `web/lib/use-actions.ts`：`useResourceAction` 负责调用、把服务端返回的新行回填进列表，
  并把 `ProblemDetails.code` 映射成中文提示（冲突 / 权限 / 状态非法 / 未接入）。
- `web/lib/use-api.ts`：`useApiList` 补 `reload()`（reloadToken 触发重取）与
  `replaceRow()`（按 id 就地替换，避免整表刷新）；加载失败时透出服务端 detail。
- `web/components/row-actions.tsx`：`view` 被过滤（行链接即查看），pending 时整行禁用，
  `reassign` 暂以「退回待领取」呈现（无成员选择器，不传 assigneeId 即释放回池）。
- `ui.tsx` 新增 `InlineNotice`（conflict / error 两色），冲突场景附带「重新加载」按钮。

补全的权限缺口：`content:resume` / `content:cancel` 此前不在角色目录与
`CANDIDATE_ACTIONS` 里，导致 **暂停后永远无法恢复**；现已加入 editor / admin。
已有租户需重跑 `seed_dev.py` 补齐 `role_permission`（seed 的 `missing` 判定是幂等的）。

## 后续

- `export` / `collect` / `assign` 需要 Celery 任务与副作用，暂不支持（返回 400 而非静默）。
- 租约到期回收、EXPIRED 状态迁移需要定时对账任务。
- 状态级授权（`workflow_state_policies`）接入 RBAC 表。
