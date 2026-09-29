"use client";

import { Activity, Clock3, ListTodo, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useTenantSession } from "@/components/tenant-context";
import { PageHeader, StatusBadge } from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import { useApiList } from "@/lib/use-api";
import type { ContentRunCounts, ContentRunSummary, HumanTaskSummary } from "@/lib/types";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 6) return "夜深了";
  if (hour < 12) return "上午好";
  if (hour < 18) return "下午好";
  return "晚上好";
}

export default function OverviewPage() {
  const session = useTenantSession();
  const [counts, setCounts] = useState<ContentRunCounts | null>(null);
  const { items: contentRuns, loading: runsLoading } = useApiList<ContentRunSummary>("content-runs", { pageSize: 4 });
  const { items: humanTasks, loading: tasksLoading } = useApiList<HumanTaskSummary>("human-tasks", { pageSize: 4 });

  useEffect(() => {
    let alive = true;
    apiClient
      .contentRunCounts()
      .then((value) => { if (alive) setCounts(value); })
      .catch(() => { if (alive) setCounts(null); });
    return () => { alive = false; };
  }, []);

  const metric = (value: number | undefined) => (counts === null ? "—" : String(value ?? 0));

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="概览"
        title={`${greeting()}，${session.user.displayName}`}
        description="关注正在运行的内容任务和需要团队处理的节点。"
      />

      <section className="metric-grid" aria-label="工作台摘要">
        <article className="metric">
          <span className="metric-icon"><Activity size={18} /></span>
          <span>运行中</span>
          <strong>{metric(counts?.running)}</strong>
          <small>共 {counts?.total ?? "—"} 个内容任务</small>
        </article>
        <article className="metric">
          <span className="metric-icon metric-icon-amber"><ListTodo size={18} /></span>
          <span>等待人工</span>
          <strong>{metric(counts?.waiting_human)}</strong>
          <small>{humanTasks.length > 0 ? `最近一条：${humanTasks[0].dueLabel}` : "当前没有到期任务"}</small>
        </article>
        <article className="metric">
          <span className="metric-icon metric-icon-blue"><Clock3 size={18} /></span>
          <span>已完成</span>
          <strong>{metric(counts?.completed)}</strong>
          <small>已暂停 {counts?.paused ?? "—"} 个</small>
        </article>
        <article className="metric">
          <span className="metric-icon metric-icon-neutral"><TriangleAlert size={18} /></span>
          <span>需要处理</span>
          <strong>{metric(counts?.failed)}</strong>
          <small>执行失败或人工介入的任务</small>
        </article>
      </section>

      <section className="split-grid">
        <div className="section-block">
          <div className="section-heading">
            <div>
              <h2>最近内容任务</h2>
              <p>跨品牌的最新执行情况</p>
            </div>
            <Link href="/app/content">查看全部</Link>
          </div>
          <div className="compact-list">
            {runsLoading && <p className="table-summary">加载中…</p>}
            {!runsLoading && contentRuns.length === 0 && <p className="table-summary">还没有内容任务，去「内容任务」新建一个。</p>}
            {contentRuns.map((run) => (
              <Link className="compact-row" href={`/app/content/${run.id}`} key={run.id}>
                <div>
                  <strong>{run.title}</strong>
                  <span>{run.brand} · {run.stageLabel}</span>
                </div>
                <StatusBadge tone={run.tone}>{run.statusLabel}</StatusBadge>
              </Link>
            ))}
          </div>
        </div>

        <div className="section-block">
          <div className="section-heading">
            <div>
              <h2>待处理人工任务</h2>
              <p>按任务序号排序的处理队列</p>
            </div>
            <Link href="/app/human-tasks">处理队列</Link>
          </div>
          <div className="compact-list">
            {tasksLoading && <p className="table-summary">加载中…</p>}
            {!tasksLoading && humanTasks.length === 0 && <p className="table-summary">当前没有待处理的人工任务。</p>}
            {humanTasks.map((task) => (
              <div className="compact-row" key={task.id}>
                <div>
                  <strong>{task.title}</strong>
                  <span className="inline-meta"><Clock3 size={14} /> {task.dueLabel} · {task.brand}</span>
                </div>
                <StatusBadge tone={task.priority === "高" ? "danger" : "neutral"}>{task.priority}</StatusBadge>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
