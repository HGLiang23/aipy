import type { ContentRunSummary, HumanTaskSummary, MaterialSummary, TenantSession } from "@/lib/types";

export const mockSession: TenantSession = {
  tenant: { id: "019f91e3-tenant", name: "远山内容工作室", slug: "yuanshan", timezone: "Asia/Shanghai", status: "ACTIVE" },
  workspace: { id: "019f91e3-workspace", name: "默认工作空间" },
  user: { id: "019f91e3-user", displayName: "林编辑", email: "editor@example.com", roleLabel: "租户管理员", dataScopes: ["TENANT_ALL"] },
  permissions: [
    "batch:view", "batch:create", "content:view", "content:create", "content:edit", "content:assign",
    "artifact:view", "artifact:edit", "artifact:compare", "source:view", "source:create", "source:edit", "source:collect",
    "workflow:view", "workflow:configure", "workflow:execute", "review:view", "review:claim", "review:approve", "review:reject", "review:reassign",
    "publication:view", "publication:preview", "publication:export", "model:view", "model:configure", "model:credential_manage",
    "quota:view", "quota:configure", "member:view", "member:manage", "role:view", "role:manage", "audit:view",
  ],
};

export const mockContentRuns: ContentRunSummary[] = [
  { id: "CR-20260724-018", title: "AI 搜索如何改变品牌内容策略", brand: "远山商业", stageLabel: "分段写作", statusLabel: "运行中", tone: "info", owner: "林编辑", updatedAt: "2 分钟前", allowed_actions: ["view", "pause"], etag: '"run-v8"', version: 8 },
  { id: "CR-20260724-017", title: "周末城市轻徒步路线清单", brand: "慢游计划", stageLabel: "大纲审核", statusLabel: "等待人工", tone: "warning", owner: "周岚", updatedAt: "18 分钟前", allowed_actions: ["view", "approve", "reject"], etag: '"run-v5"', version: 5 },
  { id: "CR-20260724-014", title: "团队知识库落地的五个误区", brand: "远山商业", stageLabel: "平台适配", statusLabel: "运行中", tone: "info", owner: "林编辑", updatedAt: "42 分钟前", allowed_actions: ["view", "pause"], etag: '"run-v12"', version: 12 },
  { id: "CR-20260724-011", title: "新消费品牌七月观察", brand: "趋势手记", stageLabel: "发布包", statusLabel: "已完成", tone: "success", owner: "陈知", updatedAt: "今天 09:20", allowed_actions: ["view", "export"], etag: '"run-v14"', version: 14 },
  { id: "CR-20260723-096", title: "内容团队如何配置模型预算", brand: "远山商业", stageLabel: "事实检查", statusLabel: "需要处理", tone: "danger", owner: "林编辑", updatedAt: "昨天 18:06", allowed_actions: ["view", "rerun"], etag: '"run-v9"', version: 9 },
];

export const mockHumanTasks: HumanTaskSummary[] = [
  { id: "HT-201", title: "审核《周末城市轻徒步路线清单》大纲", type: "大纲审核", reason: "人机协同模板在大纲节点要求人工确认。", priority: "高", brand: "慢游计划", owner: "已分配给你", dueLabel: "今天 14:30 到期", allowed_actions: ["approve", "reject", "reassign"], etag: '"task-v4"', version: 4 },
  { id: "HT-198", title: "确认新消费品牌观察的引用来源", type: "事实核查", reason: "两条行业数据缺少一级来源。", priority: "普通", brand: "趋势手记", owner: "已分配给你", dueLabel: "今天 18:00 到期", allowed_actions: ["submit", "reassign"], etag: '"task-v2"', version: 2 },
  { id: "HT-193", title: "处理模型预算文章的质量门禁", type: "异常处理", reason: "事实检查评分 72，低于租户阈值 80。", priority: "普通", brand: "远山商业", owner: "团队任务", dueLabel: "明天 10:00 到期", allowed_actions: ["claim"], etag: '"task-v1"', version: 1 },
];

export const mockMaterials: MaterialSummary[] = [
  { id: "MAT-301", title: "2026 内容营销趋势报告", summary: "聚焦生成式搜索、内容可信度和品牌自有数据策略。", source: "research.example.com", type: "PDF", trustLabel: "高可信", tone: "success", updatedAt: "今天 10:16", allowed_actions: ["view", "edit"], etag: '"material-v3"', version: 3 },
  { id: "MAT-299", title: "微信公众号内容运营规则更新", summary: "平台近期关于原创、转载和 AI 辅助内容标识的规则摘要。", source: "weixin.qq.com", type: "网页", trustLabel: "官方来源", tone: "info", updatedAt: "今天 09:42", allowed_actions: ["view", "edit"], etag: '"material-v2"', version: 2 },
  { id: "MAT-287", title: "团队访谈：内容审核流程", summary: "内部编辑与审核员访谈纪要，包含现有协作问题。", source: "人工上传", type: "DOCX", trustLabel: "内部资料", tone: "neutral", updatedAt: "昨天 16:20", allowed_actions: ["view", "edit"], etag: '"material-v1"', version: 1 },
  { id: "MAT-281", title: "城市徒步路线用户调研", summary: "来自 126 份问卷的偏好、时长和安全关注点汇总。", source: "人工上传", type: "XLSX", trustLabel: "待复核", tone: "warning", updatedAt: "昨天 11:08", allowed_actions: ["view", "edit"], etag: '"material-v1"', version: 1 },
];

export const mockWorkflowNodes = [
  { name: "素材准备", detail: "12 条来源已确认", state: "done", label: "完成", tone: "success" as const },
  { name: "选题分析", detail: "选题评分 86", state: "done", label: "完成", tone: "success" as const },
  { name: "内容 Brief", detail: "已应用远山商业写作规范", state: "done", label: "完成", tone: "success" as const },
  { name: "大纲生成", detail: "人工确认版本 v3", state: "done", label: "完成", tone: "success" as const },
  { name: "分段写作", detail: "正在生成第 3 / 5 节", state: "active", label: "运行中", tone: "info" as const },
  { name: "事实与合规检查", detail: "等待上游产物", state: "pending", label: "等待", tone: "neutral" as const },
  { name: "平台适配", detail: "公众号、小红书", state: "pending", label: "等待", tone: "neutral" as const },
];

export const mockUsage = { used: 37, limit: 80, resetLabel: "明日 00:00" };
