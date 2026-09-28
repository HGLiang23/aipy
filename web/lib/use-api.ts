"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiClient, ApiProblem } from "@/lib/api-client";
import type { ListQuery, Page } from "@/lib/api-client";

type ListKind = "content-runs" | "human-tasks" | "materials";

/**
 * Loads a board page. The query is part of the effect key so changing the search
 * term or the active tab refetches, and the caller keeps ownership of that state.
 */
export function useApiList<T extends { id: string }>(kind: ListKind, query: ListQuery = {}) {
  const [page, setPage] = useState<Page<T> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  // Serialised so a fresh object literal on every render does not re-trigger the
  // effect; only an actual change in the query does.
  const queryKey = JSON.stringify(query);

  useEffect(() => {
    let active = true;
    setLoading(true);
    const parsed = JSON.parse(queryKey) as ListQuery;
    // ``kind`` and ``T`` are chosen together by the caller, so the endpoint's
    // item type always matches; TypeScript cannot see that through the union.
    const promise = (kind === "content-runs"
      ? apiClient.listContentRuns(parsed)
      : kind === "human-tasks"
        ? apiClient.listHumanTasks(parsed)
        : apiClient.listMaterials(parsed)) as unknown as Promise<Page<T>>;

    promise
      .then((data) => {
        if (active) {
          setPage(data);
          setError(null);
        }
      })
      .catch((cause: unknown) => {
        // Surface what the server actually said instead of a generic message.
        if (active) setError(cause instanceof ApiProblem ? cause.problem.detail || cause.problem.title : "加载失败，请稍后重试");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [kind, queryKey, reloadToken]);

  const reload = useCallback(() => setReloadToken((value) => value + 1), []);
  const replaceRow = useCallback((row: T) => {
    setPage((current) => (current ? { ...current, items: current.items.map((item) => (item.id === row.id ? row : item)) } : current));
  }, []);

  // Memoised so a consumer can safely use it as an effect dependency.
  const items = useMemo(() => page?.items ?? [], [page]);

  return { page, items, total: page?.total ?? 0, loading, error, reload, replaceRow };
}

/** Delay a fast-changing value (a search box) before it drives a request. */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
