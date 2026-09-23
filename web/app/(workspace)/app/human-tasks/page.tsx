"use client";

import { CheckCircle2, Filter, UserRoundCheck } from "lucide-react";
import { PageHeader, StatusBadge } from "@/components/ui";
import { useApiList } from "@/lib/use-api";
import type { HumanTaskSummary } from "@/lib/types";

export default function HumanTasksPage() {
  const { page, loading, error } = useApiList<HumanTaskSummary>("human-tasks");
  const tasks = page?.items ?? [];

  return (
    <div className="page-stack">
      <PageHeader eyebrow="内容生产" title="人工任务" description="集中领取、审核和转派需要人工处理的工作流节点。" />
      <div className="tabs" role="tablist" aria-label="人工任务范围">
        <button className="tab tab-active" role="tab" aria-selected="true">我的任务 <span>{tasks.length}</span></button>
        <button className="tab" role="tab" aria-selected="false">待领取 <span>2</span></button>
        <button className="tab" role="tab" aria-selected="false">团队任务 <span>7</span></button>
        <button className="tab" role="tab" aria-selected="false">已完成</button>
      </div>
      <div className="toolbar toolbar-end">
        <button className="button button-secondary" type="button"><Filter size={16} /> 筛选</button>
      </div>
      {loading && <p className="table-summary">加载中…</p>}
      {error && <p className="table-summary">{error}</p>}
      <div className="task-list">
        {tasks.map((task) => (
          <article className="task-row" key={task.id}>
            <div className="task-kind"><UserRoundCheck size={18} /></div>
            <div className="task-main">
              <div><StatusBadge tone={task.priority === "高" ? "danger" : "neutral"}>{task.priority}优先级</StatusBadge><span>{task.type}</span></div>
              <h2>{task.title}</h2>
              <p>{task.reason}</p>
              <small>{task.brand} · {task.owner} · {task.dueLabel}</small>
            </div>
            <button className="button button-primary" type="button"><CheckCircle2 size={16} /> 处理</button>
          </article>
        ))}
      </div>
    </div>
  );
}
