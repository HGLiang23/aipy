import { Bot, ChevronRight, FileClock, KeyRound, Settings2, Shield, UsersRound, Workflow } from "lucide-react";
import Link from "next/link";
import { PermissionGate } from "@/components/permission-gate";
import { ForbiddenState, PageHeader } from "@/components/ui";

const adminSections = [
  { title: "成员与团队", description: "管理成员状态、团队归属与角色分配", icon: UsersRound, href: "/app/admin/members", permission: "member:view" as const },
  { title: "角色与数据范围", description: "配置功能权限与租户内数据可见范围", icon: Shield, href: "/app/admin/roles", permission: "role:view" as const },
  { title: "工作流模板", description: "配置节点模式、人工介入点和质量门禁", icon: Workflow, href: "/app/admin/workflow-templates", permission: "workflow:view" as const },
  { title: "模型策略", description: "配置任务模型路由、备用模型与预算", icon: Bot, href: "/app/admin/model-policies", permission: "model:view" as const },
  { title: "模型凭证", description: "管理平台托管凭证或租户 BYOK 引用", icon: KeyRound, href: "/app/admin/model-credentials", permission: "model:credential_manage" as const },
  { title: "配额与告警", description: "查看套餐上限并设置团队软硬限制", icon: Settings2, href: "/app/admin/quotas", permission: "quota:view" as const },
  { title: "审计日志", description: "追踪配置、内容、审批和导出操作", icon: FileClock, href: "/app/admin/audit-logs", permission: "audit:view" as const },
];

export default function AdminPage() {
  return (
    <div className="page-stack">
      <PageHeader eyebrow="租户设置" title="系统管理" description="管理当前租户的组织、权限和内容生产策略。" />
      <div className="admin-list">
        {adminSections.map((section) => (
          <PermissionGate key={section.title} permission={section.permission}>
            {section.href ? (
              <Link className="admin-row" href={section.href}>
                <span className="admin-icon"><section.icon size={19} /></span>
                <span><strong>{section.title}</strong><small>{section.description}</small></span>
                <ChevronRight size={18} aria-hidden="true" />
              </Link>
            ) : (
              <div className="admin-row admin-row-disabled" aria-disabled="true">
                <span className="admin-icon"><section.icon size={19} /></span>
                <span><strong>{section.title}</strong><small>{section.description}（开发中）</small></span>
                <ChevronRight size={18} aria-hidden="true" />
              </div>
            )}
          </PermissionGate>
        ))}
      </div>
      <PermissionGate permission="member:view" invert>
        <ForbiddenState description="你没有查看租户系统设置的权限。" />
      </PermissionGate>
    </div>
  );
}
