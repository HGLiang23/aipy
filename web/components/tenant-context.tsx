"use client";

import { createContext, useContext, useMemo } from "react";
import type { TenantSession } from "@/lib/types";

const TenantContext = createContext<TenantSession | null>(null);

export function TenantProvider({ initialSession, children }: { initialSession: TenantSession; children: React.ReactNode }) {
  const session = useMemo(() => initialSession, [initialSession]);
  return <TenantContext.Provider value={session}>{children}</TenantContext.Provider>;
}

export function useTenantSession(): TenantSession {
  const context = useContext(TenantContext);
  if (!context) throw new Error("useTenantSession must be used inside TenantProvider");
  return context;
}
