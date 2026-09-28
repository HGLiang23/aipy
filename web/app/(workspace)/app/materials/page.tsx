"use client";

import { Download, FileText, Link2, Plus, Search, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { PermissionGate } from "@/components/permission-gate";
import { ActionNoticeBar, Modal, PageHeader, Pagination, StatusBadge } from "@/components/ui";
import { ApiProblem, apiClient } from "@/lib/api-client";
import { useApiList, useDebouncedValue } from "@/lib/use-api";
import type { ContentRunSummary, MaterialSummary } from "@/lib/types";

const PAGE_SIZE = 24;

const TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "全部类型" },
  { value: "网页", label: "网页" },
  { value: "PDF", label: "PDF" },
  { value: "DOCX", label: "DOCX" },
  { value: "XLSX", label: "XLSX" },
  { value: "Markdown", label: "Markdown" },
  { value: "文本", label: "文本" },
  { value: "图片", label: "图片" },
];

const TRUST_OPTIONS = ["待复核", "高可信", "官方来源", "内部资料"];

type Notice = { tone: "success" | "error"; title: string; detail: string };

export default function MaterialsPage() {
  const [term, setTerm] = useState("");
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const [dialog, setDialog] = useState<"import" | "upload" | null>(null);
  const [attaching, setAttaching] = useState<MaterialSummary | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  const search = useDebouncedValue(term);
  const { items, total, loading, error, reload } = useApiList<MaterialSummary>("materials", {
    page,
    pageSize: PAGE_SIZE,
    q: search,
    type,
  });

  useEffect(() => setPage(1), [search, type]);

  async function download(material: MaterialSummary) {
    try {
      await apiClient.downloadMaterial(material.id, material.title);
      setNotice(null);
    } catch {
      setNotice({ tone: "error", title: "下载失败", detail: "无法读取该素材的原件，请稍后重试。" });
    }
  }

  function created(message: string) {
    setDialog(null);
    setPage(1);
    reload();
    setNotice({ tone: "success", title: "已加入素材库", detail: message });
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="素材与采集"
        title="素材库"
        description="管理采集原文、人工修订和可用于内容生成的可信来源。"
        action={
          <PermissionGate permission="source:create">
            <div className="button-group">
              <button className="button button-secondary" type="button" onClick={() => setDialog("import")}><Link2 size={16} /> 导入 URL</button>
              <button className="button button-primary" type="button" onClick={() => setDialog("upload")}><Upload size={16} /> 上传文件</button>
            </div>
          </PermissionGate>
        }
      />
      <div className="toolbar">
        <label className="search-field">
          <Search size={17} aria-hidden="true" />
          <span className="sr-only">搜索素材</span>
          <input placeholder="搜索标题、域名或关键词" value={term} onChange={(event) => setTerm(event.target.value)} />
        </label>
        <select className="filter-select" aria-label="按类型筛选" value={type} onChange={(event) => setType(event.target.value)}>
          {TYPE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </div>

      {notice && (
        <ActionNoticeBar
          notice={notice}
          onClear={() => setNotice(null)}
          onReload={() => { setNotice(null); reload(); }}
        />
      )}

      {loading && <p className="table-summary">加载中…</p>}
      {error && <p className="table-summary">{error}</p>}
      {!loading && !error && items.length === 0 && <p className="table-summary">没有匹配的素材。</p>}
      <div className="material-grid">
        {items.map((material) => (
          <article className="material-row" key={material.id}>
            <span className="file-icon"><FileText size={20} /></span>
            <div className="material-main">
              <div><h2>{material.title}</h2><StatusBadge tone={material.tone}>{material.trustLabel}</StatusBadge></div>
              <p>{material.summary}</p>
              <small>{material.source} · {material.type} · {material.updatedAt}</small>
            </div>
            <div className="material-actions">
              <button className="icon-button" type="button" title="下载原件" aria-label={`下载 ${material.title} 的原件`} onClick={() => download(material)}>
                <Download size={18} />
              </button>
              <button className="icon-button" type="button" title="添加到内容任务" aria-label={`将 ${material.title} 添加到内容任务`} onClick={() => setAttaching(material)}>
                <Plus size={18} />
              </button>
            </div>
          </article>
        ))}
      </div>
      {!loading && !error && <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />}

      {dialog === "import" && <ImportUrlDialog onClose={() => setDialog(null)} onCreated={created} />}
      {dialog === "upload" && <UploadFileDialog onClose={() => setDialog(null)} onCreated={created} />}
      {attaching && (
        <AttachToRunDialog
          material={attaching}
          onClose={() => setAttaching(null)}
          onAttached={(run) => {
            setAttaching(null);
            setNotice({ tone: "success", title: "已关联到内容任务", detail: `「${attaching.title}」已加入任务 ${run.id}。` });
          }}
        />
      )}
    </div>
  );
}

function ImportUrlDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (message: string) => void }) {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [trustLabel, setTrustLabel] = useState(TRUST_OPTIONS[0]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const material = await apiClient.createMaterial({ url: url.trim(), title: title.trim() || undefined, trustLabel });
      onCreated(`已抓取「${material.title}」并登记为 ${material.type} 素材。`);
    } catch (cause) {
      setError(cause instanceof ApiProblem ? cause.problem.detail || cause.problem.title : "导入失败，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="导入 URL"
      description="提交后服务器会抓取该网页的标题与摘要；仅支持公网 http/https 地址。"
      onClose={onClose}
      footer={
        <>
          <button className="button button-secondary" type="button" onClick={onClose} disabled={busy}>取消</button>
          <button className="button button-primary" type="submit" form="import-url-form" disabled={busy || !url.trim()}>
            {busy ? "抓取中…" : "导入"}
          </button>
        </>
      }
    >
      <form id="import-url-form" className="form-stack" onSubmit={submit}>
        <label className="field">
          <span>网页地址</span>
          <input value={url} onChange={(event) => setUrl(event.target.value)} maxLength={2048} placeholder="https://example.com/report" required />
          <small>地址必须能在公网访问；内网与保留地址会被拒绝。</small>
        </label>
        <label className="field">
          <span>标题（可选）</span>
          <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={255} placeholder="留空则使用网页标题" />
        </label>
        <label className="field">
          <span>可信度</span>
          <select value={trustLabel} onChange={(event) => setTrustLabel(event.target.value)}>
            {TRUST_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
        </label>
        {error && <p className="field-error" role="alert">{error}</p>}
      </form>
    </Modal>
  );
}

function UploadFileDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (message: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [trustLabel, setTrustLabel] = useState(TRUST_OPTIONS[0]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const material = await apiClient.uploadMaterial(file, title.trim(), trustLabel);
      onCreated(`已保存「${material.title}」的原件，可随时下载。`);
    } catch (cause) {
      setError(cause instanceof ApiProblem ? cause.problem.detail || cause.problem.title : "上传失败，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="上传文件"
      description="原件会存入库中并归入当前租户，单文件上限 10 MB。"
      onClose={onClose}
      footer={
        <>
          <button className="button button-secondary" type="button" onClick={onClose} disabled={busy}>取消</button>
          <button className="button button-primary" type="submit" form="upload-file-form" disabled={busy || !file}>
            {busy ? "上传中…" : "上传"}
          </button>
        </>
      }
    >
      <form id="upload-file-form" className="form-stack" onSubmit={submit}>
        <label className="field">
          <span>选择文件</span>
          <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} required />
          <small>{file ? `${file.name} · ${(file.size / 1024).toFixed(0)} KB` : "支持 PDF / DOCX / XLSX / 文本 / 图片等格式。"}</small>
        </label>
        <label className="field">
          <span>标题（可选）</span>
          <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={255} placeholder="留空则使用文件名" />
        </label>
        <label className="field">
          <span>可信度</span>
          <select value={trustLabel} onChange={(event) => setTrustLabel(event.target.value)}>
            {TRUST_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
        </label>
        {error && <p className="field-error" role="alert">{error}</p>}
      </form>
    </Modal>
  );
}

function AttachToRunDialog({ material, onClose, onAttached }: { material: MaterialSummary; onClose: () => void; onAttached: (run: ContentRunSummary) => void }) {
  const [runs, setRuns] = useState<ContentRunSummary[] | null>(null);
  const [runId, setRunId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    apiClient
      .listContentRuns({ pageSize: 50 })
      .then((page) => { if (alive) setRuns(page.items); })
      .catch(() => { if (alive) setRuns([]); });
    return () => { alive = false; };
  }, []);

  async function submit() {
    if (!runId) return;
    setBusy(true);
    setError(null);
    try {
      onAttached(await apiClient.attachMaterial(runId, material.id));
    } catch (cause) {
      setError(cause instanceof ApiProblem ? cause.problem.detail || cause.problem.title : "关联失败，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="添加到内容任务"
      description={`把「${material.title}」关联到某个内容任务，参与生成与核查。`}
      onClose={onClose}
      footer={
        <>
          <button className="button button-secondary" type="button" onClick={onClose} disabled={busy}>取消</button>
          <button className="button button-primary" type="button" onClick={submit} disabled={busy || !runId}>{busy ? "关联中…" : "关联"}</button>
        </>
      }
    >
      {runs === null && <p className="table-summary">加载中…</p>}
      {runs?.length === 0 && <p className="table-summary">当前还没有内容任务，先去「内容任务」新建一个。</p>}
      {runs && runs.length > 0 && (
        <label className="field">
          <span>目标任务</span>
          <select value={runId} onChange={(event) => setRunId(event.target.value)}>
            <option value="">请选择…</option>
            {runs.map((run) => <option key={run.id} value={run.id}>{run.id} · {run.title}</option>)}
          </select>
        </label>
      )}
      {error && <p className="field-error" role="alert">{error}</p>}
    </Modal>
  );
}
