# 项目结构与功能地图

本文按**当前代码**逐层记录 AIPY 仓库的目录职责、模块边界与关键链路，供日常开发定位文件用。
设计意图与未来方向见 [`docs/README.md`](./README.md) 索引中的设计文档，两者冲突时以设计文档为准并记录 ADR。

## 0. 技术栈与分层

| 层 | 技术 | 位置 |
| --- | --- | --- |
| API | FastAPI（同步 SQLAlchemy Session）、Pydantic v2 | `apps/api` |
| 异步任务 | Celery（注册 `content.run.execute`，执行内容生成并回写正文） | `apps/worker` |
| 领域模块 | DDD 风格：`domain/`（模型 + Port）+ `infrastructure/`（适配器）+ `service.py` | `src/aipy/modules/*` |
| 共享内核 | 配置、ORM 基类/Mixin、会话与 RLS 上下文、安全上下文与错误 | `src/aipy/shared` |
| 持久化 | PostgreSQL 16（全表 RLS，租户隔离）+ Redis 7 | `migrations`、`deploy/compose.yaml` |
| 前端 | Next.js 15 App Router + React 19 + TypeScript | `web` |

依赖方向：`apps/*` → `aipy.modules/*` → `aipy.shared/*`；`modules` 之间只允许依赖 `organization`/`tenancy` 的模型与 `shared`。

## 1. 顶层目录

| 目录 | 内容 |
| --- | --- |
| `apps/api` | FastAPI 应用：入口、中间件、依赖、路由、仓储、契约模型 |
| `apps/worker` | Celery 应用对象与配置 |
| `src/aipy` | 领域模块与共享内核（唯一可被引用的业务代码） |
| `migrations` | Alembic 环境、版本脚本、`alembic.ini` |
| `web` | Next.js 前端（`app/` 路由、`components/`、`lib/`） |
| `scripts` | `seed_dev.py` 建库播种；`scripts/dev/*.ps1` Windows 一键开发脚本 |
| `deploy` | Dockerfile、compose（postgres/redis/minio/api/worker/migrate）、运行时角色初始化 |
| `docs` | 设计基线文档与 ADR |
| `openapi` | OpenAPI 3.1 **草案**（与实现有差异，见 §9） |
| `tests` | 单元测试 + PostgreSQL RLS 集成测试 |

## 2. `apps/api` — HTTP 适配层

| 文件 | 职责 |
| --- | --- |
| `main.py` | `create_app()`：注册 CORS 与 `RequestIdMiddleware`、把 `HTTPException`/`RequestValidationError` 统一转成 `ProblemDetails`、挂载路由；启动即预热 `session_factory` 与 `jwt_service`（连接错误、缺签名密钥在启动时暴露） |
| `middleware.py` | `RequestIdMiddleware`：复用或生成请求 ID，写入 `request.state.request_id` 并回写 `X-Request-ID` 响应头 |
| `dependencies.py` | 单例与鉴权依赖：`get_jwt_service` / `get_login_lockout` / `get_revocations` / `get_session_factory` / `get_authorization_service`（均 `lru_cache`）；`require_claims` → `require_tenant` → `get_tenant_context` → `get_current_session` |
| `repositories.py` | SQLAlchemy 查询层：登录校验、会话装配、三块看板的分页与详情查询，并按调用者策略**实时计算** `allowed_actions` |
| `schemas.py` | 请求/响应模型，字段命名刻意对齐 `web/lib/types.ts`（snake/camel 混排），泛型 `Page[T]` = `{items, page, page_size, total}` |
| `routes/health.py` | `/health/live`、`/health/ready`（就绪检查由 `app.state.readiness_checks` 注入，任一失败返回 503） |
| `routes/auth.py` | `/api/v1/auth/login`、`/auth/refresh`、`/auth/logout`、`/api/v1/me` |
| `routes/workflow_runs.py` | `/api/v1/workflow-runs` 列表与详情（对应内容任务 `content_run`） |
| `routes/human_tasks.py` | `/api/v1/human-tasks` 列表与详情 |
| `routes/materials.py` | `/api/v1/materials` 列表与详情 |

