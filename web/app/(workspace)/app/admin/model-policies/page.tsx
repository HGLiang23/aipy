"use client";

import { useCallback, useEffect, useState } from "react";
import { Bot, Plus, Save, Trash2 } from "lucide-react";
import { PermissionGate } from "@/components/permission-gate";
import { PageHeader, StatusBadge } from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import type { ModelCatalogItem, ModelRoutePolicyDetail, ModelRoutePolicySummary, StatusTone } from "@/lib/types";

const TASK_TYPES = [
  { code: "BRIEF", label: "选题简报" },
  { code: "OUTLINE_BUILD", label: "大纲构建" },
  { code: "DRAFT_WRITE", label: "正文写作" },
  { code: "FACT_CHECK", label: "事实核查" },
  { code: "PLATFORM_ADAPT", label: "平台适配" },
];

const statusTone: Record<string, StatusTone> = { ACTIVE: "success", DISABLED: "neutral" };

interface DraftCandidate {
  model_definition_id: string;
  temperature: number;
  max_output_tokens: number;
  allowed_for_publish: boolean;
}

export default function ModelPoliciesPage() {
  const [policies, setPolicies] = useState<ModelRoutePolicySummary[]>([]);
  const [catalog, setCatalog] = useState<ModelCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [taskType, setTaskType] = useState<string>(TASK_TYPES[0].code);
  const [detail, setDetail] = useState<ModelRoutePolicyDetail | null>(null);
  const [draft, setDraft] = useState<{ name: string; daily_cost_limit: number | null; per_call_timeout_seconds: number; status: "ACTIVE" | "DISABLED"; candidates: DraftCandidate[] }>(
    { name: "", daily_cost_limit: null, per_call_timeout_seconds: 60, status: "ACTIVE", candidates: [] },
  );

  const loadPolicies = useCallback(() => {
    apiClient.listModelRoutePolicies().then(setPolicies).catch(() => setError("加载失败"));
  }, []);

  useEffect(() => {
    apiClient.listModelCatalog().then(setCatalog).catch(() => setCatalog([]));
    loadPolicies();
    setLoading(false);
  }, [loadPolicies]);

  const loadPolicy = useCallback(async (tt: string) => {
    try {
      const d = await apiClient.getModelRoutePolicy(tt);
      setDetail(d);
      setDraft({
        name: d.name,
        daily_cost_limit: d.dailyCostLimit,
        per_call_timeout_seconds: d.perCallTimeoutSeconds,
        status: d.status,
        candidates: d.candidates.map((c) => ({
          model_definition_id: c.modelDefinitionId,
          temperature: c.temperature,
          max_output_tokens: c.maxOutputTokens,
          allowed_for_publish: c.allowedForPublish,
        })),
      });
    } catch {
      // No policy yet for this task type -> start a fresh draft.
      setDetail(null);
      setDraft({
        name: TASK_TYPES.find((t) => t.code === tt)?.label ?? tt,
        daily_cost_limit: null,
        per_call_timeout_seconds: 60,
        status: "ACTIVE",
        candidates: [],
      });
    }
  }, []);

  useEffect(() => {
    loadPolicy(taskType);
  }, [taskType, loadPolicy]);

  function addCandidate() {
    setDraft((d) => ({
      ...d,
      candidates: [...d.candidates, { model_definition_id: catalog[0]?.id ?? "", temperature: 0.7, max_output_tokens: 2048, allowed_for_publish: false }],
    }));
  }

  function updateCandidate(idx: number, patch: Partial<DraftCandidate>) {
    setDraft((d) => ({
      ...d,
      candidates: d.candidates.map((c, i) => (i === idx ? { ...c, ...patch } : c)),
    }));
  }

  function removeCandidate(idx: number) {
    setDraft((d) => ({ ...d, candidates: d.candidates.filter((_, i) => i !== idx) }));
  }

  async function save() {
    if (!draft.name || draft.candidates.length === 0) {
      setError("请填写策略名称并至少配置一个候选模型");
      return;
    }
    setBusy(true);
    try {
      await apiClient.upsertModelRoutePolicy(taskType, draft);
      setError(null);
      loadPolicies();
      await loadPolicy(taskType);
    } catch {
      setError("保存失败，请检查候选模型是否有效");
    } finally {
      setBusy(false);
    }
  }

  const modelName = (id: string) => catalog.find((m) => m.id === id)?.displayName ?? id.slice(0, 8);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="组织与权限"
        title="模型策略"
        description="按任务类型配置主模型、降级模型、温度、最大输出与每日成本上限。"
      />
      {error && <p className="table-summary">{error}</p>}
      {loading && <p className="table-summary">加载中…</p>}
      <div className="split-layout">
        <table className="data-table">
          <thead>
            <tr>
              <th>任务类型</th>
              <th>策略名称</th>
              <th>候选数</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {TASK_TYPES.map((t) => {
              const p = policies.find((x) => x.taskType === t.code);
              return (
                <tr
                  key={t.code}
                  className={taskType === t.code ? "row-selected" : ""}
                  onClick={() => setTaskType(t.code)}
                  style={{ cursor: "pointer" }}
                >
                  <td><strong>{t.label}</strong><small className="muted">{t.code}</small></td>
                  <td>{p?.name ?? <span className="muted">未配置</span>}</td>
                  <td>{p?.candidateCount ?? 0}</td>
                  <td>
                    {p ? <StatusBadge tone={statusTone[p.status] ?? "neutral"}>{p.status}</StatusBadge> : <span className="muted">-</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <aside className="detail-panel">
          <div className="detail-head">
            <Bot size={18} />
            <div>
              <strong>{TASK_TYPES.find((t) => t.code === taskType)?.label}</strong>
              <small className="muted">{detail ? "已配置" : "尚未配置，可直接创建"}</small>
            </div>
          </div>

          <PermissionGate permission="model:configure">
            <div className="policy-form">
              <label>
                策略名称
                <input value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
              </label>
              <div className="policy-row">
                <label>
                  每日成本上限
                  <input
                    type="number" min={0} step={0.01}
                    value={draft.daily_cost_limit ?? ""}
                    placeholder="不限"
                    onChange={(e) => setDraft((d) => ({ ...d, daily_cost_limit: e.target.value ? Number(e.target.value) : null }))}
                  />
                </label>
                <label>
                  单次超时(秒)
                  <input
                    type="number" min={1}
                    value={draft.per_call_timeout_seconds}
                    onChange={(e) => setDraft((d) => ({ ...d, per_call_timeout_seconds: Number(e.target.value) }))}
                  />
                </label>
              </div>
            </div>

            <div className="candidate-head">
              <span>候选模型（按顺序降级）</span>
              <button type="button" className="icon-button" onClick={addCandidate} title="添加候选">
                <Plus size={16} />
              </button>
            </div>
            <ol className="node-list">
              {draft.candidates.map((c, idx) => (
                <li key={idx}>
                  <span className="node-seq">{idx + 1}</span>
                  <div className="candidate-body">
                    <select
                      value={c.model_definition_id}
                      onChange={(e) => updateCandidate(idx, { model_definition_id: e.target.value })}
                    >
                      {catalog.map((m) => (
                        <option key={m.id} value={m.id}>{m.displayName}（{m.modelCode}）</option>
                      ))}
                    </select>
                    <div className="policy-row">
                      <label>
                        温度
                        <input type="number" min={0} max={1} step={0.05} value={c.temperature}
                          onChange={(e) => updateCandidate(idx, { temperature: Number(e.target.value) })} />
                      </label>
                      <label>
                        最大输出
                        <input type="number" min={1} value={c.max_output_tokens}
                          onChange={(e) => updateCandidate(idx, { max_output_tokens: Number(e.target.value) })} />
                      </label>
                    </div>
                    <label className="checkbox-row">
                      <input type="checkbox" checked={c.allowed_for_publish}
                        onChange={(e) => updateCandidate(idx, { allowed_for_publish: e.target.checked })} />
                      允许用于对外发布
                    </label>
                    <small className="muted">{modelName(c.model_definition_id)}</small>
                  </div>
                  <button type="button" className="icon-button" onClick={() => removeCandidate(idx)} title="移除">
                    <Trash2 size={15} />
                  </button>
                </li>
              ))}
            </ol>

            <button type="button" className="primary-button" disabled={busy} onClick={save}>
              <Save size={15} /> 保存策略
            </button>
          </PermissionGate>
        </aside>
      </div>
    </div>
  );
}
