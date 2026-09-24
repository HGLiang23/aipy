"use client";

import { useCallback, useEffect, useState } from "react";
import { FileClock, Filter } from "lucide-react";
import { PageHeader, StatusBadge } from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import type { Page } from "@/lib/api-client";
import type { AuditEventDetail, AuditEventSummary, StatusTone } from "@/lib/types";

const resultTone: Record<string, StatusTone> = {
  SUCCESS: "success",
  FAILURE: "danger",
  DENIED: "warning",
};

const actionLabel: Record<string, string> = {
  "member.update": "更新成员",
  "role.update": "更新角色",
  "workflow.publish": "发布工作流模板",
};

function fmt(ts: string): string {
  if (!ts) return "-";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString("zh-CN", { hour12: false });
}

export default function AuditLogsPage() {
  const [filters, setFilters] = useState({ action: "", result: "" });
  const [page, setPage] = useState<Page<AuditEventSummary> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<AuditEventDetail | null>(null);

  const events = page?.items ?? [];

  const load = useCallback(() => {
    setLoading(true);
    const query = new URLSearchParams(
      Object.entries(filters).filter(([, v]) => v) as [string, string][],
    );
    apiClient
      .listAuditLogs(query)
      .then((data) => {
        setPage(data);
        setError(null);
      })
      .catch(() => setError("加载失败，请稍后重试"))
      .finally(() => setLoading(false));
  }, [filters]);

  useEffect(() => {
    load();
  }, [load]);

  async function openEvent(id: string) {
    try {
      setSelected(await apiClient.getAuditLog(id));
    } catch {
      setSelected(null);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="组织与权限"
        title="审计日志"
        description="追踪配置、审批、发布和导出操作。审计记录只追加、不可修改。"
      />
      <form className="toolbar" onSubmit={(e) => e.preventDefault()}>
        <label className="search-field">
          <Filter size={16} />
          <span className="sr-only">动作</span>
          <select
            value={filters.action}
            onChange={(e) => setFilters((f) => ({ ...f, action: e.target.value }))}
          >
            <option value="">全部动作</option>
            <option value="member.update">更新成员</option>
            <option value="role.update">更新角色</option>
            <option value="workflow.publish">发布工作流模板</option>
          </select>
        </label>
        <label className="search-field">
          <span className="sr-only">结果</span>
          <select
            value={filters.result}
            onChange={(e) => setFilters((f) => ({ ...f, result: e.target.value }))}
          >
            <option value="">全部结果</option>
            <option value="SUCCESS">成功</option>
            <option value="FAILURE">失败</option>
            <option value="DENIED">被拒绝</option>
          </select>
        </label>
      </form>
      {loading && <p className="table-summary">加载中…</p>}
      {error && <p className="table-summary">{error}</p>}
      <div className="split-layout">
        <table className="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>操作者</th>
              <th>动作</th>
              <th>资源</th>
              <th>结果</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr
                key={e.id}
                className={selected?.id === e.id ? "row-selected" : ""}
                onClick={() => openEvent(e.id)}
                style={{ cursor: "pointer" }}
              >
                <td>{fmt(e.occurredAt)}</td>
                <td>{e.actorLabel ?? "系统"}</td>
                <td>{actionLabel[e.action] ?? e.action}</td>
                <td>
                  {e.resourceType}
                  {e.resourceId ? <small className="muted"> #{e.resourceId.slice(0, 8)}</small> : null}
                </td>
                <td><StatusBadge tone={resultTone[e.result] ?? "neutral"}>{e.result}</StatusBadge></td>
              </tr>
            ))}
          </tbody>
        </table>

        <aside className="detail-panel">
          {selected ? (
            <>
              <div className="detail-head">
                <FileClock size={18} />
                <div>
                  <strong>{actionLabel[selected.action] ?? selected.action}</strong>
                  <small className="muted">{fmt(selected.occurredAt)}</small>
                </div>
              </div>
              <dl className="definition-list">
                <dt>操作者</dt><dd>{selected.actorLabel ?? "系统"}（{selected.actorType}）</dd>
                <dt>资源</dt><dd>{selected.resourceType} {selected.resourceId ?? "-"}</dd>
                <dt>结果</dt><dd>{selected.result}</dd>
                <dt>原因</dt><dd>{selected.reason ?? "-"}</dd>
                <dt>请求 ID</dt><dd>{selected.requestId ?? "-"}</dd>
              </dl>
              {(selected.beforeData || selected.afterData) ? (
                <div className="audit-diff">
                  {selected.beforeData && (
                    <div>
                      <span className="muted">变更前</span>
                      <pre>{JSON.stringify(selected.beforeData, null, 2)}</pre>
                    </div>
                  )}
                  {selected.afterData && (
                    <div>
                      <span className="muted">变更后</span>
                      <pre>{JSON.stringify(selected.afterData, null, 2)}</pre>
                    </div>
                  )}
                </div>
              ) : null}
            </>
          ) : (
            <p className="table-summary">从左侧选择一条审计记录查看详情</p>
          )}
        </aside>
      </div>
      {!loading && events.length === 0 && (
        <div className="table-summary">暂无审计记录</div>
      )}
    </div>
  );
}