## 3. `src/aipy/modules` — 领域模块

| 模块 | 关键文件 | 职责 |
| --- | --- | --- |
| `tenancy` | `models.py` | `Plan`、`Tenant`、`TenantSubscription`：租户主档、套餐与配额、订阅周期与宽限期 |
| `organization` | `models.py` | `AppUser`（跨租户账号，Argon2 哈希）、`TenantMembership`（成员身份，含 `job_title` 作为当前角色信号）、`Team`（可层级）、`TeamMember` |
| `brand` | `models.py` | `Workspace`（协作空间，持有默认品牌）、`Brand`（口吻规范、禁用词、默认语言） |
| `content` | `models.py` | `ContentRun`、`HumanTask`、`Material`：三块看板的持久化实体，含展示文案字段（`stage_label`/`status_label`/`tone`/`*_label`）与租户内 `seq` 排序键 |
| `identity` | `domain/models.py`、`domain/ports.py` | 令牌值对象（`TokenSubject`/`AccessTokenClaims`/`RefreshTokenClaims`/`TokenPair`/`JwtTokenSettings` 带长度与 TTL 校验）与端口（`TokenService`、`TokenRevocationRepository`、`PasswordHasher`、`LoginLockout`） |
| `identity` | `infrastructure/jwt_tokens.py` | PyJWT 实现：签发/校验/轮换；`token_type` 校验、`iss`/`aud` 强校验、时钟偏移容忍、撤销检查 |
| `identity` | `infrastructure/passwords.py`、`redis_revocations.py`、`in_memory_revocations.py`、`login_lockout.py` | 哈希适配器；Redis 撤销存储（`SET NX` 保证 refresh 单次使用、TTL 取令牌剩余寿命）；进程内/Redis 两种登录锁定 |
| `authorization` | `domain/models.py` | `Permission`（`resource:action` 正则约束）、`DataScope`、`PermissionGrant`、`WorkflowStatePolicy`、`SeparationOfDutiesPolicy`、`AuthorizationPolicy`、`ResourceContext`、`DenialReason`、`AuthorizationDecision` |
| `authorization` | `service.py` | `AuthorizationService`：默认拒绝，按顺序判定租户一致性 → 资源类型 → 策略存在 → 租户/成员活跃 → 权限命中 → 工作流状态 → 职责分离 → 数据范围 |
| `authorization` | `infrastructure/policy_repository.py` | `SqlAuthorizationPolicyRepository`：由租户 + 成员 + 用户状态生成策略快照；当前所有角色均为 `TENANT_ALL` 范围 |
| `authorization` | `infrastructure/role_catalog.py` | 静态角色目录：`job_title` → 角色 → 权限集（管理员/编辑/审核员/成员）；接入真实 RBAC 表时只需替换仓储实现 |

## 4. `src/aipy/shared` — 共享内核

| 文件 | 职责 |
| --- | --- |
| `config.py` | `AppSettings`：`AIPY_` 前缀、`__` 嵌套分隔符、读根目录 `.env`；`cookie_secure`（仅 staging/production 加 Secure）、`uses_shared_state`（非 local/test 时才走 Redis）；`jwt_secret()` 在非 local/test 缺失密钥时直接抛错 |
| `db/base.py` | 声明式基类 + 索引/约束命名约定 |
| `db/ids.py` | `new_uuid7()`：应用侧生成时间有序 UUIDv7 主键 |
| `db/mixins.py` | `UUIDPrimaryKeyMixin`、`TimestampAuditMixin`、`OptimisticLockMixin`（`row_version` + `version_id_col`）、`TenantScopedMixin`（`tenant_id` FK → `tenant.id`）；组合出 `EntityMixin` / `TenantEntityMixin` |
| `db/session.py` | `make_engine` / `make_session_factory`（`autoflush=False`）；`set_tenant_context`（`app.tenant_id`、`app.membership_id`）、`set_user_context`（`app.user_id`，登录后自助查成员用）；`session_scope` / `tenant_session_scope` 事务上下文（RLS 变量用 `set_config(..., true)`，事务结束即失效） |
| `security/context.py` | `TenantContext` / `ActorContext`：只能由已验证凭据构造，禁止合并请求体中的租户/成员标识 |
| `security/errors.py` | 与框架无关的稳定错误码（`INVALID_TOKEN`、`TOKEN_REVOKED`、`AUTHORIZATION_DENIED` 等） |

