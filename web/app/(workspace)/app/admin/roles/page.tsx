"use client";

import { useEffect, useState } from "react";
import { Shield, ShieldCheck, ShieldAlert, Settings } from "lucide-react";
import { PermissionGate } from "@/components/permission-gate";
import { PageHeader } from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import type { RoleDetail, RoleSummary } from "@/lib/types";

export default function RolesPage() {
  const [roles, setRoles] = useState<RoleSummary[]>([]);
  const [selected, setSelected] = useState<RoleDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    apiClient.listRoles()
      .then((data) => { if (active) { setRoles(data); setError(null); } })
      .catch(() => { if (active) setError("加载失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const handleSelect = (id: string) => {
    apiClient.getRole(id)
      .then(setSelected)
      .catch(() => setError("加载角色详情失败"));
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="组织与权限"
        title="角色与数据范围"
        description="配置功能权限与租户内数据可见范围。"
      />
      <div className="admin-layout">
        <div className="role-list">
          {loading && <p className="table-summary">加载中…</p>}
          {error && <p className="table-summary">{error}</p>}
          {roles.map((r) => (
            <button
              key={r.id}
              className={`role-card ${selected?.id === r.id ? "role-card-active" : ""}`}
              type="button"
              onClick={() => handleSelect(r.id)}
            >
              <span className="role-icon">
                {r.isBuiltin ? <ShieldAlert size={20} /> : <Shield size={20} />}
              </span>
              <div>
                <strong>{r.name}</strong>
                <small>{r.code} · {r.permissionCount} 个权限</small>
              </div>
              {r.isDefault && <span className="badge badge-info">默认</span>}
            </button>
          ))}
        </div>
        <div className="role-detail">
          {selected ? (
            <>
              <h2>{selected.name}</h2>
              <p className="text-muted">{selected.description ?? "无描述"}</p>
              <div className="detail-meta">
                <span><ShieldCheck size={14} /> 编码：{selected.code}</span>
                <span>成员：{selected.memberCount} 人</span>
                {selected.isBuiltin && <span className="badge badge-info">内置角色</span>}
              </div>
              <h3>权限列表</h3>
              <div className="permission-grid">
                {selected.permissions.map((p) => (
                  <span key={p.code} className="permission-tag">
                    <Settings size={12} />
                    {p.code}
                    {p.dataScope && p.dataScope !== "TENANT_ALL" && (
                      <small className="scope-hint">{p.dataScope}</small>
                    )}
                  </span>
                ))}
                {selected.permissions.length === 0 && <p className="text-muted">暂无权限</p>}
              </div>
              <PermissionGate permission="role:manage">
                <div className="detail-actions">
                  <button className="button button-secondary" type="button">编辑角色</button>
                </div>
              </PermissionGate>
            </>
          ) : (
            <div className="empty-detail">
              <Shield size={40} />
              <p>选择一个角色查看详情</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
