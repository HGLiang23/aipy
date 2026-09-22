import { AppShell } from "@/components/app-shell";
import { TenantProvider } from "@/components/tenant-context";
import { mockSession } from "@/lib/mock-data";

export default function WorkspaceLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <TenantProvider initialSession={mockSession}>
      <AppShell>{children}</AppShell>
    </TenantProvider>
  );
}
