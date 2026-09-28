# AIPY 代码评审：功能真实性与可用性核查

- 日期：2026-09-25
- 范围：`apps/`、`src/aipy/`、`migrations/`、`web/`、`tests/`、`docs/`
- 结论摘要：**核心执行/审批链路是真的，但产品侧只有"看板 + 对已有数据做动作"可用；
  没有创建/编辑/上传/管理类接口，前端仍有一批装饰性按钮和硬编码数字；发现 2 个真实缺陷。**

---

## 1. 本次实际执行的验证

| 验证项 | 命令 | 结果 |
| --- | --- | --- |
| 单元/集成测试 | `.venv/bin/python -m pytest -q` | **97 passed, 1 skipped**（skip = RLS 集成测试缺 DB URL） |
| 静态检查 | `ruff check .` / `mypy` | 全绿 / 58 文件 strict clean |
| 前端类型 | `web: tsc --noEmit` | 0 错 |
| 路由真实性 | `create_app().openapi()` | 共 **15** 条路由（清单见 §4） |
| 缺陷复现 | `TestClient` 打 `/api/v1/auth/logout` | 204 但 **0 条 `Set-Cookie`**（见 §3.1） |
| 最小复现 | 自建 FastAPI 对照（返回 model vs 返回 Response） | 确认是 FastAPI 语义，非环境问题 |
| 就绪探针 | `GET /health/ready`（无 DB/无配置） | 返回 `200 {"status":"ready","checks":{}}` |

**未能执行的验证（重要）**：本机无 PostgreSQL / Redis / Docker，`pgserver` 无 arm64+py3.13 wheel，
仓库根目录无 `.env`（远端 `120.26.123.108:7891` 端口可连通但无凭据）。
因此**所有落库路径未经本机实测**——登录、五个写动作、`export/collect/assign`、worker 回写正文，
只有 `.github/workflows/ci.yml`（postgres16 + redis7 service）覆盖。这是本次评审最大的证据缺口。

---

## 2. 结论：哪些功能是"真的"

| 能力 | 落点 | 真实性 |
| --- | --- | --- |
| 登录 / 刷新轮换 / 撤销 / 登录锁定 | `routes/auth.py`、`identity/infrastructure/*`（PyJWT + Argon2 + 单次性 refresh + Redis/内存双实现） | 真实 |
| 租户 RLS | 8 个迁移全表 `FORCE ROW LEVEL SECURITY`，`tenant_session_scope` 设 `app.tenant_id` | 真实（仅 CI 验证） |
| RBAC 授权接线 | `SqlAuthorizationPolicyRepository` 读 `membership_role→role→role_permission` 取并集，无角色回退 `job_title`；默认拒绝 + 职责分离 + 数据范围 | 真实 |
| 看板按钮 | `_allowed_actions` 逐行实时计算，不再读存储列 | 真实 |
| 状态机 | `content/state_machine.py` 纯函数转换表 + 展示标签映射 | 真实（27 例单测） |
| 写动作 + 乐观锁 | `pause/resume/rerun/cancel`、`claim/reassign/submit/approve/reject`，`If-Match` → 428/412/409，`StaleDataError` → 409 | 真实 |
| 副作用动作 | `export` 落 `content_export` + 写 `exported_at`；`collect` 落 `content_run_material`；`assign` 写 `assignee_id` 且 OPEN→CLAIMED | 真实（逻辑层） |
| 异步生成 | Celery `content.run.execute`，写入 `content_run.content`；`HttpModelGateway`（OpenAI 兼容）接通，local/test 回退 Stub，staging/prod 无配置显式报错 | 真实（逻辑层） |
| 前端数据流 | 所有页面走真 API；`mock-data.ts` 已无人 import | 真实 |

已复现的质量门（ADR-0005 声称的 ruff / mypy / pytest / tsc）与实测数字完全一致，宣称是诚实的。

---

## 3. 真实缺陷（建议修）

### 3.1 P0 — 登出不清除 Cookie

`apps/api/routes/auth.py:161-179`：

```python
def logout(response: Response, ...) -> Response:
    ...
    _clear_auth_cookies(response)          # 写到了注入的 response 上
    return Response(status_code=204)       # 但返回的是新对象，注入 response 被丢弃
```

FastAPI 只在返回非 `Response` 值时才会合并注入 `response` 的 Set-Cookie；
直接返回 `Response(...)` 会整体替换。实测：

| 请求 | 结果 |
| --- | --- |
| `POST /api/v1/auth/logout`（带两个旧 cookie） | `204`，`set-cookie: []` |
| 对照：返回 pydantic model 的同构 handler | `set-cookie: ['k=v; Path=/; SameSite=lax']` |