## 5. 数据模型与隔离

**表清单**（13 张，迁移 `0001`/`0002` 建立）

| 域 | 表 | RLS |
| --- | --- | --- |
| 全局 | `plan`、`app_user` | 否 |
| 租户 | `tenant`（按 `id` 隔离）、`tenant_subscription`、`tenant_membership`、`team`、`team_member`、`workspace`、`brand` | 是（`ENABLE` + `FORCE`） |
| 内容 | `content_run`、`human_task`、`material` | 是（`ENABLE` + `FORCE`） |

- 迁移 `0003` 为 `tenant_membership` 增加**自助查询策略**：登录时还没有 `app.tenant_id`，故校验密码后设置 `app.user_id`，仅暴露该用户自己的成员行。
- 迁移 `0004` 补充内容表的**复合外键**（`tenant_id` + 业务 ID），防止跨租户引用。
- 迁移 `0005` 为全部表/列写入中文注释（注释声明在 ORM 模型上，否则 `alembic check` 会判漂移）。
- 运行时角色必须非 superuser、非表 owner、无 `BYPASSRLS`；`deploy/postgres/init-runtime-role.sh` 负责创建。

## 6. 认证链路

```
POST /auth/login → 登录锁定检查(429) → authenticate()：查 app_user → 校验状态 → Argon2 校验
                 → set_user_context(app.user_id) → 取 ACTIVE 成员 → 签发令牌对 → 写 HttpOnly Cookie → 返回 TenantSession
GET  /me         → require_claims(access_token) → build_session() → TenantSession
POST /auth/refresh → 校验 refresh → rotate_token_pair（SET NX 单次消费）→ 轮换 Cookie
POST /auth/logout  → 撤销 access token 与整个 session → 清 Cookie（幂等）
```

- Cookie：`access_token`（path `/`，15 分钟）、`refresh_token`（path `/api/v1/auth`，14 天，普通请求不会携带）；`samesite=lax`。
- 所有失败模式统一返回 `None` → 401，避免账号枚举；连续失败 10 次锁定 15 分钟（邮箱小写归一化为 key）。
- 撤销/锁定状态：`local`/`test` 用进程内实现，其余环境走 Redis，保证多副本一致。

## 7. 授权链路

`AuthorizationService.authorize()` 判定顺序与拒绝原因：

| 顺序 | 检查 | 拒绝原因 |
| --- | --- | --- |
| 1 | 权限码格式 | `INVALID_PERMISSION` |
| 2 | 主体与资源租户一致 | `TENANT_MISMATCH` |
| 3 | 权限 resource 与资源类型一致 | `RESOURCE_TYPE_MISMATCH` |
| 4 | 策略存在 | `POLICY_NOT_FOUND` |
| 5 | 租户 / 成员与用户活跃 | `TENANT_INACTIVE`、`ACTOR_INACTIVE` |
| 6 | 权限被授予 | `PERMISSION_MISSING` |
| 7 | 工作流状态允许 | `WORKFLOW_STATE_DENIED` |
| 8 | 职责分离（提交人/创建人不可自审；编辑者不可自发布等） | `SEPARATION_OF_DUTIES` |
| 9 | 数据范围（当前统一 `TENANT_ALL`） | `DATA_SCOPE_MISMATCH` |

- 看板行的 `allowed_actions` **由服务实时计算**，不再读取 `content_run.allowed_actions` 等存储列（列仍存在，属种子数据遗留）；返回给前端时只取 `action` 半段（如 `view`、`approve`）。
- 资源类型必须匹配权限前缀：`content` / `review` / `source`，候选动作定义在 `repositories.CANDIDATE_ACTIONS`（顺序即响应顺序）。

