import { Filter, Plus, Search } from "lucide-react";
import Link from "next/link";
import { PermissionGate } from "@/components/permission-gate";
import { PageHeader, StatusBadge } from "@/components/ui";
import { mockContentRuns } from "@/lib/mock-data";

export default function ContentRunsPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="内容生产"
        title="内容任务"
        description="查看单篇内容从素材分析到平台适配的执行状态。"
        action={
          <PermissionGate permission="content:create">
            <button className="button button-primary" type="button"><Plus size={17} /> 新建任务</button>
          </PermissionGate>
        }
      />

      <div className="toolbar">
        <label className="search-field">
          <Search size={17} aria-hidden="true" />
          <span className="sr-only">搜索内容任务</span>
          <input placeholder="搜索标题、品牌或任务 ID" />
        </label>
        <button className="button button-secondary" type="button"><Filter size={16} /> 筛选</button>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>内容任务</th><th>品牌</th><th>当前阶段</th><th>状态</th><th>负责人</th><th>更新时间</th></tr>
          </thead>
          <tbody>
            {mockContentRuns.map((run) => (
              <tr key={run.id}>
                <td data-label="内容任务"><Link className="table-link" href={`/app/content/${run.id}`}>{run.title}</Link><small>{run.id}</small></td>
                <td data-label="品牌">{run.brand}</td>
                <td data-label="当前阶段">{run.stageLabel}</td>
                <td data-label="状态"><StatusBadge tone={run.tone}>{run.statusLabel}</StatusBadge></td>
                <td data-label="负责人">{run.owner}</td>
                <td data-label="更新时间">{run.updatedAt}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="table-summary">共 {mockContentRuns.length} 项 · 模拟数据</p>
    </div>
  );
}
