"use client";

import { useEffect, useState } from "react";
import { Layers, Rocket } from "lucide-react";
import { PermissionGate } from "@/components/permission-gate";
import { PageHeader, StatusBadge } from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import type { StatusTone, WorkflowNode, WorkflowTemplateDetail, WorkflowTemplateSummary } from "@/lib/types";

const categoryLabel: Record<string, string> = { SYSTEM: "系统预设", TENANT: "租户自定义" };
const statusTone: Record<string, StatusTone> = {
  DRAFT: "warning",
  PUBLISHED: "success",
  ARCHIVED: "neutral",
};
const modeLabel: Record<string, string> = {
  AUTO_CONTINUE: "自动继续",
  AUTO_REVIEW: "自动后审",
  MANUAL: "人工",
  SKIP: "跳过",
  DISABLED: "禁用",
};

export default function WorkflowTemplatesPage() {
  const [templates, setTemplates] = useState<WorkflowTemplateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<WorkflowTemplateDetail | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiClient
      .listWorkflowTemplates()
      .then((p) => setTemplates(p.items))
      .catch(() => setError("加载失败，请稍后重试"))
      .finally(() => setLoading(false));
  }, []);

  async function openTemplate(id: string) {
    try {
      setSelected(await apiClient.getWorkflowTemplate(id));
    } catch {
      setSelected(null);
    }
  }

  async function publish(id: string) {
    setBusy(true);
    try {
      const updated = await apiClient.publishWorkflowTemplate(id);
      setSelected(updated);
      setTemplates((prev) =>
        prev.map((t) => (t.id === id ? { ...t, status: updated.status, currentVersion: updated.currentVersion } : t)),
      );
    } catch {
      setError("发布失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="组织与权限"
        title="工作流模板"
        description="查看系统预设与租户自定义模板，检查节点执行模式与质量门禁。"
      />
      {loading && <p className="table-summary">加载中…</p>}
      {error && <p className="table-summary">{error}</p>}
      <div className="split-layout">
        <table className="data-table">
          <thead>
            <tr>
              <th>模板</th>
              <th>类别</th>
              <th>状态</th>
              <th>节点数</th>
              <th>当前版本</th>
            </tr>
          </thead>
          <tbody>
            {templates.map((t) => (
              <tr
                key={t.id}
                className={selected?.id === t.id ? "row-selected" : ""}
                onClick={() => openTemplate(t.id)}
                style={{ cursor: "pointer" }}
              >
                <td>
                  <strong>{t.name}</strong>
                  <small className="muted">{t.code}</small>
                </td>
                <td>{categoryLabel[t.category] ?? t.category}</td>
                <td><StatusBadge tone={statusTone[t.status] ?? "neutral"}>{t.status}</StatusBadge></td>
                <td>{t.nodeCount}</td>
                <td>{t.currentVersion ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <aside className="detail-panel">
          {selected ? (
            <>
              <div className="detail-head">
                <Layers size={18} />
                <div>
                  <strong>{selected.name}</strong>
                  <small className="muted">{selected.description ?? "无说明"}</small>
                </div>
              </div>
              <div className="toolbar">
                <PermissionGate permission="workflow:configure">
                  <button
                    type="button"
                    className="primary-button"
                    disabled={busy || !selected.allowed_actions.includes("publish")}
                    onClick={() => publish(selected.id)}
                  >
                    <Rocket size={15} /> 发布版本
                  </button>
                </PermissionGate>
                {!selected.allowed_actions.includes("publish") && (
                  <span className="muted">已发布模板不支持在 MVP 中重复发布</span>
                )}
              </div>
              <ol className="node-list">
                {selected.nodes.map((n: WorkflowNode) => (
                  <li key={n.node_key}>
                    <span className="node-seq">{n.sequence_no}</span>
                    <div>
                      <strong>{n.title}</strong>
                      <small className="muted">
                        {modeLabel[n.execution_mode] ?? n.execution_mode}
                        {n.quality_threshold ? ` · 质量≥${n.quality_threshold}` : ""}
                        {` · 重试${n.max_attempts}`}
                      </small>
                    </div>
                  </li>
                ))}
              </ol>
            </>
          ) : (
            <p className="table-summary">从左侧选择一个模板查看节点配置</p>
          )}
        </aside>
      </div>
      {!loading && templates.length === 0 && (
        <div className="table-summary">暂无工作流模板</div>
      )}
    </div>
  );
}