## 8. API 契约（实现现状）

以 `create_app().openapi()` 为准，共 22 条路由。`openapi/openapi.yaml` 是手写草案，与实现不一致，不作为契约来源。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health/live` | 存活 |
| GET | `/health/ready` | 就绪；默认注册 PostgreSQL（`SELECT 1`）与 Redis（`PING`）探针，任一失败返回 503 |
| POST | `/api/v1/auth/login` | 登录，签发 Cookie 对并返回会话 |
| POST | `/api/v1/auth/refresh` | 轮换令牌对（refresh 单次使用） |
| POST | `/api/v1/auth/logout` | 撤销并在**返回的** Response 上清 Cookie，204 |
| GET | `/api/v1/me` | 当前会话（租户/工作区/用户/权限） |
| GET | `/api/v1/workflow-runs` | 内容任务分页；支持 `q`（标题/品牌/编码）与 `status` |
| POST | `/api/v1/workflow-runs` | 新建任务（`content:create`），直接以 RUNNING 落库并投递 worker |
| GET | `/api/v1/workflow-runs/counts` | 各状态计数，供概览页指标使用 |
| GET | `/api/v1/workflow-runs/{run_id}` | 详情（`run_id` 为业务编码，如 `CR-20260724-018`），额外返回 `content` 正文 |
| POST | `/api/v1/workflow-runs/{run_id}/actions` | 状态动作 + 副作用动作，需 `If-Match` |
| GET | `/api/v1/workflow-runs/{run_id}/exports` | 导出记录列表 |
| GET | `/api/v1/workflow-runs/{run_id}/exports/{export_id}/download` | 下载导出成品（markdown） |
| POST | `/api/v1/workflow-runs/{run_id}/materials/{material_id}` | 把素材关联到任务（幂等） |
| GET | `/api/v1/human-tasks` | 人工任务分页；支持 `q`、`status`、`mine` |
| GET | `/api/v1/human-tasks/counts` | 各 Tab 计数与待办总数 |
| GET | `/api/v1/human-tasks/{task_id}` | 人工任务详情 |
| POST | `/api/v1/human-tasks/{task_id}/actions` | 领取/转派/提交/通过/驳回/分派，需 `If-Match` |
| GET | `/api/v1/materials` | 素材库分页；支持 `q`、`type` |
| POST | `/api/v1/materials` | 建素材；带 `url` 时服务端抓取标题与摘要（含 SSRF 防护） |
| POST | `/api/v1/materials/upload` | multipart 上传原件，字节存 `material_file`，上限 10 MB |
| GET | `/api/v1/materials/{material_id}` | 素材详情 |
| GET | `/api/v1/materials/{material_id}/file` | 下载上传的原件 |

- 分页响应固定为 `{items, page, page_size, total}`（不是 `pageSize`）。
- 业务路由统一依赖：`get_tenant_context`（可信主体）+ `get_authorization_service` + `get_current_session`（租户/工作区可用性）。
- 声明在前、匹配在后的字面量路径（`/counts`）必须写在 `/{id}` 之前，否则会被路径参数吃掉。
- 下载响应的文件名走 RFC 5987（`filename*=UTF-8''`）并带 ASCII 回退，因为 HTTP 头是 latin-1。

## 9. 前端 `web`

| 路径/文件 | 职责 |
| --- | --- |
| `app/page.tsx` | 根路径重定向到 `/login` |
| `app/login/page.tsx` | 登录表单，成功后跳 `/app`（预填演示账号） |
| `app/(workspace)/app/layout.tsx` | `SessionLoader` → `AppShell` 包裹所有工作台页面 |
| `app/(workspace)/app/page.tsx` | 概览：状态计数指标卡 + 最近内容任务 + 待处理人工任务 |
| `app/(workspace)/app/content/page.tsx`、`content/[id]/page.tsx` | 内容任务列表（搜索/筛选/分页/新建弹窗）与详情（正文、导出记录与下载） |
| `app/(workspace)/app/human-tasks/page.tsx` | 人工任务队列，Tab 为服务端过滤 + 真实计数 |
| `app/(workspace)/app/materials/page.tsx` | 素材库：导入 URL、上传文件、筛选、下载原件、关联到任务 |
| `app/(workspace)/app/admin/page.tsx` | 系统管理（受权限门控）；入口按钮均 `disabled`，因后端接口尚未实现 |
| `app/forbidden/page.tsx` | 无权限页 |
| `lib/api-client.ts` | `HttpApiClient`：统一 `credentials: "include"`；遇 401 自动静默刷新一次并重放请求；非 2xx 抛 `ApiProblem`（ProblemDetails）；204/空体不再尝试 `json()`；下载走 blob + `Content-Disposition` |
| `lib/use-api.ts` | `useApiList(kind, query)`：带查询参数的加载态封装；`useDebouncedValue` 用于搜索框 |
| `lib/types.ts` | 与后端 `schemas.py` 对齐的类型（`PermissionCode`、`TenantSession`、`*Summary`、`*Counts`） |
| `components/app-shell.tsx` | 侧边导航（每项可挂 `permission`）、真实待办徽标、顶栏搜索、退出登录（调用 `/auth/logout` 后跳转） |
| `components/session-loader.tsx` | 拉取 `/me`，失败重定向登录，成功提供 `TenantProvider` |
| `components/tenant-context.tsx`、`permission-gate.tsx` | 会话上下文；基于 `permissions` 的显隐门控（支持 `anyOf`、`invert`） |
| `components/ui.tsx` | `PageHeader`、`StatusBadge`、`Modal`、`Pagination`、`ActionNoticeBar`、`EmptyState`、`ForbiddenState` 等基础组件 |

前端基准地址默认 `http://localhost:8000/api/v1`（`NEXT_PUBLIC_API_BASE_URL` 可覆盖）。

