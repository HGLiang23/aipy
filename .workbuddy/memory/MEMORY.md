# AIPY 项目长期笔记

## 技术栈与结构
- `apps/api`（FastAPI，入口 `apps/api/main.py:app`）、`apps/worker`（Celery）、`src/aipy`（DDD 模块：tenancy/organization/brand/content）、`web`（Next.js 15 App Router）、`migrations`（Alembic）。
- venv：`.venv`（Python 3.12）。依赖：fastapi / uvicorn / celery / sqlalchemy 2 / psycopg3 / pydantic-settings / redis-py。
- 数据层：PostgreSQL + 全表 RLS，租户上下文走 `tenant_session_scope`（设置 `app.tenant_id`）；登录额外用 `app.user_id` 自查询策略（迁移 0003）。

## 环境与凭据
- 配置只从根目录 `.env` 读（已被 gitignore）。变量名：`AIPY_DATABASE__URL`、`AIPY_REDIS__URL`、`AIPY_CELERY__BROKER_URL`。
- 远程测试库 `aipg_test`：PG 16.14 @ `120.26.123.108:7891`；Redis 7.2.4 @ `120.26.123.108:3769`，**统一用 DB7**。口令不入笔记，见 `.env`。
- Alembic 需从 `migrations/` 目录跑：`python -m alembic upgrade head`（`script_location = %(here)s`，`env.py` 读 `AIPY_DATABASE__URL`/`AIPY_DATABASE__URL` 覆盖 ini）。

## 常用命令
```powershell
cd D:\code\aipy
.\scripts\dev\start.ps1                             # 一键启动前后端（推荐）
.\.venv\Scripts\python.exe scripts\seed_dev.py     # 迁移 + 幂等种子
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
cd web; .\node_modules\.bin\next.cmd dev -H 0.0.0.0 -p 3000
```
演示账户：`editor@example.com` / `demo-password`。
`scripts/dev/start.ps1` 支持 `-ApiPort` / `-WebPort` / `-ApiOnly` / `-WebOnly` / `-Reload`。

## API 契约
- `/api/v1/auth/login`（注意 `me` 在 `/api/v1/me`，两者前缀不一致，前端 api-client 如此约定）。
- 列表返回 `Page<T>`：`{items, page, page_size, total}`（**不是 pageSize**）。详情额外含 `allowedActions`、`etag`、`version`、`denial_reason`。

## 工程约定与坑
- 改 schema 必须同步迁移，改完用 `alembic check` 复核漂移；`TenantScopedMixin.tenant_id` 自带 `FK → tenant.id`，新迁移别漏。
- **表/字段注释声明在 ORM 模型上**（`__table_args__` 末尾 dict `{"comment": ...}` + `mapped_column(comment=...)`，共享列在 `shared/db/mixins.py`），迁移用 `alembic revision --autogenerate` 生成。只在迁移里写 COMMENT 会被 `alembic check` 判成漂移。autogenerate 产出的 revision 是随机 hash，需手动改成 `2026MMDD_000N`。
- **ruff E501 按东亚字符宽度计算**（中文算 2 列）：含中文的长 `comment` 字面量即使 `len()` 不到 100 也可能报超长，且 `ruff format` 不会折字符串，需手工折成括号内隐式拼接。`migrations/` 现已 ruff 全净。
- `make_session_factory` 是 `autoflush=False`：`add()` 后需显式 `flush()` 才能被 `Session.get` 看到。
- 租户表 `FORCE RLS` 且 `aipg` 非超级用户 → **不设 `app.tenant_id` 时任何查询都返回 0 行**，做备份/巡检前要 `ALTER TABLE ... DISABLE ROW LEVEL SECURITY`。
- 路由里调用仓储函数要写 `repositories.xxx`，否则被同名路由函数遮蔽导致自调用。

## 前端路由（易踩）
- 真实路由在 `/app/*`：`web/app/(workspace)/app/{page.tsx, content/, content/[id]/, human-tasks/, materials/, admin/}`（`(workspace)` 是路由组，不进 URL），另有 `web/app/login`、`web/app/forbidden`。**没有** `/content`、`/human-tasks` 顶层路径。
- 后端健康检查是 `/health/live`、`/health/ready`（不是 `/healthz`）；`/openapi.json` 可用。
- **前端必须走同源代理调后端**：`web/next.config.ts` 已配 `rewrites`（`/api/:path*` → `http://localhost:8000/api/:path*`），`web/lib/api-client.ts` 的 `baseUrl` 默认是相对 `/api/v1`（不再直连 `localhost:8000`）。原因：WorkBuddy 预览面板从非 `localhost:3000` 的 origin（如 `172.22.2.169`）访问，直连会被后端 CORS（白名单仅 `localhost:3000`）拦截，且跨端口 cookie 的 `SameSite=Lax` 在 fetch 子请求里不可靠。改了 `next.config.ts` 后 Next.js 会**自动重启**（无需手动杀进程），但 `taskkill /PID x /T` 会误杀 supervisor 进程树导致前端不再被拉起——重启用 supervisor 重新 `run_in_background` 即可。

