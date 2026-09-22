import { FileText, Filter, Link2, Plus, Search, Upload } from "lucide-react";
import { PermissionGate } from "@/components/permission-gate";
import { PageHeader, StatusBadge } from "@/components/ui";
import { mockMaterials } from "@/lib/mock-data";

export default function MaterialsPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="素材与采集"
        title="素材库"
        description="管理采集原文、人工修订和可用于内容生成的可信来源。"
        action={
          <PermissionGate permission="source:create">
            <div className="button-group">
              <button className="button button-secondary" type="button"><Link2 size={16} /> 导入 URL</button>
              <button className="button button-primary" type="button"><Upload size={16} /> 上传文件</button>
            </div>
          </PermissionGate>
        }
      />
      <div className="toolbar">
        <label className="search-field"><Search size={17} /><span className="sr-only">搜索素材</span><input placeholder="搜索标题、域名或关键词" /></label>
        <button className="button button-secondary" type="button"><Filter size={16} /> 筛选</button>
      </div>
      <div className="material-grid">
        {mockMaterials.map((material) => (
          <article className="material-row" key={material.id}>
            <span className="file-icon"><FileText size={20} /></span>
            <div className="material-main">
              <div><h2>{material.title}</h2><StatusBadge tone={material.tone}>{material.trustLabel}</StatusBadge></div>
              <p>{material.summary}</p>
              <small>{material.source} · {material.type} · {material.updatedAt}</small>
            </div>
            <button className="icon-button" type="button" title="添加到内容任务" aria-label={`将 ${material.title} 添加到内容任务`}><Plus size={18} /></button>
          </article>
        ))}
      </div>
    </div>
  );
}
