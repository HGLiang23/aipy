# 代码修复与接线报告 — 2026-09-28

**目标**：把 `code-review-2026-09-25.md` 指出的「前端能看不能点」改成真实闭环。

**结论**：2 个 P0、2 个 P1 已修；新增 4 组写端点（含上传/下载）；前端 22 处装饰性控件全部接线或显式
`disabled`。静态质量门全绿（ruff / ruff format / mypy / tsc / pytest 124 passed）。
**数据库端到端未执行**——按你的指示「先不连接库验证」，本期不碰任何数据库。

---

## 1. P0 / P1 修复

| 级别 | 问题 | 位置 | 修法 |
| --- | --- | --- | --- |
| P0 | `logout` 不清 Cookie | `apps/api/routes/auth.py` | 原写法注入 `Response` 后又 `return Response(204)`，FastAPI 只在**返回非 Response 值**时才合并注入 response 的 `Set-Cookie`，必然丢。改为自建 `Response(204)`、在其上 `_clear_auth_cookies` 再返回；并补 `httponly=True, samesite="lax"` |
| P0 | 前端从不调 `logout()` | `web/components/app-shell.tsx` | 侧栏「退出」由 `<Link href="/login">` 改为真调 `apiClient.logout()` → `router.replace("/login")` |
| P1 | `/health/ready` 无探针，无 DB 也返回 200 ready | `apps/api/routes/health.py`、`apps/api/main.py` | 新增 `DATABASE_CHECK` / `REDIS_CHECK`（2s 超时、`anyio.to_thread` 卸载）；`create_app` 在 `readiness_checks is None` 时接 `default_readiness_checks(...)`，探针失败返回 503 |
| P1 | `assign` 无状态守卫，对已结束任务也能改 | `apps/api/repositories.py` | `_apply_assign` 加守卫：状态不在 `{OPEN, CLAIMED}` → 409 `illegal_transition` |

## 2. 新增后端端点（路由 15 → **24**，写路由 5 → **9**）

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/api/v1/workflow-runs` | 建内容任务，起始态 RUNNING，编码 `CR-YYYYMMDD-NNN` |
| POST | `/api/v1/materials` | 建素材（支持 URL 导入，走 SSRF 校验） |
| POST | `/api/v1/materials/upload` | multipart 上传，单文件上限 10MB |
| GET | `/api/v1/materials/{id}/file` | 下载素材原件 |
| POST | `/api/v1/workflow-runs/{id}/materials/{material_id}` | 素材关联到任务 |
| GET | `/api/v1/workflow-runs/{id}/exports` | 导出历史列表 |
| GET | `/api/v1/workflow-runs/{id}/exports/{export_id}/download` | 下载导出件（`filename*=UTF-8''`） |
| GET | `/api/v1/workflow-runs/counts` | 任务分状态计数 |
| GET | `/api/v1/human-tasks/counts` | 人工任务分状态计数 |

列表端点同时补齐 `query` / `status` / `type` / `assignee_id` 过滤（`ILIKE` 已转义 `%`、`_`）。

新增文件：`apps/api/url_import.py`（SSRF 防护：scheme + 全局 IP 校验、手动跟最多 5 次重定向、
响应体上限 256KB）、`apps/api/http_utils.py`（RFC 5987 下载文件名头）。
新增表 `material_file`（迁移 `20260928_0009_material_file.py`，含 RLS）。

## 3. 前端接线

| 页面 / 组件 | 原状 | 现状 |
| --- | --- | --- |
| `app-shell.tsx` | 退出是链接；待办角标硬编码 | 真 `logout()`；角标真拉 `humanTaskCounts().pending` |
| 顶栏搜索 | 装饰 | 真跳 `/app/content?q=` |
| 租户切换器 / admin 7 入口 | 装饰 | 显式 `disabled` +「待开放」 |
| 首页指标卡 | 硬编码数字 | 真拉 `contentRunCounts()` |
| `content/page.tsx` | 无搜索/过滤/分页 | 搜索 + 状态过滤 + 分页 + 新建任务弹窗 |
| `content/[id]/page.tsx` | 硬编码「暂停」 | 渲染真实 `run.content` + 导出历史可下载 |
| `human-tasks/page.tsx` | 4 个 tab 是静态 | 4 个 tab = 真服务端过滤 + 真计数 + 搜索 |
| `materials/page.tsx` | 无任何写操作 | URL 导入 / 文件上传 / 类型过滤 / 下载 / 关联任务 |

`lib/api-client.ts` 重写：新增 9 个方法，**204 与空 body 不再走 `.json()`**（原会抛异常）；
新增 `toQueryString` / `saveBlob` / `filenameFrom` / `download`。
`components/ui.tsx` 新增 `Modal` / `Pagination` / `ActionNoticeBar`。

## 4. 质量门证据（本次实跑）

| 门 | 命令 | 结果 |
| --- | --- | --- |
| Lint | `ruff check .` | All checks passed |
| 格式 | `ruff format --check .` | 109 files already formatted |
| 类型（后端） | `mypy apps src` | Success: no issues found in 58 source files |
| 类型（前端） | `tsc --noEmit` | exit 0，无输出 |
| 单测 | `pytest -q` | **124 passed, 1 skipped** in 4.54s |
| 迁移可渲染 | `alembic upgrade head --sql` | 离线渲染至 `20260928_0009` 成功 |

改动规模：37 个文件修改，+3865 / −394 行；另有 9 个测试文件新增。

## 5. 未验证项与风险（重要）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 数据库端到端链路 | **未执行** | 按你的指示不连库。登录→建任务→动作→导出→下载→worker 回写**全部未经真库实测**，仅有单测覆盖逻辑层 |
| RLS 集成测试 | 跳过 | `tests/integration/test_tenant_rls.py` 需已迁移的 PG 与两个不同角色 |
| 迁移 `0008` 的复合外键修复 | **未在真库验证** | `content_run` / `material` 补了 `UNIQUE(tenant_id, id)`（复合 FK 的必要条件，否则 PG 建表即拒）。离线渲染已含该约束，但未在真实 PG 上跑过 |
| `material_file.data` 存字节 | 未压测 | 单文件限 10MB，未评估大文件对库/接口的影响 |
| 真实大模型 provider | 未接入 | 需运营配 `AIPY_LLM__*`；local/test 走 `StubModelGateway` |

## 6. 等有了库之后怎么跑

```bash
# .env 已生成在仓库根（gitignored），只需把 3 处 REPLACE_WITH_REMOTE_PASSWORD 换成真口令
.venv/bin/python -m alembic -c migrations/alembic.ini upgrade head   # 或 cd migrations
.venv/bin/python scripts/seed_dev.py                                  # 幂等种子
.venv/bin/python -m uvicorn apps.api.main:app --port 8000
.venv/bin/python -m celery -A apps.worker.celery_app worker -Q content -l info
```

演示账户：`editor@example.com` / `demo-password`。
