import { Bot, ChevronRight, FileClock, KeyRound, Settings2, Shield, UsersRound, Workflow } from "lucide-react";
import { PermissionGate } from "@/components/permission-gate";
import { ForbiddenState, PageHeader } from "@/components/ui";

const adminSections = [
  { title: "成员与团队", description: "管理成员状态、团队归属与角色分配", icon: UsersRound, permission: "member:view" as const },
  { title: "角色与数据范围", description: "配置功能权限与租户内数据可见范围", icon: Shield, permission: "role:view" as const },
  { title: "工作流模板", description: "配置节点模式、人工介入点和质量门禁", icon: Workflow, permission: "workflow:view" as const },
  { title: "模型策略", description: "配置任务模型路由、备用模型与预算", icon: Bot, permission: "model:view" as const },
  { title: "模型凭证", description: "管理平台托管凭证或租户 BYOK 引用", icon: KeyRound, permission: "model:credential_manage" as const },
  { title: "配额与告警", description: "查看套餐上限并设置团队软硬限制", icon: Settings2, permission: "quota:view" as const },
  { title: "审计日志", description: "追踪配置、内容、审批和导出操作", icon: FileClock, permission: "audit:view" as const },
];

export default function AdminPage() {
  return (
    <div className="page-stack">
      <PageHeader eyebrow="租户设置" title="系统管理" description="管理当前租户的组织、权限和内容生产策略。" />
      <div className="admin-list">
        {adminSections.map((section) => (
          <PermissionGate key={section.title} permission={section.permission}>
            <button className="admin-row" type="button">
              <span className="admin-icon"><section.icon size={19} /></span>
              <span><strong>{section.title}</strong><small>{section.description}</small></span>
              <ChevronRight size={18} aria-hidden="true" />
            </button>
          </PermissionGate>
        ))}
      </div>
      <PermissionGate permission="member:view" invert>
        <ForbiddenState description="你没有查看租户系统设置的权限。" />
      </PermissionGate>
    </div>
  );
}
