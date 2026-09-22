import { EmptyState } from "@/components/ui";

export default function NotFoundPage() {
  return <main className="centered-page"><EmptyState title="页面不存在" description="该页面可能已移动，或你无权查看对应资源。" actionLabel="返回工作台" actionHref="/app" /></main>;
}
