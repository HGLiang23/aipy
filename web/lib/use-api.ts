"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import type { Page } from "@/lib/api-client";

type ListKind = "content-runs" | "human-tasks" | "materials" | "members" | "workflow-templates" | "audit-logs" | "model-credentials";

export function useApiList<T>(kind: ListKind) {
  const [page, setPage] = useState<Page<T> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    const promise =
      kind === "content-runs"
        ? apiClient.listContentRuns()
        : kind === "human-tasks"
          ? apiClient.listHumanTasks()
          : kind === "materials"
            ? apiClient.listMaterials()
            : kind === "members"
              ? apiClient.listMembers()
              : kind === "workflow-templates"
                ? apiClient.listWorkflowTemplates()
                : kind === "audit-logs"
                  ? apiClient.listAuditLogs()
                  : apiClient.listModelCredentials();

    promise
      .then((data) => {
        if (active) {
          setPage(data as Page<T>);
          setError(null);
        }
      })
      .catch(() => {
        if (active) setError("加载失败，请稍后重试");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [kind]);

  return { page, loading, error };
}
