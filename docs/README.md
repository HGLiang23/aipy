# AI 内容 SaaS 详细设计

本目录是设计基线与实现现状的合集：`00`–`07` 与 `adr/` 描述方向性设计，
`08-project-structure.md` 描述**代码当前实际长什么样**。两者冲突时，以 `08` 与
`create_app().openapi()` 为准。

## 文档索引

1. [方案总览](./00-solution-overview.md)
2. [领域与数据模型](./01-domain-data-model.md)
3. [工作流状态机](./02-workflow-state-machine.md)
4. [后端架构与 API](./03-backend-architecture-api.md)
5. [前端、系统管理与 RBAC](./04-frontend-admin-rbac.md)
6. [MVP 交付计划](./05-mvp-delivery-plan.md)
7. [ADR-0001: MVP 工程实现基线](./adr/0001-mvp-implementation-baseline.md)
8. [M0 决策闭环](./06-m0-closure.md)
9. [安全威胁模型](./07-security-threat-model.md)
10. [项目结构与功能地图](./08-project-structure.md)（按当前代码逐层说明目录、模块、链路与工程约定）
11. [OpenAPI 3.1 草案](../openapi/openapi.yaml)（**手写草案，路径与实现不一致，不是契约来源**）

## 使用规则

这些文档共同定义已经确认的产品和技术方向。代码不得另行引入冲突的
工作流状态所有者、租户隔离方式或产物版本机制。确需调整时，应先记录
架构决策并完成设计评审。
