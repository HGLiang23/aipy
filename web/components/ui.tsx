"use client";

import { AlertTriangle, Ban, FileQuestion, Inbox, RefreshCw } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import type { StatusTone } from "@/lib/types";

export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <header className="page-header"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{action && <div className="page-actions">{action}</div>}</header>;
}

export function StatusBadge({ tone = "neutral", children }: { tone?: StatusTone; children: ReactNode }) {
  return <span className={`status-badge status-${tone}`}>{children}</span>;
}

export function LoadingState({ rows = 4 }: { rows?: number }) {
  return <div className="loading-state" aria-busy="true" aria-label="正在加载"><div className="skeleton skeleton-title" />{Array.from({ length: rows }, (_, index) => <div className="skeleton skeleton-row" key={index} />)}</div>;
}

export function EmptyState({ title = "暂无数据", description = "当前范围内还没有可显示的内容。", actionLabel, actionHref }: { title?: string; description?: string; actionLabel?: string; actionHref?: string }) {
  return <section className="page-state"><span className="state-icon"><Inbox size={22} /></span><h2>{title}</h2><p>{description}</p>{actionLabel && actionHref && <Link className="button button-secondary" href={actionHref}>{actionLabel}</Link>}</section>;
}

export function ForbiddenState({ description = "你没有访问此页面的权限，请联系租户管理员。" }: { description?: string }) {
  return <section className="page-state"><span className="state-icon state-icon-danger"><Ban size={22} /></span><p className="error-code">403</p><h2>访问受限</h2><p>{description}</p><Link className="button button-secondary" href="/app">返回工作台</Link></section>;
}

export function ConflictState({ onReload }: { onReload?: () => void }) {
  return <section className="conflict-state" role="alert"><AlertTriangle size={20} /><div><h2>内容版本已发生变化</h2><p>服务器上已有更新版本。请重新加载并核对差异，系统不会覆盖你的修改。</p></div><button className="button button-secondary" type="button" onClick={onReload}><RefreshCw size={16} /> 重新加载</button></section>;
}

export function ErrorState({ requestId }: { requestId?: string }) {
  return <section className="page-state"><span className="state-icon state-icon-danger"><FileQuestion size={22} /></span><h2>暂时无法加载</h2><p>服务请求失败，请稍后重试。{requestId ? `追踪 ID：${requestId}` : ""}</p><button className="button button-secondary" type="button"><RefreshCw size={16} /> 重试</button></section>;
}
