"use client";

import { Search, UserRoundCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { RowActions } from "@/components/row-actions";
import { ActionNoticeBar, PageHeader, StatusBadge } from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import type { ListQuery } from "@/lib/api-client";
import { useResourceAction } from "@/lib/use-actions";
import { useApiList, useDebouncedValue } from "@/lib/use-api";
import type { HumanTaskCounts, HumanTaskSummary, MemberSummary } from "@/lib/types";

/** Each tab is a real server-side filter; the badge shows the matching total. */
const TABS: Array<{ key: keyof HumanTaskCounts; label: string; query: ListQuery }> = [
  { key: "mine", label: "我的任务", query: { mine: true } },
  { key: "open", label: "待领取", query: { status: "OPEN" } },
  { key: "team", label: "团队任务", query: {} },
  { key: "completed", label: "已完成", query: { status: "COMPLETED" } },
];

export default function HumanTasksPage() {
  const [tab, setTab] = useState<keyof HumanTaskCounts>("mine");
  const [term, setTerm] = useState("");
  const [members, setMembers] = useState<MemberSummary[]>([]);
  const [counts, setCounts] = useState<HumanTaskCounts | null>(null);

  const search = useDebouncedValue(term);
  const activeTab = TABS.find((item) => item.key === tab) ?? TABS[0];
  const { page, items: tasks, loading, error, reload, replaceRow } = useApiList<HumanTaskSummary>("human-tasks", {
    pageSize: 50,
    q: search,
    ...activeTab.query,
  });
  const actions = useResourceAction<HumanTaskSummary>("human-tasks", replaceRow);

  useEffect(() => {
    apiClient.listOrganizationMembers().then(setMembers).catch(() => setMembers([]));
  }, []);

  // ``page`` only changes when a request settles, so this refreshes the badges
  // after every action without polling.
  useEffect(() => {
    let alive = true;
    apiClient
      .humanTaskCounts()
      .then((value) => { if (alive) setCounts(value); })
      .catch(() => { if (alive) setCounts(null); });
    return () => { alive = false; };
  }, [page]);

  return (
    <div className="page-stack">
      <PageHeader eyebrow="内容生产" title="人工任务" description="集中领取、审核和转派需要人工处理的工作流节点。" />
      <div className="tabs" role="tablist" aria-label="人工任务范围">
        {TABS.map((item) => (
          <button
            key={item.key}
            className={item.key === tab ? "tab tab-active" : "tab"}
            role="tab"
            aria-selected={item.key === tab}
            type="button"
            onClick={() => setTab(item.key)}
          >
            {item.label}{counts ? <span>{counts[item.key]}</span> : null}
          </button>
        ))}
      </div>
      <div className="toolbar">
        <label className="search-field">
          <Search size={17} aria-hidden="true" />
          <span className="sr-only">搜索人工任务</span>
          <input placeholder="搜索任务标题、品牌或任务 ID" value={term} onChange={(event) => setTerm(event.target.value)} />
        </label>
      </div>

      {actions.notice && <ActionNoticeBar notice={actions.notice} onClear={actions.clearNotice} onReload={reload} />}

      {loading && <p className="table-summary">加载中…</p>}
      {error && <p className="table-summary">{error}</p>}
      {!loading && !error && tasks.length === 0 && <p className="table-summary">该范围下没有人工任务。</p>}
      <div className="task-list">
        {tasks.map((task) => (
          <article className="task-row" key={task.id}>
            <div className="task-kind"><UserRoundCheck size={18} /></div>
            <div className="task-main">
              <div>
                <StatusBadge tone={task.priority === "高" ? "danger" : "neutral"}>{task.priority}优先级</StatusBadge>
                <span>{task.type}</span>
                {task.statusLabel && <StatusBadge tone="neutral">{task.statusLabel}</StatusBadge>}
              </div>
              <h2>{task.title}</h2>
              <p>{task.reason}</p>
              <small>{task.brand} · {task.owner} · {task.dueLabel}</small>
            </div>
            <RowActions
              actions={task.allowed_actions}
              pending={actions.pendingId === task.id}
              members={members}
              onRun={(action, assigneeId) => actions.run(task, action, assigneeId)}
            />
          </article>
        ))}
      </div>
    </div>
  );
}
