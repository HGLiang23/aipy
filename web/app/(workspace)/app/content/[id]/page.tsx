"use client";

import { ArrowLeft, Clock3, Ellipsis, Pause, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { PageHeader, StatusBadge } from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import { mockWorkflowNodes } from "@/lib/mock-data";
import type { ContentRunSummary } from "@/lib/types";

type State = { kind: "loading" } | { kind: "missing" } | { kind: "ready"; run: ContentRunSummary };

export default function ContentRunDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let active = true;
    apiClient
      .getContentRun(id)
      .then((run) => {
        if (active) setState({ kind: "ready", run });
      })
      .catch(() => {
        if (active) setState({ kind: "missing" });
      });
    return () => {
      active = false;
    };
  }, [id]);

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
  return (
    <div className="page-stack">
      <Link className="back-link" href="/app/content"><ArrowLeft size={16} /> 返回内容任务</Link>
      <PageHeader
        eyebrow={`${run.brand} · ${run.id}`}
        title={run.title}
        description="此页为内容任务详情骨架，后续接入结构化产物与版本编辑器。"
        action={
          <div className="button-group">
            <button className="icon-button" type="button" title="更多操作" aria-label="更多操作"><Ellipsis size={19} /></button>
            <button className="button button-secondary" type="button"><Pause size={16} /> 暂停</button>
          </div>
        }
      />

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
            {mockWorkflowNodes.map((node) => (
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
            <div className="section-heading"><div><h2>当前产物</h2><p>大纲 v3 · FRESH</p></div></div>
            <p className="body-copy">已形成 5 个章节，引用 8 条素材。正文生成节点正在执行，暂不可编辑。</p>
            <button className="button button-secondary button-wide" type="button"><RotateCcw size={16} /> 查看版本记录</button>
          </section>
          <section className="section-block">
            <div className="section-heading"><div><h2>运行信息</h2></div></div>
            <dl className="definition-list">
              <div><dt>工作流</dt><dd>公众号深度内容 v2</dd></div>
              <div><dt>开始时间</dt><dd><Clock3 size={14} /> 今天 09:24</dd></div>
              <div><dt>预计成本</dt><dd>¥ 3.80 / ¥ 8.00</dd></div>
              <div><dt>来源</dt><dd>12 条已确认素材</dd></div>
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
}