后果：浏览器保留旧 `access_token` / `refresh_token`。服务端撤销仍在生效，所以
**local/test（`InMemoryTokenRevocations`）下进程一重启，被"登出"的旧 Cookie 就又变成有效凭证**，
直到 15 分钟自然过期。

修法（二选一）：`return Response(status_code=204, headers=response.headers)`，
或把 `_clear_auth_cookies` 的 delete 写到新建的那个 Response 上。

### 3.2 P0 — 前端从不调用登出接口

`web/components/app-shell.tsx:47`：

```tsx
<div className="sidebar-footer"><Link className="nav-link" href="/login"><LogOut size={18}/><span>退出演示</span></Link></div>
```

全仓 grep：`apiClient.logout` 只有定义（`web/lib/api-client.ts:64`），**没有任何调用点**。
用户点"退出"只是跳到登录页，Cookie 与令牌都还在，回退到 `/app` 依然可用。
叠加 §3.1，登出功能实际不可用。

### 3.3 P1 — 就绪探针不检测任何依赖

`apps/api/main.py:45` `readiness_checks or {}`，无人注册探针；`routes/health.py:29` 对空 dict 求
`all([]) == True`。实测无 DB 时 `/health/ready` 仍返回 `200 ready`。
用它做 K8s readinessProbe 会把没有数据库的实例判为可用。`README.md:40` 已承认是待办，但仍是可观测性缺口。

### 3.4 P1 — `assign` 没有状态守卫

`apps/api/repositories.py:711-745` 的 `_apply_assign` 不检查 `row.status`：

```python
row.assignee_id = assignee_id
if row.status == "OPEN":
    row.status = "CLAIMED"
row.decision = None
row.lease_expires_at = now + CLAIM_LEASE
```

对一个 **COMPLETED / CANCELLED** 的任务调 `assign`，会清掉 `decision`、重设租约，
但状态仍是 `COMPLETED`——出现"已完成但被重新指派且结论丢失"的不一致行。
`export/collect` 无状态限制是设计如此，但 `assign` 应当限定在 `OPEN/CLAIMED`。

### 3.5 P2 — `reassign` 语义不一致（潜在）

`plan_task_transition('reassign')` 恒为 `OPEN`，而 `_apply_assign` 对 `assign` 是 `OPEN→CLAIMED`。
接口层面 `reassign` 携带 `assigneeId` 时会写出「状态=待领取、但 assignee 和租约都已设置」的行。
当前前端没有给 `reassign` 渲染成员选择器，所以是潜在问题；建议要么禁止 `reassign` 带目标，
要么让它转 `CLAIMED`。

### 3.6 P2 — 死代码 / 死列 / 声明未用

| 项 | 位置 | 说明 |
| --- | --- | --- |
| `REVIEW_SIDE_EFFECTS` | `repositories.py:129` | 只在测试里被断言，运行时未使用（`assign` 是硬编码 `if`） |
| `allowed_actions` 列 | `content/models.py:98`、`human_task`、`material` | NOT NULL 且 `seed_dev.py:460` 仍在写，但 API 已改为实时计算，属遗留列 |
| `web/lib/mock-data.ts` | 整文件 | 全仓无 import，但 `web/README.md:25` 仍声称"页面用 mock-data" |

### 3.7 P2 — `_allowed_actions` 与 `_require_permission` 的上下文不一致（潜在）

`_allowed_actions`（`:225-230`）构造 `ResourceContext` 时**不传** `assignee_id`，
而 `_require_permission`（`:185-195`）传了。当前所有授权范围都是 `TENANT_ALL`，无影响；
一旦有策略使用 `ASSIGNED` 范围，就会出现"按钮能点、点了 403 data_scope_mismatch"。

---

## 4. 后端缺口：15 条路由里只有 5 条写路由

实际路由（`create_app().openapi()` 导出）：

```
POST /api/v1/auth/login        POST /api/v1/auth/refresh    POST /api/v1/auth/logout
GET  /api/v1/me
GET  /api/v1/workflow-runs     GET  /api/v1/workflow-runs/{id}
POST /api/v1/workflow-runs/{id}/actions
GET  /api/v1/human-tasks       GET  /api/v1/human-tasks/{id}
POST /api/v1/human-tasks/{id}/actions
GET  /api/v1/materials         GET  /api/v1/materials/{id}
GET  /api/v1/organization/members
GET  /health/live              GET  /health/ready
```

