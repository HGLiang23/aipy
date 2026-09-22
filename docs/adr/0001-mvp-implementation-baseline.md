# ADR-0001: MVP 工程实现基线

- 状态：Accepted
- 日期：2026-07-24

## 背景

首版面向小团队，优先保证租户隔离、可测试性和业务闭环，不为理论并发量
提前引入微服务、Kubernetes、Temporal 或两套数据库访问模型。

## 决策

### Python 后端

- Python 3.12，项目声明 `>=3.12,<3.14`。
- 使用 `pyproject.toml` 和 `src` 布局。
- FastAPI + Pydantic v2 + pydantic-settings。
- SQLAlchemy 2 同步 ORM + psycopg 3；API 使用同步路由，Celery Worker 复用同一会话模型。
- Alembic 管理 PostgreSQL 迁移。
- Celery + Redis 负责异步任务；业务状态不写 Celery result backend。
- 身份令牌使用 PyJWT，密码使用 `pwdlib[argon2]`。
- UUIDv7 通过 `uuid6` 生成，领域代码通过统一 ID 工厂调用。
- 测试使用 pytest；格式和静态检查使用 Ruff、mypy。

### 前端

- Next.js + TypeScript + TipTap。
- pnpm 管理依赖。
- 首版只搭建登录、租户工作台、内容任务和系统管理导航骨架，不在本阶段实现完整编辑器。

### 数据与基础设施

- PostgreSQL 是业务事实源，Redis 仅用于 Broker、缓存、限流和短锁。
- 所有租户业务表携带 `tenant_id`，使用复合外键并启用 RLS。
- 本地环境通过 Docker Compose 提供 PostgreSQL、Redis 和 MinIO。
- CI 执行 Ruff、mypy、pytest、Alembic 迁移检查和前端类型检查。

## 边界

- 单元测试可以使用纯领域对象或 Mock Repository；RLS 和迁移测试必须运行在 PostgreSQL。
- 不使用 SQLite 冒充 PostgreSQL 集成测试。
- 不在 FastAPI Controller、Celery Task 或 LangGraph Node 中直接写跨模块数据库状态。
- 当前仓库没有固定开发者机器上的 Python 路径；本地文档说明如何使用 Python 3.12，CI 使用标准 Python 3.12 镜像。

## 后果

- 同步 SQLAlchemy 降低 API/Worker 共享代码复杂度，当前容量基线足够。
- 若未来 API 存在明确数据库并发瓶颈，可通过 Repository 接口评估迁移异步访问；在有测量数据前不引入。
- Temporal、微服务和独立向量数据库继续保持为明确暂缓项。