## 沙箱与运行（重要）
- **默认沙箱禁止监听端口**：python / PowerShell / 脱离进程组的子进程，`bind('127.0.0.1')` 与 `bind('0.0.0.0')` 均 `WinError 10013`，限制作用于整棵进程树。
- **给 Bash 传 `dangerouslyDisableSandbox: true` 即可正常绑定端口**，项目能在 agent 内真正跑起来；这属于「任务在语义上无法在沙箱内完成」的正当用法。
- agent 内起服务必须用 `run_in_background: true` 跑一个 `while True: sleep()` 的常驻 supervisor，否则命令一返回子进程就被回收。
- **本机有 `HTTP_PROXY=http://127.0.0.1:3468`**，会劫持 `127.0.0.1` 探活导致假 **502**；探活要 `build_opener(ProxyHandler({}))` 绕过，子进程里 `pop` 掉 proxy 变量并设 `NO_PROXY`。
- `netstat` / `tasklist` 输出是 **GBK**，`subprocess(text=True)` 要加 `encoding='gbk', errors='replace'`。
- PowerShell `Start-Process` 会报 `已添加项。字典中的关键字:"HTTPS_PROXY"...`（本机 env 同时有大小写两种代理变量）；用 Python `subprocess` 启动可绕开。
- PowerShell 取证：stdout 回传失效，需 `Set-Content` 写文件再 Read。Bash 的 coreutils 可能整体失效（`ls/grep/head/dirname` not found），此时改用 `python -c` 或 PowerShell。
- 服务长期运行请让用户在自有终端跑 `scripts/dev/start.ps1`；agent 内进程会随任务回收。
- **`.ps1` 一律只写 ASCII**：`Write` 产出的是无 BOM UTF-8，而 Windows PowerShell 5.1 按 ANSI(GBK) 解码，中文注释/字符串会乱码甚至触发 `字符串缺少终止符`。可用 `[System.Management.Automation.Language.Parser]::ParseFile()` 静态校验语法，无需真的执行。

## 用户偏好
- 要简洁、不要冗余；变更摘要用表格；先给结论再列证据；多步改动过程中会反复要求增量确认。

## 管理后台接口备忘（09-24 复核）
- 7 个 admin 模块中 **6 个有写能力**：members PUT、roles PUT、workflow-templates POST publish、model-credentials POST/test/DELETE、model-routing-policies PUT、quotas PUT。**audit-logs 刻意只读**（BEFORE UPDATE/DELETE 触发器强制 append-only）。
- `POST /api/v1/model-credentials` 请求体字段为 **snake_case**：`{provider_id, name, secret, ownership_type?}`。若传 camelCase（`provider`/`apiKey`）会得到笼统的 422 `{"detail":"request validation failed"}`，无字段级提示。
- `DELETE /model-credentials/{id}` 是**撤销**（status→REVOKED，HTTP 204），非物理删除；因此同名重建前需换名或用唯一后缀（smoke 用 `__smoke__{ts}`）。
- 可用测试账号：`editor@example.com` / `demo-password`。
- `GET /model-providers` 返回分页对象，需取 `items[0].id` 作为 provider_id。

## 成员新增（09-24）
- `POST /api/v1/members` 请求体：`{email, displayName, role_id（必填）, job_title?}`。响应 = `CreateMemberResponse`（MemberSummary + `initialPassword` + `accountCreated`）。
- **`role_id` 必填**：省略时曾回落 `is_default` 角色，而种子里 admin 就是 `is_default=True` → 静默提权。别再引入「默认角色」回落。
- 邮箱若已是平台用户（`app_user.email` 全局唯一），**复用账号**加入本租户并返回 `initialPassword=null`；已是本租户成员 → 409。
- 无删除成员接口（有外键指向 `tenant_membership`）；移除语义 = `status='SUSPENDED'`（`PUT /members/{id}`）。
- `scripts/smoke_admin.py` 27 项；跑完用 `scripts/cleanup_smoke_data.py [--dry-run]` 清 `__smoke__` 残留。

## 构建租户实体的硬性要求
- `TenantScopedMixin.tenant_id` **无默认值**，必须显式传 `tenant_id=...`。漏了会报 `new row violates row-level security policy for table "<table>"`（是 WITH CHECK 失败，不是缺权限）。
- API 请求体字段命名在同一文件里**驼峰与下划线混用**（如 `displayName` 配 `role_id`），写仓储前先读 schema，别猜。

## 前端类型检查 / 验证工具
- `web` 下 `npx tsc --noEmit` 是快速回归（约 13s）。
- 页面走客户端渲染（`SessionLoader` 以 `GET /me` 为门），**curl 拿到的 HTML 只有「加载中…」**，要看真实渲染必须用浏览器。
- 本机已装无头 Chrome 工具：`C:/Users/hongguoliang/.workbuddy/binaries/node/workspace/node_modules/.bin/agent-browser`（需 `PATH` 前置 managed node 22；输出**不能走管道**，要重定向到文件；daemon 不跨 Bash 调用存活，登录+操作必须写在同一次调用里）。

## 成员密码重置（09-24）
- `POST /api/v1/members/{member_id}/reset-password` → 200 `{memberId,displayName,email,password}`；404 不存在；**409 成员非 ACTIVE**；422 非法 UUID。
- 语义 = 覆盖 `app_user.password_hash`，**旧密码立即失效**（实测旧密码 401）。审计 `member.password_reset` 只记 email/displayName。
- `app_user` 是**平台级全局账号**（email 全局唯一），重置会影响该账号在**所有租户**的密码 —— 接口设计时须考虑这点，UI 要给二次确认。
- 登录要求 `TenantMembership.status == "ACTIVE"`（`repositories.py` 的 `authenticate`），所以停用成员重置密码无意义，直接 409。
- **后端没有权限强制**：`member:manage` 等权限码仅在前端 `PermissionGate` 生效，API 层只校验 `require_tenant` 登录态。所有 admin 写接口都如此，是既有缺口。
- smoke 现在 33 项；`scripts/cleanup_smoke_data.py` 会清 `__smoke__` 成员/凭证/路由策略。