| 缺口 | 影响 |
| --- | --- |
| **没有任何创建/编辑端点** | 内容任务、人工任务、素材只能靠 `scripts/seed_dev.py` 产生；`POST /workflow-runs`、素材 create/upload/edit 全部不存在 |
| 无 admin 端点 | 前端 7 个管理入口（成员/角色/工作流模板/模型策略/模型凭证/配额/审计）后端全无 |
| `export` 无下载端点 | 成品落 `content_export.payload`，但没有任何路由能取出来 |
| `collect` 是 `ILIKE '%brand%'` | 字符串匹配，非语义检索；且未转义 `%`/`_` |
| 分页只有 `page/page_size` | 前端不做分页 UI，`use-api.ts` 固定请求第 1 页；`content/page.tsx:85` 的"共 N 项"取 `items.length` 而非 `total`，>20 条时显示错误 |
| 单租户假设 | `authenticate`（`:258-267`）取第一个 ACTIVE membership，无租户切换（`app-shell` 的租户切换器是死的） |
| `openapi/openapi.yaml` 是手写草案 | 路径 `/session`、`/content-runs`、`/decisions` 与实现（`/me`、`/workflow-runs`、`/actions`）全不一致，无契约测试 |

---

## 5. 前端"能看不能点"清单（渲染了但没有后端或没有 handler）

| 页面 | 元素 | 现状 |
| --- | --- | --- |
| 概览 `app/page.tsx` | "上午好，林编辑"(21)、运行中 12(29)、今日已完成 18(41)、配额 37/80(8,47)、"2 个任务等待外部模型"(30) | 硬编码；只有"待人工处理"接了真数据 |
| 概览 | 侧栏徽标 `人工任务 <em>3</em>` (`app-shell.tsx:41`) | 硬编码 3 |
| 内容任务 `content/page.tsx` | 新建任务(25)、搜索框(34)、筛选(36) | 无 onClick/onChange |
| 内容详情 `content/[id]/page.tsx` | 更多操作(92)、查看版本记录(148) | 无 handler；页面自述"骨架，后续接入结构化产物与版本编辑器" |
| 人工任务 `human-tasks/page.tsx` | 4 个 tab + 计数「2」「7」(27-28)、筛选(32) | tab 无 state，计数硬编码（实际只有 3 条任务） |
| 素材库 `materials/page.tsx` | 导入 URL(22)、上传文件(23)、搜索(29)、筛选(30)、行内 `+`(43) | 全部无 handler（`source:create` 权限与按钮都就绪，但无端点） |
| 系统管理 `admin/page.tsx` | 7 个入口按钮(22) | 纯展示，无路由无端点 |
| 全局 | 顶栏搜索(`app-shell.tsx:56`)、租户切换器(31) | 无 handler |

---

## 6. 文档漂移

| 文档 | 声称 | 实际 |
| --- | --- | --- |
| `docs/08-project-structure.md:142,197-201` | "只实现了读接口，写操作尚未落地"、"Celery 空转：未注册任何任务"、"工作流状态机尚未接入"、"真实阶段/状态字段尚未建模" | 全部已被 ADR-0003/0004/0005 推翻；`docs/README.md` 却说该目录是"统一设计基线" |
| `web/README.md:25` | "页面目前使用 `lib/mock-data.ts`" | 已全部改为真 API，文件成死代码 |
| `README.md:3-5` | "contains the MVP engineering skeleton only" | 低估了现状（已有 RBAC/状态机/异步生成） |

---

## 7. 建议修复顺序

| 优先级 | 事项 |
| --- | --- |
| P0 | 修 `logout` 的 Cookie 清除（§3.1）；前端侧栏接 `apiClient.logout()` 后再跳转（§3.2） |
| P0 | 补一个真实 DB 的端到端验证（`seed_dev.py` → login → 5 个写动作 → export/collect/assign → worker 回写），这是唯一的证据缺口 |
| P1 | `assign` 加状态守卫（§3.4）；`/health/ready` 注册 DB/Redis 探针（§3.3） |
| P1 | 刷新 `docs/08`、`web/README.md`；或明确标注为历史快照 |
| P2 | 清理死列 `allowed_actions` / `REVIEW_SIDE_EFFECTS` / `mock-data.ts`；`reassign` 语义收敛（§3.5）；统一 `ResourceContext` 上下文（§3.7） |
| P2 | 假按钮：要么补端点（新建任务 / 素材上传），要么换成"未开放"并 `disabled` |

---

## 8. 一句话总结

**不是"功能都真实实现可用了"，而是"一条执行链路真实可用 + 一个可演示的只读外壳"。**
写动作、授权、状态机、异步生成、导出/采集/指派都是真实现（并在 CI 有覆盖），
但产品闭环缺了最前面的"创建"和最外面的"下载/管理"，前端还有大量装饰性交互；
另有 2 个 P0 级缺陷（登出不清 Cookie、前端从不调登出）需要先修。
