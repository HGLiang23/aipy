"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { TenantProvider } from "@/components/tenant-context";
import { apiClient } from "@/lib/api-client";
import type { TenantSession } from "@/lib/types";

export function SessionLoader({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [session, setSession] = useState<TenantSession | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    apiClient
      .getSession()
      .then((s) => {
        if (!active) return;
        setSession(s);
        setReady(true);
      })
      .catch(() => {
        if (active) router.replace("/login");
      });
    return () => {
      active = false;
    };
  }, [router]);

  if (!ready || !session) {
    return <div className="loading-shell">加载中…</div>;
  }
  return <TenantProvider initialSession={session}>{children}</TenantProvider>;
}
