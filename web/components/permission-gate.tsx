"use client";

import { useTenantSession } from "@/components/tenant-context";
import type { PermissionCode } from "@/lib/types";

type PermissionGateProps = {
  permission?: PermissionCode;
  anyOf?: PermissionCode[];
  invert?: boolean;
  fallback?: React.ReactNode;
  children: React.ReactNode;
};

export function PermissionGate({ permission, anyOf, invert = false, fallback = null, children }: PermissionGateProps) {
  const { permissions } = useTenantSession();
  const allowed = permission
    ? permissions.includes(permission)
    : anyOf
      ? anyOf.some((candidate) => permissions.includes(candidate))
      : true;
  const visible = invert ? !allowed : allowed;
  return visible ? <>{children}</> : <>{fallback}</>;
}
