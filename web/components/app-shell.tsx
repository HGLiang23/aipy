"use client";

import { BookOpenText, ChevronDown, FileStack, LayoutDashboard, Library, ListChecks, LogOut, Menu, Search, Settings, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { PermissionGate } from "@/components/permission-gate";
import { useTenantSession } from "@/components/tenant-context";
import type { PermissionCode } from "@/lib/types";

const navigation: Array<{ href: string; label: string; icon: typeof LayoutDashboard; permission?: PermissionCode }> = [
  { href: "/app", label: "概览", icon: LayoutDashboard },
  { href: "/app/content", label: "内容任务", icon: FileStack, permission: "content:view" },
  { href: "/app/human-tasks", label: "人工任务", icon: ListChecks, permission: "review:view" },
  { href: "/app/materials", label: "素材库", icon: Library, permission: "source:view" },
  { href: "/app/admin", label: "系统管理", icon: Settings, permission: "member:view" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const session = useTenantSession();
  const [open, setOpen] = useState(false);

  return (
    <div className="workspace-shell">
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
        <div className="sidebar-brand">
          <span className="brand-mark brand-mark-small">A</span><strong>AIPY</strong>
          <button className="mobile-close" onClick={() => setOpen(false)} aria-label="关闭导航"><X size={19} /></button>
        </div>
        <button className="tenant-switcher" type="button">
          <span><small>当前租户</small><strong>{session.tenant.name}</strong></span>
          <ChevronDown size={16} aria-hidden="true" />
        </button>
        <nav className="main-nav" aria-label="主导航">
          <p>工作台</p>
          {navigation.map((item) => {
            const active = item.href === "/app" ? pathname === item.href : pathname.startsWith(item.href);
            const entry = (
              <Link className={active ? "nav-link nav-link-active" : "nav-link"} href={item.href} onClick={() => setOpen(false)}>
                <item.icon size={18} /><span>{item.label}</span>{item.label === "人工任务" && <em>3</em>}
              </Link>
            );
            return item.permission ? <PermissionGate permission={item.permission} key={item.href}>{entry}</PermissionGate> : <span key={item.href}>{entry}</span>;
          })}
        </nav>
        <div className="sidebar-footer"><Link className="nav-link" href="/login"><LogOut size={18} /><span>退出演示</span></Link></div>
      </aside>
      {open && <button className="sidebar-backdrop" aria-label="关闭导航" onClick={() => setOpen(false)} />}

      <div className="workspace-main">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setOpen(true)} aria-label="打开导航"><Menu size={20} /></button>
          <div className="topbar-context"><BookOpenText size={18} /><span>{session.workspace.name}</span></div>
          <div className="topbar-actions">
            <button className="icon-button" aria-label="搜索" title="搜索"><Search size={18} /></button>
            <span className="avatar" aria-hidden="true">林</span>
            <div className="user-name"><strong>{session.user.displayName}</strong><small>{session.user.roleLabel}</small></div>
          </div>
        </header>
        <main className="content-area">{children}</main>
      </div>
    </div>
  );
}