## 10. 工程配套

| 位置 | 用途 |
| --- | --- |
| `migrations/env.py` | 从 `AIPY_DATABASE_URL` 或 `AIPY_DATABASE__URL` 覆盖 `sqlalchemy.url`；导入各模块模型以支撑 autogenerate 漂移检查 |
| `scripts/seed_dev.py` | 先 `alembic upgrade head`，再按固定 UUID **逐实体幂等**插入演示数据；演示账号 `editor@example.com` / `demo-password` |
| `scripts/dev/*.ps1` | Windows 一键脚本：`install` / `infrastructure` / `migrate` / `start`（前后端）/ `test` / `check-python` |
| `deploy/compose.yaml` | postgres、redis、minio(+init)、`migrate`（一次性）、`api`、`worker`（均属 `application` profile） |
| `deploy/Dockerfile` | 多阶段构建，`api` 与 `worker` 两个 target |
| `tests/unit/*` | 授权服务（默认拒绝、范围、职责分离）、授权接线（allowed_actions 由服务产出）、健康检查、安全错误、租户模型 |
| `tests/integration/test_tenant_rls.py` | 真实 PostgreSQL RLS 校验：缺失 `app.tenant_id` 时 0 行、跨租户写入被拒、复合 FK 拒绝跨租户父级、`SET LOCAL` 不跨事务；缺环境变量时跳过 |
| `tests/fixtures/e2e/*.json` | 端到端场景夹具（全自动、全人工、辅助审核、越权、上游改动过期） |

质量门禁：`ruff check .`（line-length 100）、`mypy`（strict）、`pytest`。

## 11. 关键约定与坑

