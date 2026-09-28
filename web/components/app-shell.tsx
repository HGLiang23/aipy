"use client";

import { BookOpenText, ChevronDown, FileStack, LayoutDashboard, Library, ListChecks, LogOut, Menu, Search, Settings, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PermissionGate } from "@/components/permission-gate";
import { useTenantSession } from "@/components/tenant-context";
import { apiClient } from "@/lib/api-client";
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
  const router = useRouter();
  const session = useTenantSession();
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [pending, setPending] = useState<number | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  // Refresh the badge on every navigation: it is a real count, not a decoration.
  useEffect(() => {
    let alive = true;
    apiClient
      .humanTaskCounts()
      .then((counts) => { if (alive) setPending(counts.pending); })
      .catch(() => { if (alive) setPending(null); });
    return () => { alive = false; };
  }, [pathname]);

  async function logout() {
    setSigningOut(true);
    try {
      await apiClient.logout();
    } catch {
      // Clearing the cookie is best-effort: still leave the workspace either way.
    }
    router.replace("/login");
  }

  function search(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = term.trim();
    router.push(value ? `/app/content?q=${encodeURIComponent(value)}` : "/app/content");
  }

  return (
    <div className="workspace-shell">
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
        <div className="sidebar-brand">
          <span className="brand-mark brand-mark-small">A</span><strong>AIPY</strong>
          <button className="mobile-close" onClick={() => setOpen(false)} aria-label="关闭导航"><X size={19} /></button>
        </div>
        <button
          className="tenant-switcher"
          type="button"
          disabled
          title="登录账号当前只属于一个租户，切换能力尚未开放"
        >
          <span><small>当前租户</small><strong>{session.tenant.name}</strong></span>
          <ChevronDown size={16} aria-hidden="true" />
        </button>
        <nav className="main-nav" aria-label="主导航">
          <p>工作台</p>
          {navigation.map((item) => {
            const active = item.href === "/app" ? pathname === item.href : pathname.startsWith(item.href);
            const entry = (
              <Link className={active ? "nav-link nav-link-active" : "nav-link"} href={item.href} onClick={() => setOpen(false)}>
                <item.icon size={18} /><span>{item.label}</span>
                {item.label === "人工任务" && pending !== null && pending > 0 && <em>{pending}</em>}
              </Link>
            );
            return item.permission ? <PermissionGate permission={item.permission} key={item.href}>{entry}</PermissionGate> : <span key={item.href}>{entry}</span>;
          })}
        </nav>
        <div className="sidebar-footer">
          <button className="nav-link nav-link-button" type="button" onClick={logout} disabled={signingOut}>
            <LogOut size={18} /><span>{signingOut ? "正在退出…" : "退出登录"}</span>
          </button>
        </div>
      </aside>
      {open && <button className="sidebar-backdrop" aria-label="关闭导航" onClick={() => setOpen(false)} />}

      <div className="workspace-main">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setOpen(true)} aria-label="打开导航"><Menu size={20} /></button>
          <div className="topbar-context"><BookOpenText size={18} /><span>{session.workspace.name}</span></div>
          <div className="topbar-actions">
            <form className="topbar-search" role="search" onSubmit={search}>
              <Search size={15} aria-hidden="true" />
              <input aria-label="搜索内容任务" placeholder="搜索内容任务" value={term} onChange={(event) => setTerm(event.target.value)} />
            </form>
            <span className="avatar" aria-hidden="true">{session.user.displayName.slice(0, 1)}</span>
            <div className="user-name"><strong>{session.user.displayName}</strong><small>{session.user.roleLabel}</small></div>
          </div>
        </header>
        <main className="content-area">{children}</main>
      </div>
    </div>
  );
}
