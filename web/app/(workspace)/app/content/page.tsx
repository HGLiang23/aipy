"use client";

import { Plus, Search } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { PermissionGate } from "@/components/permission-gate";
import { RowActions } from "@/components/row-actions";
import { ActionNoticeBar, Modal, PageHeader, Pagination, StatusBadge } from "@/components/ui";
import { ApiProblem, apiClient } from "@/lib/api-client";
import { useResourceAction } from "@/lib/use-actions";
import { useApiList, useDebouncedValue } from "@/lib/use-api";
import type { ContentRunSummary } from "@/lib/types";

const PAGE_SIZE = 20;

const STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "全部状态" },
  { value: "RUNNING", label: "运行中" },
  { value: "WAITING_HUMAN", label: "等待人工" },
  { value: "PAUSED", label: "已暂停" },
  { value: "FAILED", label: "需要处理" },
  { value: "COMPLETED", label: "已完成" },
  { value: "CANCELLED", label: "已取消" },
];

export default function ContentRunsPage() {
  // ``useSearchParams`` needs a Suspense boundary during prerendering.
  return (
    <Suspense fallback={<div className="page-stack"><p className="table-summary">加载中…</p></div>}>
      <ContentRunsBoard />
    </Suspense>
  );
}

function ContentRunsBoard() {
  const routeTerm = useSearchParams().get("q") ?? "";
  const [term, setTerm] = useState(routeTerm);
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);

  const search = useDebouncedValue(term);
  const { items, total, loading, error, reload, replaceRow } = useApiList<ContentRunSummary>("content-runs", {
    page,
    pageSize: PAGE_SIZE,
    q: search,
    status,
  });
  const actions = useResourceAction<ContentRunSummary>("content-runs", replaceRow);

  // Keep the box in step when the top bar navigates here with a new search term.
  useEffect(() => setTerm(routeTerm), [routeTerm]);
  // A new filter must start from the first page, or the user lands on an empty page.
  useEffect(() => setPage(1), [search, status]);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="内容生产"
        title="内容任务"
        description="查看单篇内容从素材分析到平台适配的执行状态。"
        action={
          <PermissionGate permission="content:create">
            <button className="button button-primary" type="button" onClick={() => setCreating(true)}><Plus size={17} /> 新建任务</button>
          </PermissionGate>
        }
      />

      <div className="toolbar">
        <label className="search-field">
          <Search size={17} aria-hidden="true" />
          <span className="sr-only">搜索内容任务</span>
          <input
            placeholder="搜索标题、品牌或任务 ID"
            value={term}
            onChange={(event) => setTerm(event.target.value)}
          />
        </label>
        <select className="filter-select" aria-label="按状态筛选" value={status} onChange={(event) => setStatus(event.target.value)}>
          {STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </div>

      {actions.notice && <ActionNoticeBar notice={actions.notice} onClear={actions.clearNotice} onReload={reload} />}

      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>内容任务</th><th>品牌</th><th>当前阶段</th><th>状态</th><th>负责人</th><th>更新时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} className="table-summary">加载中…</td></tr>
            )}
            {!loading && items.length === 0 && (
              <tr><td colSpan={7} className="table-summary">没有匹配的内容任务。</td></tr>
            )}
            {!loading && items.map((run) => (
              <tr key={run.id}>
                <td data-label="内容任务">
                  <Link className="table-link" href={`/app/content/${run.id}`}>{run.title}</Link>
                  <small>{run.id}</small>
                </td>
                <td data-label="品牌">{run.brand}</td>
                <td data-label="当前阶段">{run.stageLabel}</td>
                <td data-label="状态"><StatusBadge tone={run.tone}>{run.statusLabel}</StatusBadge></td>
                <td data-label="负责人">{run.owner}</td>
                <td data-label="更新时间">{run.updatedAt}</td>
                <td data-label="操作">
                  <RowActions
                    actions={run.allowed_actions}
                    pending={actions.pendingId === run.id}
                    onRun={(action) => actions.run(run, action)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error && <p className="table-summary">{error}</p>}
      {!loading && !error && <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />}

      {creating && (
        <CreateRunDialog
          onClose={() => setCreating(false)}
          onCreated={() => { setCreating(false); setPage(1); reload(); }}
        />
      )}
    </div>
  );
}

function CreateRunDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [title, setTitle] = useState("");
  const [brand, setBrand] = useState("");
  const [stageLabel, setStageLabel] = useState("素材准备");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const ready = title.trim().length > 0 && brand.trim().length > 0;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiClient.createContentRun({ title: title.trim(), brand: brand.trim(), stageLabel: stageLabel.trim() || "素材准备" });
      onCreated();
    } catch (cause) {
      setError(cause instanceof ApiProblem ? cause.problem.detail || cause.problem.title : "创建失败，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="新建内容任务"
      description="提交后任务立即进入运行，后台开始生成正文；可在详情页导出成品。"
      onClose={onClose}
      footer={
        <>
          <button className="button button-secondary" type="button" onClick={onClose} disabled={busy}>取消</button>
          <button className="button button-primary" type="submit" form="create-run-form" disabled={busy || !ready}>
            {busy ? "创建中…" : "创建并开始"}
          </button>
        </>
      }
    >
      <form id="create-run-form" className="form-stack" onSubmit={submit}>
        <label className="field">
          <span>内容标题</span>
          <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={255} placeholder="如：AI 搜索如何改变品牌内容策略" required />
        </label>
        <label className="field">
          <span>所属品牌</span>
          <input value={brand} onChange={(event) => setBrand(event.target.value)} maxLength={120} placeholder="如：远山商业" required />
        </label>
        <label className="field">
          <span>起始阶段</span>
          <input value={stageLabel} onChange={(event) => setStageLabel(event.target.value)} maxLength={64} />
        </label>
        {error && <p className="field-error" role="alert">{error}</p>}
      </form>
    </Modal>
  );
}