| 事项 | 说明 |
| --- | --- |
| RLS 上下文 | 任何租户表查询必须走 `tenant_session_scope`；未设 `app.tenant_id` 时查询返回 **0 行**，不报错 |
| 会话 autoflush | `make_session_factory` 设 `autoflush=False`，`add()` 后需显式 `flush()` 才能被 `Session.get` 看到 |
| 同名遮蔽 | 路由函数与仓储函数同名时（如 `list_materials`）必须写成 `repositories.list_materials(...)`，否则递归自调用 |
| 表/列注释 | 注释写在 ORM 模型（`__table_args__` 末尾 `{"comment": ...}`、`mapped_column(comment=...)`），只写迁移会被判漂移；autogenerate 产出的 revision 名需手工改为 `YYYYMMDD_000N`。手工迁移要给实体列（`id`/`tenant_id`/`created_*`/`updated_*`/`row_version`）也写上 `comment=`，否则 `alembic check` 会报差 |
| 复合外键 | 形如 `(tenant_id, x_id) → (t.tenant_id, t.id)` 的外键要求被引用列上有**唯一约束**，主键在 `id` 上并不满足；受影响表需自带 `UniqueConstraint("tenant_id", "id")`，且该约束必须在建外键**之前**创建 |
| 路由声明顺序 | 字面量路径（`/counts`）必须声明在 `/{id}` 之前，否则会被路径参数匹配 |
| 迁移执行 | 在 `migrations/` 目录下运行，或 `python -m alembic -c migrations/alembic.ini upgrade head` |
| 签名密钥 | 非 local/test 必须提供 `AIPY_JWT__SECRET_KEY`（≥32 字符），否则启动失败 |
| 数据范围 | 内容实体尚无 `workspace_id`/`team_id`，因此 `WORKSPACE`/`TEAM` 范围暂不可用，全部按 `TENANT_ALL` 授予 |
| 代理干扰 | 本机存在 `HTTP_PROXY` 时探活 `127.0.0.1` 会假失败，需绕过代理或设 `NO_PROXY` |

## 12. 当前缺口

1. **人工任务仍只能由 seed 产生**：没有创建端点，也没有"质量门禁失败自动转人工"的编排；`content.run.execute` 只回写正文与状态。
2. **admin 七个模块无后端**：成员/角色/工作流模板/模型策略/模型凭证/配额/审计均无接口，前端入口已置灰而非可点。
3. **多租户未开放**：`authenticate` 取第一个 ACTIVE membership，无租户切换接口；侧栏切换器已置灰。
4. **`collect` 是字符串匹配**：`ILIKE` 命中品牌/标题（`%`、`_` 已转义），不是语义检索。
5. **数据范围恒为 `TENANT_ALL`**：内容实体仍无 `workspace_id`/`team_id`，因此 `WORKSPACE`/`TEAM` 范围不可用。`_allowed_actions` 构造 `ResourceContext` 时也未传 `assignee_id`，一旦有 `ASSIGNED` 范围策略会出现"按钮可点、点了 403"。
6. **展示字段落库**：`stage_label`、`status_label`、`*_label`、`tone` 等前端文案直接存库，真实阶段/状态字段尚未建模。
7. **遗留列 `allowed_actions`**：API 已改为实时计算，该列仍在写入（seed 写固定数组，新建行写空数组），属可清理项。
8. **`openapi/openapi.yaml` 是手写草案**：路径（`/session`、`/content-runs`）与实现不一致，且无契约测试，不要当作契约来源。

### 已修复（2026-09-28）

- `logout` 曾在新建的 `Response` 上返回 204、把 `delete_cookie` 留在被丢弃的注入对象上，浏览器保留旧 Cookie。
- 前端从未调用 `/auth/logout`，侧栏"退出"只是跳转登录页。
- `/health/ready` 未注册任何依赖探针，无库实例也返回 `200 ready`。
- `_apply_assign` 无状态守卫，对 COMPLETED/CANCELLED 任务分派会清掉 `decision` 但保留终态。
- `collect` 的 `ILIKE` 未转义 `%`/`_`。
- 迁移 `0008` 的复合外键引用 `content_run(tenant_id, id)` / `material(tenant_id, id)`，但这两张表当时只有 `id` 主键、没有对应的唯一约束，PostgreSQL 会拒绝创建该外键；已补 `uq_content_run_tenant_id_id`、`uq_material_tenant_id_id`，并把实体列的 COMMENT 一并写全，使手工迁移与 ORM 元数据对齐。
