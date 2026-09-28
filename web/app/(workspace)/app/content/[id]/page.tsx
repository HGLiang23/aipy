"use client";

import { ArrowLeft, Clock3, Download, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { RowActions } from "@/components/row-actions";
import { ActionNoticeBar, PageHeader, StatusBadge } from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import { useResourceAction } from "@/lib/use-actions";
import type { ContentRunDetail, ContentRunSummary, ExportSummary } from "@/lib/types";

type RunNode = { name: string; detail: string; state: string; label: string; tone: string };

const STAGES: Array<{ name: string; key: string }> = [
  { name: "素材准备", key: "素材" },
  { name: "选题分析", key: "选题" },
  { name: "内容 Brief", key: "Brief" },
  { name: "大纲生成", key: "大纲" },
  { name: "分段写作", key: "写作" },
  { name: "事实与合规检查", key: "事实" },
  { name: "平台适配", key: "平台" },
];

/** Derive a workflow timeline from the run's real status/stage (no mock data). */
function buildRunTimeline(run: ContentRunSummary): RunNode[] {
  const stageIdx = STAGES.findIndex((s) => run.stageLabel.includes(s.key));
  const active = stageIdx < 0 ? STAGES.length - 1 : stageIdx;
  return STAGES.map((stage, i) => {
    if (run.status === "COMPLETED") {
      return { name: stage.name, detail: i === active ? run.stageLabel : "", state: "done", label: "完成", tone: "success" };
    }
    if (i < active) return { name: stage.name, detail: "", state: "done", label: "完成", tone: "success" };
    if (i > active) return { name: stage.name, detail: "", state: "pending", label: "等待", tone: "neutral" };
    if (run.status === "RUNNING") return { name: stage.name, detail: run.stageLabel, state: "active", label: "运行中", tone: "info" };
    if (run.status === "WAITING_HUMAN") return { name: stage.name, detail: run.stageLabel, state: "active", label: "等待人工", tone: "warning" };
    if (run.status === "PAUSED") return { name: stage.name, detail: run.stageLabel, state: "active", label: "已暂停", tone: "warning" };
    if (run.status === "FAILED") return { name: stage.name, detail: run.stageLabel, state: "active", label: "需处理", tone: "danger" };
    if (run.status === "CANCELLED") return { name: stage.name, detail: run.stageLabel, state: "active", label: "已取消", tone: "neutral" };
    return { name: stage.name, detail: run.stageLabel, state: "active", label: run.statusLabel, tone: run.tone };
  });
}

type State = { kind: "loading" } | { kind: "missing" } | { kind: "ready"; run: ContentRunDetail };

export default function ContentRunDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [state, setState] = useState<State>({ kind: "loading" });
  const [exports, setExports] = useState<ExportSummary[]>([]);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiClient
      .getContentRun(id)
      .then((run) => setState({ kind: "ready", run }))
      .catch(() => setState({ kind: "missing" }));
    apiClient.listContentExports(id).then(setExports).catch(() => setExports([]));
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // The actions endpoint returns the summary (no body), so re-read the detail
  // instead of feeding it into state, or the generated text would vanish.
  const onUpdated = useCallback(() => load(), [load]);
  const actions = useResourceAction<ContentRunSummary>("content-runs", onUpdated);

  async function download(item: ExportSummary) {
    setDownloadError(null);
    try {
      await apiClient.downloadExport(id, item.id, `${item.title}.md`);
    } catch {
      setDownloadError("下载失败，请稍后重试。");
    }
  }

  if (state.kind === "loading") {
    return <div className="page-stack"><p className="table-summary">加载中…</p></div>;
  }
  if (state.kind === "missing") {
    return (
      <div className="page-stack">
        <Link className="back-link" href="/app/content"><ArrowLeft size={16} /> 返回内容任务</Link>
        <p className="table-summary">未找到该内容任务（{id}）。</p>
      </div>
    );
  }

  const run = state.run;
  const timeline = buildRunTimeline(run);
  return (
    <div className="page-stack">
      <Link className="back-link" href="/app/content"><ArrowLeft size={16} /> 返回内容任务</Link>
      <PageHeader
        eyebrow={`${run.brand} · ${run.id}`}
        title={run.title}
        description="查看执行状态、工作流进度、生成的正文与导出成品。"
        action={
          <RowActions
            actions={run.allowed_actions}
            pending={actions.pendingId === run.id}
            onRun={(action) => actions.run(run, action)}
          />
        }
      />

      {actions.notice && <ActionNoticeBar notice={actions.notice} onClear={actions.clearNotice} onReload={load} />}
      {downloadError && <p className="field-error" role="alert">{downloadError}</p>}

      <div className="detail-summary">
        <div><span>执行状态</span><StatusBadge tone={run.tone}>{run.statusLabel}</StatusBadge></div>
        <div><span>当前阶段</span><strong>{run.stageLabel}</strong></div>
        <div><span>负责人</span><strong>{run.owner}</strong></div>
        <div><span>更新时间</span><strong>{run.updatedAt}</strong></div>
      </div>

      <div className="detail-layout">
        <section className="section-block">
          <div className="section-heading">
            <div><h2>工作流进度</h2><p>全自动模式 · 质量门禁失败时转人工</p></div>
          </div>
          <ol className="timeline">
            {timeline.map((node) => (
              <li className={`timeline-item timeline-${node.state}`} key={node.name}>
                <span className="timeline-dot" aria-hidden="true" />
                <div><strong>{node.name}</strong><small>{node.detail}</small></div>
                <StatusBadge tone={node.tone as never}>{node.label}</StatusBadge>
              </li>
            ))}
          </ol>
        </section>

        <aside className="detail-aside">
          <section className="section-block">
            <div className="section-heading">
              <div><h2>当前产物</h2><p>{run.stageLabel}</p></div>
              <a href="#" onClick={(event) => { event.preventDefault(); load(); }}>刷新</a>
            </div>
            {run.content ? (
              <pre className="generated-body">{run.content}</pre>
            ) : (
              <p className="body-copy">
                {run.status === "RUNNING"
                  ? "正文生成节点正在执行，完成或重跑后会显示在这里。"
                  : "本次任务还没有生成正文，可执行「重跑」后等待后台完成。"}
              </p>
            )}
          </section>

          <section className="section-block">
            <div className="section-heading">
              <div><h2>导出记录</h2><p>执行「导出」后生成的可下载成品</p></div>
              <a href="#" onClick={(event) => { event.preventDefault(); load(); }}><RefreshCw size={14} aria-hidden="true" /> 刷新</a>
            </div>
            {exports.length === 0 ? (
              <p className="body-copy">还没有导出文件。执行「导出」动作即可生成 markdown 成品。</p>
            ) : (
              <div className="export-list">
                {exports.map((item) => (
                  <div className="export-row" key={item.id}>
                    <div>
                      <strong>{item.title}</strong>
                      <span>{item.createdAt} · {item.format} · {item.sizeBytes} 字节</span>
                    </div>
                    <button className="button button-secondary" type="button" onClick={() => download(item)}>
                      <Download size={14} /> 下载
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="section-block">
            <div className="section-heading"><div><h2>运行信息</h2></div></div>
            <dl className="definition-list">
              <div><dt>任务编码</dt><dd>{run.id}</dd></div>
              <div><dt>品牌</dt><dd>{run.brand}</dd></div>
              <div><dt>负责人</dt><dd>{run.owner}</dd></div>
              <div><dt>更新时间</dt><dd><Clock3 size={14} /> {run.updatedAt}</dd></div>
              <div><dt>状态</dt><dd>{run.statusLabel}</dd></div>
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
}
