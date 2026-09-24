"use client";

import { useCallback, useEffect, useState } from "react";
import { Gauge, Save } from "lucide-react";
import { PermissionGate } from "@/components/permission-gate";
import { PageHeader, StatusBadge } from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import type { QuotaOverview, QuotaLevel, QuotaPolicyDetail, StatusTone } from "@/lib/types";

const PERIOD_LABELS: Record<string, string> = {
  DAILY: "每日",
  MONTHLY: "每月",
  ROLLING_30D: "滚动 30 天",
};

const LEVEL_META: Record<QuotaLevel, { tone: StatusTone; label: string }> = {
  NORMAL: { tone: "success", label: "正常" },
  WARNING: { tone: "warning", label: "接近上限" },
  EXCEEDED: { tone: "danger", label: "已超硬限" },
  NO_LIMIT: { tone: "neutral", label: "未设上限" },
};

function formatAmount(value: number): string {
  if (value >= 10000) return `${(value / 1000).toFixed(1)}k`;
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

export default function QuotasPage() {
  const [policies, setPolicies] = useState<QuotaPolicyDetail[]>([]);
  const [overview, setOverview] = useState<QuotaOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<{
    period_type: "DAILY" | "MONTHLY" | "ROLLING_30D";
    soft_limit: number | null;
    hard_limit: number | null;
    overage_allowed: boolean;
    status: "ACTIVE" | "DISABLED";
  }>({ period_type: "MONTHLY", soft_limit: null, hard_limit: null, overage_allowed: false, status: "ACTIVE" });

  const load = useCallback(async () => {
    try {
      const [list, ov] = await Promise.all([
        apiClient.listQuotaPolicies(),
        apiClient.getQuotaOverview(),
      ]);
      setPolicies(list);
      setOverview(ov);
      setError(null);
      return list;
    } catch {
      setError("加载失败，请稍后重试");
      return [];
    }
  }, []);

  useEffect(() => {
    load().then((list) => {
      if (list.length > 0) setSelected(list[0].metric);
      setLoading(false);
    });
  }, [load]);

  const current = policies.find((p) => p.metric === selected) ?? null;

  useEffect(() => {
    if (!current) return;
    setDraft({
      period_type: current.periodType,
      soft_limit: current.softLimit,
      hard_limit: current.hardLimit,
      overage_allowed: current.overageAllowed,
      status: current.status,
    });
  }, [current]);

  async function save() {
    if (!current) return;
    if (draft.soft_limit === null && draft.hard_limit === null) {
      setError("软限与硬限至少需要填写一个");
      return;
    }
    if (draft.soft_limit !== null && draft.hard_limit !== null && draft.soft_limit > draft.hard_limit) {
      setError("软限不能高于硬限");
      return;
    }
    setBusy(true);
    try {
      await apiClient.upsertQuotaPolicy(current.metric, draft);
      setError(null);
      await load();
    } catch {
      setError("保存失败，请检查限额设置是否合法");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="租户设置"
        title="配额与告警"
        description="查看套餐上限，设置团队软硬限制。超出软限告警、超出硬限阻断。"
      />
      {error && <p className="table-summary">{error}</p>}
      {loading && <p className="table-summary">加载中…</p>}

      {overview && (
        <div className="metric-grid">
          <div className="metric">
            <span className="metric-icon"><Gauge size={16} /></span>
            <span>受管指标</span>
            <strong>{overview.policyCount}</strong>
            <small>{overview.activeCount} 个已生效</small>
          </div>
          <div className="metric">
            <span className="metric-icon"><Gauge size={16} /></span>
            <span>告警中</span>
            <strong>{overview.warningCount}</strong>
            <small>已越过软限</small>
          </div>
          <div className="metric">
            <span className="metric-icon"><Gauge size={16} /></span>
            <span>已超硬限</span>
            <strong>{overview.exceededCount}</strong>
            <small>相关操作将被阻断</small>
          </div>
        </div>
      )}

      <div className="split-layout">
        <table className="data-table">
          <thead>
            <tr>
              <th>指标</th>
              <th>周期</th>
              <th>软限 / 硬限</th>
              <th>本周期用量</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {policies.map((p) => {
              const meta = LEVEL_META[p.usage.level];
              const ratio = p.usage.usageRatio ?? 0;
              return (
                <tr
                  key={p.metric}
                  className={selected === p.metric ? "row-selected" : ""}
                  onClick={() => setSelected(p.metric)}
                  style={{ cursor: "pointer" }}
                >
                  <td>
                    <strong>{p.metricLabel}</strong>
                    <small className="muted">{p.metric}</small>
                  </td>
                  <td>{PERIOD_LABELS[p.periodType] ?? p.periodType}</td>
                  <td>
                    {p.softLimit ?? "—"} / {p.hardLimit ?? "—"} <span className="muted">{p.unit}</span>
                  </td>
                  <td>
                    <div className="quota-usage">
                      <span>{formatAmount(p.usage.used)} {p.unit}</span>
                      {p.usage.usageRatio !== null && (
                        <div className="quota-bar" aria-hidden="true">
                          <span style={{ width: `${Math.min(100, ratio * 100)}%` }} />
                        </div>
                      )}
                    </div>
                  </td>
                  <td><StatusBadge tone={meta.tone}>{meta.label}</StatusBadge></td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <aside className="detail-panel">
          <div className="detail-head">
            <Gauge size={18} />
            <div>
              <strong>{current?.metricLabel ?? "选择一个指标"}</strong>
              <small className="muted">
                {current ? `${PERIOD_LABELS[current.periodType]} · ${current.unit}` : "在左侧选择要配置的指标"}
              </small>
            </div>
          </div>

          {current && (
            <PermissionGate permission="quota:configure">
              <div className="policy-form">
                <label>
                  统计周期
                  <select
                    value={draft.period_type}
                    onChange={(e) => setDraft((d) => ({ ...d, period_type: e.target.value as typeof d.period_type }))}
                  >
                    <option value="DAILY">每日</option>
                    <option value="MONTHLY">每月</option>
                    <option value="ROLLING_30D">滚动 30 天</option>
                  </select>
                </label>
                <div className="policy-row">
                  <label>
                    软限（告警）
                    <input
                      type="number" min={0} step={1}
                      value={draft.soft_limit ?? ""}
                      placeholder="不限"
                      onChange={(e) => setDraft((d) => ({ ...d, soft_limit: e.target.value ? Number(e.target.value) : null }))}
                    />
                  </label>
                  <label>
                    硬限（阻断）
                    <input
                      type="number" min={0} step={1}
                      value={draft.hard_limit ?? ""}
                      placeholder="不限"
                      onChange={(e) => setDraft((d) => ({ ...d, hard_limit: e.target.value ? Number(e.target.value) : null }))}
                    />
                  </label>
                </div>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={draft.overage_allowed}
                    onChange={(e) => setDraft((d) => ({ ...d, overage_allowed: e.target.checked }))}
                  />
                  允许超额（仅计费、不阻断）
                </label>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={draft.status === "ACTIVE"}
                    onChange={(e) => setDraft((d) => ({ ...d, status: e.target.checked ? "ACTIVE" : "DISABLED" }))}
                  />
                  启用该配额策略
                </label>
              </div>

              <button type="button" className="primary-button" disabled={busy} onClick={save}>
                <Save size={15} /> 保存配额
              </button>
            </PermissionGate>
          )}
        </aside>
      </div>
    </div>
  );
}
