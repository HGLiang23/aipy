# ADR-0002: RBAC 表落地与权限来源切换

- 状态：Accepted
- 日期：2026-09-25

## 背景

授权引擎（`AuthorizationService`：权限、数据范围、工作流态、职责分离）早已实现，
但策略来源一直是 `tenant_membership.job_title` 字符串映射——权限不可配置，
新增角色要改代码，租户也无法自定义权限集合。

## 决策

### 1. 三张租户级表

| 表 | 作用 | 关键约束 |
|---|---|---|
| `role` | 租户内角色：`code` / `name` / `is_system` / `status` | `(tenant_id, code)` 唯一；`status ∈ {ACTIVE, INACTIVE}` |
| `role_permission` | 角色 → 权限码（`resource:action`） | `(tenant_id, role_id, permission_code)` 唯一；级联删除 |
| `membership_role` | 成员 → 角色（多对多） | `(tenant_id, membership_id, role_id)` 唯一；双复合外键 |

三张表全部启用 `ENABLE + FORCE ROW LEVEL SECURITY` 及 `tenant_isolation` 策略，
与其他租户表一致。系统预置四个角色：`admin` / `editor` / `reviewer` / `member`，
权限模板定义在 `authorization/infrastructure/role_catalog.py`。

### 2. 权限解析优先级

`SqlAuthorizationPolicyRepository` 按以下顺序解析：

1. 查 `membership_role → role → role_permission`，**只取 `status = 'ACTIVE'` 的角色**，
   多角色权限取并集；
2. 一个角色都没分配时，**回退到 `job_title` 映射**，保证存量数据与未配角色的租户不丢权限；
3. 权限码去重、丢弃格式非法的码（防脏数据让整个策略构造失败）。

### 3. 迁移

`20260925_0006_rbac_tables.py`：建表 + 索引 + RLS + 表/列注释。
约束名遵循 `NAMING_CONVENTION`（`ck_<table>_<name>`、多列唯一约束全列拼接、
`fk_<table>_tenant_id_tenant`），与 ORM 元数据逐项对齐。

## 影响

- 停用角色即刻生效（`Role.status`）；停用成员/租户仍由策略层统一拒绝。
- `allowed_actions` 数据库列仍是死字段，API 不读它，待后续迁移清理。
- 新租户开通流程需要调用 `seed_dev._ensure_default_roles` 等价逻辑预置角色，
  目前仅 seed 脚本覆盖。

## 后续

- 角色/权限管理 API（`role:manage` 权限已在目录中预留）。
- 数据范围收窄：等 content 实体带上 `workspace_id` / `team_id` 后启用
  `WORKSPACE` / `TEAM` 级别的 `DataScopeGrant`。
