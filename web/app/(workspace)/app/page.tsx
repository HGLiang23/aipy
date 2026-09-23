"use client";

import { Activity, Clock3, FileText, ListTodo, TrendingUp } from "lucide-react";
import { PageHeader, StatusBadge } from "@/components/ui";
import { useApiList } from "@/lib/use-api";
import type { ContentRunSummary, HumanTaskSummary } from "@/lib/types";

const USAGE = { used: 37, limit: 80, resetLabel: "明日 00:00" };

export default function OverviewPage() {
  const { page: runsPage, loading: runsLoading } = useApiList<ContentRunSummary>("content-runs");
  const { page: tasksPage, loading: tasksLoading } = useApiList<HumanTaskSummary>("human-tasks");

  const contentRuns = runsPage?.items ?? [];
  const humanTasks = tasksPage?.items ?? [];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="概览"
        title="上午好，林编辑"
        description="关注正在运行的内容任务和需要团队处理的节点。"
      />

      <section className="metric-grid" aria-label="工作台摘要">
        <article className="metric">
          <span className="metric-icon"><Activity size={18} /></span>
          <span>运行中</span>
          <strong>12</strong>
          <small>2 个任务等待外部模型</small>
        </article>
        <article className="metric">
          <span className="metric-icon metric-icon-amber"><ListTodo size={18} /></span>
          <span>待人工处理</span>
          <strong>{humanTasks.length}</strong>
          <small>1 项将在今天到期</small>
        </article>
        <article className="metric">
          <span className="metric-icon metric-icon-blue"><FileText size={18} /></span>
          <span>今日已完成</span>
          <strong>18</strong>
          <small>公众号 11 · 小红书 7</small>
        </article>
        <article className="metric">
          <span className="metric-icon metric-icon-neutral"><TrendingUp size={18} /></span>
          <span>生成配额</span>
          <strong>{USAGE.used}/{USAGE.limit}</strong>
          <small>{USAGE.resetLabel}重置</small>
        </article>
      </section>

      <section className="split-grid">
        <div className="section-block">
          <div className="section-heading">
            <div>
              <h2>最近内容任务</h2>
              <p>跨品牌的最新执行情况</p>
            </div>
            <a href="/app/content">查看全部</a>
          </div>
          <div className="compact-list">
            {runsLoading && <p className="table-summary">加载中…</p>}
            {contentRuns.slice(0, 4).map((run) => (
              <a className="compact-row" href={`/app/content/${run.id}`} key={run.id}>
                <div>
                  <strong>{run.title}</strong>
                  <span>{run.brand} · {run.stageLabel}</span>
                </div>
                <StatusBadge tone={run.tone}>{run.statusLabel}</StatusBadge>
              </a>
            ))}
          </div>
        </div>

        <div className="section-block">
          <div className="section-heading">
            <div>
              <h2>即将到期</h2>
              <p>按截止时间排序的人工任务</p>
            </div>
            <a href="/app/human-tasks">处理队列</a>
          </div>
          <div className="compact-list">
            {tasksLoading && <p className="table-summary">加载中…</p>}
            {humanTasks.slice(0, 4).map((task) => (
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
