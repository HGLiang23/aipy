"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, KeyRound, Power, Search, Shield, UserPlus, X } from "lucide-react";
import { PermissionGate } from "@/components/permission-gate";
import { PageHeader, StatusBadge } from "@/components/ui";
import { apiClient, ApiProblem } from "@/lib/api-client";
import type { Page } from "@/lib/api-client";
import type { MemberSummary, RoleSummary, StatusTone } from "@/lib/types";

const statusMap: Record<string, { label: string; tone: StatusTone }> = {
  ACTIVE: { label: "正常", tone: "success" },
  INVITED: { label: "已邀请", tone: "warning" },
  SUSPENDED: { label: "已停用", tone: "danger" },
  LEFT: { label: "已退出", tone: "neutral" },
};

// A password is surfaced exactly once, either from create or from reset. Keeping
// both flows behind one shape lets them share the same one-time panel.
interface IssuedSecret {
  kind: "create" | "reset";
  displayName: string;
  email: string;
  roleLabel?: string;
  password: string;
}

const emptyForm = { email: "", displayName: "", role_id: "", job_title: "" };

function fmtDate(ts?: string | null): string {
  if (!ts) return "-";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleDateString("zh-CN");
}

export default function MembersPage() {
  const [page, setPage] = useState<Page<MemberSummary> | null>(null);
  const [roles, setRoles] = useState<RoleSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(emptyForm);
  // Holds the one-time password; cleared as soon as the admin dismisses it.
  const [issued, setIssued] = useState<IssuedSecret | null>(null);
  const [copied, setCopied] = useState(false);
  const [keyword, setKeyword] = useState("");
  // Reset is destructive (the old password dies immediately), so it asks first.
  const [confirmResetId, setConfirmResetId] = useState<string | null>(null);

  const members = (page?.items ?? []).filter((m) => {
    const kw = keyword.trim().toLowerCase();
    if (!kw) return true;
    return m.displayName.toLowerCase().includes(kw) || m.email.toLowerCase().includes(kw);
  });

  const load = useCallback(() => {
    setLoading(true);
    apiClient
      .listMembers()
      .then((data) => {
        setPage(data);
        setError(null);
      })
      .catch(() => setError("加载失败，请稍后重试"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    apiClient.listRoles().then(setRoles).catch(() => setRoles([]));
  }, [load]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.email.trim() || !form.displayName.trim() || !form.role_id) {
      setError("邮箱、姓名与角色均为必填项");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await apiClient.createMember({
        email: form.email.trim(),
        displayName: form.displayName.trim(),
        role_id: form.role_id,
        job_title: form.job_title.trim() || null,
      });
      setForm(emptyForm);
      setCopied(false);
      // Only surface the panel when a fresh password exists; a reused account has none.
      setIssued(
        created.initialPassword
          ? {
              kind: "create",
              displayName: created.displayName,
              email: created.email,
              roleLabel: created.roleLabel,
              password: created.initialPassword,
            }
          : null,
      );
      load();
    } catch (err) {
      setError(err instanceof ApiProblem ? err.problem.detail || err.message : "创建失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword(m: MemberSummary) {
    setBusy(true);
    setError(null);
    try {
      const result = await apiClient.resetMemberPassword(m.id);
      setCopied(false);
      setIssued({
        kind: "reset",
        displayName: result.displayName,
        email: result.email,
        password: result.password,
      });
      setConfirmResetId(null);
    } catch (err) {
      setError(err instanceof ApiProblem ? err.problem.detail || err.message : "重置密码失败");
    } finally {
      setBusy(false);
    }
  }

  async function toggleStatus(m: MemberSummary) {
    setBusy(true);
    setError(null);
    try {
      await apiClient.updateMember(m.id, { status: m.status === "ACTIVE" ? "SUSPENDED" : "ACTIVE" });
      load();
    } catch {
      setError("状态更新失败");
    } finally {
      setBusy(false);
    }
  }

  async function copyPassword() {
    if (!issued?.password) return;
    try {
      await navigator.clipboard.writeText(issued.password);
      setCopied(true);
    } catch {
      setError("浏览器拒绝了剪贴板访问，请手动选中复制");
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="组织与权限"
        title="成员与团队"
        description="新增成员并分配角色。初始密码只在创建成功时显示一次，请立即转交本人。"
      />

      <PermissionGate permission="member:manage">
        <form className="credential-form" onSubmit={submit}>
          <label>
            邮箱
            <input
              type="email"
              value={form.email}
              placeholder="name@company.com"
              autoComplete="off"
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            />
          </label>
          <label>
            姓名
            <input
              value={form.displayName}
              placeholder="如：张三"
              onChange={(e) => setForm((f) => ({ ...f, displayName: e.target.value }))}
            />
          </label>
          <label>
            角色
            <select
              value={form.role_id}
              onChange={(e) => setForm((f) => ({ ...f, role_id: e.target.value }))}
            >
              <option value="">选择角色</option>
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                  {r.isDefault ? "（默认）" : ""}
                </option>
              ))}
            </select>
          </label>
          <label>
            职位（选填）
            <input
              value={form.job_title}
              placeholder="如：内容编辑"
              onChange={(e) => setForm((f) => ({ ...f, job_title: e.target.value }))}
            />
          </label>
          <button type="submit" className="primary-button" disabled={busy}>
            <UserPlus size={15} /> 新增成员
          </button>
        </form>
      </PermissionGate>

      <div className="toolbar">
        <label className="search-field">
          <Search size={17} />
          <input
            aria-label="搜索成员"
            value={keyword}
            placeholder="搜索姓名或邮箱"
            onChange={(e) => setKeyword(e.target.value)}
          />
        </label>
        <span className="muted">共 {members.length} 位成员</span>
      </div>

      {issued && (
        <div className="onetime-secret">
          <div>
            <strong>
              {issued.kind === "create" ? "初始密码（仅显示这一次）" : "新密码（仅显示这一次）"}
            </strong>
            <small className="muted">
              {issued.displayName} · {issued.email}
              {issued.roleLabel ? ` · 角色 ${issued.roleLabel}` : ""}
              {" "}—— {issued.kind === "create"
                ? "关闭后无法再次查看，忘记只能在数据库中重置。"
                : "旧密码已立即失效，请转交本人；关闭后无法再次查看。"}
            </small>
          </div>
          <code>{issued.password}</code>
          <div className="row-actions">
            <button type="button" className="icon-button" title="复制密码" onClick={copyPassword}>
              {copied ? <Check size={16} /> : <Copy size={16} />}
            </button>
            <button type="button" className="primary-button" onClick={() => setIssued(null)}>
              我已转交，关闭
            </button>
          </div>
        </div>
      )}

      {loading && <p className="table-summary">加载中…</p>}
      {error && <p className="table-summary">{error}</p>}
      <table className="data-table">
        <thead>
          <tr>
            <th>成员</th>
            <th>角色</th>
            <th>状态</th>
            <th>职位</th>
            <th>加入时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {members.map((m) => {
            const st = statusMap[m.status] ?? { label: m.status, tone: "neutral" as const };
            const canToggle = m.status === "ACTIVE" || m.status === "SUSPENDED";
            return (
              <tr key={m.id}>
                <td>
                  <div className="user-cell">
                    <span className="avatar avatar-sm">{m.displayName.charAt(0)}</span>
                    <div>
                      <strong>{m.displayName}</strong>
                      <small>{m.email}</small>
                    </div>
                  </div>
                </td>
                <td><span className="role-tag"><Shield size={14} />{m.roleLabel}</span></td>
                <td><StatusBadge tone={st.tone}>{st.label}</StatusBadge></td>
                <td>{m.jobTitle ?? "-"}</td>
                <td>{fmtDate(m.joinedAt)}</td>
                <td>
                  <PermissionGate permission="member:manage">
                    <div className="row-actions">
                      {canToggle && (
                        <button
                          type="button"
                          className="icon-button"
                          title={m.status === "ACTIVE" ? "停用该成员" : "恢复该成员"}
                          aria-label={m.status === "ACTIVE" ? "停用该成员" : "恢复该成员"}
                          disabled={busy}
                          onClick={() => toggleStatus(m)}
                        >
                          <Power size={16} />
                        </button>
                      )}
                      {/* Suspended members cannot log in, so a reset would be dead on arrival. */}
                      {m.status === "ACTIVE" && confirmResetId !== m.id && (
                        <button
                          type="button"
                          className="icon-button"
                          title="重置密码"
                          aria-label="重置密码"
                          disabled={busy}
                          onClick={() => setConfirmResetId(m.id)}
                        >
                          <KeyRound size={16} />
                        </button>
                      )}
                      {confirmResetId === m.id && (
                        <>
                          <span className="muted">旧密码将立即失效，确认重置？</span>
                          <button
                            type="button"
                            className="primary-button"
                            disabled={busy}
                            onClick={() => resetPassword(m)}
                          >
                            确认重置
                          </button>
                          <button
                            type="button"
                            className="icon-button"
                            title="取消"
                            aria-label="取消重置"
                            disabled={busy}
                            onClick={() => setConfirmResetId(null)}
                          >
                            <X size={16} />
                          </button>
                        </>
                      )}
                      {!canToggle && <span className="muted">-</span>}
                    </div>
                  </PermissionGate>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!loading && members.length === 0 && (
        <div className="table-summary">暂无成员数据</div>
      )}
    </div>
  );
}
