import { AppShell } from "@/components/app-shell";
import { SessionLoader } from "@/components/session-loader";

export default function WorkspaceLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <SessionLoader>
      <AppShell>{children}</AppShell>
    </SessionLoader>
  );
}
