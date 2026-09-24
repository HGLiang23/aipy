"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, RefreshCw, Trash2 } from "lucide-react";
import { PermissionGate } from "@/components/permission-gate";
import { PageHeader, StatusBadge } from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import type { Page } from "@/lib/api-client";
import type { ModelCredentialSummary, ModelProviderSummary, StatusTone } from "@/lib/types";

const statusTone: Record<string, StatusTone> = {
  ACTIVE: "success",
  INVALID: "danger",
  REVOKED: "neutral",
};
const statusLabel: Record<string, string> = {
  ACTIVE: "有效",
  INVALID: "验证失败",
  REVOKED: "已吊销",
};

function fmt(ts: string | null): string {
  if (!ts) return "未验证";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString("zh-CN", { hour12: false });
}

export default function ModelCredentialsPage() {
  const [page, setPage] = useState<Page<ModelCredentialSummary> | null>(null);
  const [providers, setProviders] = useState<ModelProviderSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<{
    provider_id: string;
    name: string;
    ownership_type: "BYOK" | "PLATFORM";
    secret: string;
  }>({ provider_id: "", name: "", ownership_type: "BYOK", secret: "" });

  const credentials = page?.items ?? [];

  const load = useCallback(() => {
    setLoading(true);
    apiClient
      .listModelCredentials()
      .then((data) => {
        setPage(data);
        setError(null);
      })
      .catch(() => setError("加载失败，请稍后重试"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    apiClient.listModelProviders().then(setProviders).catch(() => setProviders([]));
  }, [load]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.provider_id || !form.name || !form.secret) return;
    setBusy(true);
    try {
      await apiClient.createModelCredential({ ...form });
      setForm({ provider_id: "", name: "", ownership_type: "BYOK", secret: "" });
      load();
    } catch {
      setError("创建失败，请检查供应商与密钥");
    } finally {
      setBusy(false);
    }
  }

  async function test(id: string) {
    setBusy(true);
    try {
      await apiClient.testModelCredential(id);
      load();
    } catch {
      setError("测试失败");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: string) {
    setBusy(true);
    try {
      await apiClient.revokeModelCredential(id);
      load();
    } catch {
      setError("吊销失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="组织与权限"
        title="模型凭证"
        description="管理平台托管凭证或租户 BYOK 引用。密钥只写不读，保存后仅显示掩码。"
      />

      <PermissionGate permission="model:credential_manage">
        <form className="credential-form" onSubmit={submit}>
          <label>
            供应商
            <select
              value={form.provider_id}
              onChange={(e) => setForm((f) => ({ ...f, provider_id: e.target.value }))}
            >
              <option value="">选择供应商</option>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>{p.name}（{p.code}）</option>
              ))}
            </select>
          </label>
          <label>
            凭证名称
            <input
              value={form.name}
              placeholder="如：生产主密钥"
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </label>
          <label>
            归属
            <select
              value={form.ownership_type}
              onChange={(e) => setForm((f) => ({ ...f, ownership_type: e.target.value as "BYOK" | "PLATFORM" }))}
            >
              <option value="BYOK">租户自有（BYOK）</option>
              <option value="PLATFORM">平台托管</option>
            </select>
          </label>
          <label>
            密钥
            <input
              type="password"
              value={form.secret}
              placeholder="sk-..."
              autoComplete="off"
              onChange={(e) => setForm((f) => ({ ...f, secret: e.target.value }))}
            />
          </label>
          <button type="submit" className="primary-button" disabled={busy}>
            <Plus size={15} /> 创建凭证
          </button>
        </form>
      </PermissionGate>

      {loading && <p className="table-summary">加载中…</p>}
      {error && <p className="table-summary">{error}</p>}
      <table className="data-table">
        <thead>
          <tr>
            <th>凭证</th>
            <th>供应商</th>
            <th>归属</th>
            <th>密钥</th>
            <th>状态</th>
            <th>最近验证</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {credentials.map((c) => (
            <tr key={c.id}>
              <td><strong>{c.name}</strong></td>
              <td>{c.providerName}</td>
              <td>{c.ownershipType === "BYOK" ? "租户自有" : "平台托管"}</td>
              <td><code>{c.secretMasked}</code></td>
              <td><StatusBadge tone={statusTone[c.status] ?? "neutral"}>{statusLabel[c.status] ?? c.status}</StatusBadge></td>
              <td>
                {fmt(c.lastVerifiedAt)}
                {c.lastVerifyMessage ? <small className="muted">{c.lastVerifyMessage}</small> : null}
              </td>
              <td>
                <PermissionGate permission="model:credential_manage">
                  <div className="row-actions">
                    <button
                      type="button"
                      className="icon-button"
                      title="连接测试"
                      disabled={busy || c.status === "REVOKED"}
                      onClick={() => test(c.id)}
                    >
                      <RefreshCw size={16} />
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      title="吊销"
                      disabled={busy || c.status === "REVOKED"}
                      onClick={() => revoke(c.id)}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </PermissionGate>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!loading && credentials.length === 0 && (
        <div className="table-summary">暂无凭证，请在上方创建</div>
      )}
    </div>
  );
}
