"use client";

import { useCallback, useState } from "react";
import { ApiProblem, apiClient } from "@/lib/api-client";

export type ActionKind = "content-runs" | "human-tasks";
export type ActionableRow = { id: string; etag: string };

export type ActionNotice = { tone: "conflict" | "error" | "success"; title: string; detail: string };

/** Server `code` -> Chinese copy the board shows; falls back to `ProblemDetails.detail`. */
const NOTICE_COPY: Record<string, { tone: ActionNotice["tone"]; title: string; detail: string }> = {
  precondition_required: { tone: "conflict", title: "缺少版本校验", detail: "页面数据已过期，请重新加载后再操作。" },
  invalid_precondition: { tone: "conflict", title: "版本校验无效", detail: "版本标识格式不正确，请重新加载页面。" },
  version_conflict: { tone: "conflict", title: "数据已被更新", detail: "其他成员已修改这条记录，系统不会覆盖。请重新加载并确认后再操作。" },
  illegal_transition: { tone: "error", title: "当前状态不允许该操作", detail: "记录状态已变化，请重新加载后确认。" },
  unsupported_action: { tone: "error", title: "该操作尚未接入", detail: "此动作依赖后台异步任务，暂未开放。" },
  permission_missing: { tone: "error", title: "权限不足", detail: "当前角色没有执行该操作的权限。" },
  separation_of_duties: { tone: "error", title: "职责分离限制", detail: "不能审批自己创建或处理的内容，请转派给其他成员。" },
};

/**
 * Copy shown after a *successful* action. Without it a click with no visible state
 * change - ``export`` in particular - looks like it did nothing.
 */
const SUCCESS_COPY: Record<string, { title: string; detail: string }> = {
  export: { title: "已生成导出文件", detail: "打开任务详情页的「导出记录」即可下载成品。" },
  collect: { title: "已采集匹配素材", detail: "与品牌或标题相关的素材已关联到该任务。" },
  assign: { title: "已分派处理人", detail: "任务已指派给对方，并重置了领取租约。" },
  claim: { title: "已领取任务", detail: "任务已归到你的名下，请在到期前处理。" },
  approve: { title: "已通过", detail: "审批结论已记录。" },
  reject: { title: "已驳回", detail: "审批结论已记录。" },
  submit: { title: "已提交", detail: "处理结果已提交。" },
  pause: { title: "已暂停", detail: "任务已暂停，可随时继续。" },
  resume: { title: "已继续", detail: "任务已重新进入运行。" },
  rerun: { title: "已重新运行", detail: "后台正在重新生成正文。" },
  cancel: { title: "已取消", detail: "任务已取消。" },
  reassign: { title: "已退回待领取", detail: "任务已回到待领取队列。" },
};

/**
 * Runs a row-level workflow action and feeds the server's updated row back to
 * the caller, so the board never guesses what the new state is.
 */
export function useResourceAction<T extends ActionableRow>(kind: ActionKind, onUpdated: (row: T) => void) {
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<ActionNotice | null>(null);

  const run = useCallback(
    async (row: T, action: string, assigneeId?: string) => {
      setPendingId(row.id);
      setNotice(null);
      try {
        // ``kind`` selects the endpoint, so its return type is the row type.
        const updated = (kind === "content-runs"
          ? await apiClient.runContentAction(row.id, { action }, row.etag)
          : await apiClient.runHumanTaskAction(
              row.id,
              assigneeId ? { action, assigneeId } : { action },
              row.etag,
            )) as unknown as T;
        onUpdated(updated);
        const copy = SUCCESS_COPY[action];
        if (copy) setNotice({ tone: "success", ...copy });
      } catch (cause) {
        const problem = cause instanceof ApiProblem ? cause.problem : null;
        const code = problem?.code ?? "";
        setNotice(
          NOTICE_COPY[code] ?? {
            tone: "error",
            title: "操作失败",
            detail: problem?.detail || problem?.title || "请稍后重试。",
          },
        );
      } finally {
        setPendingId(null);
      }
    },
    [kind, onUpdated],
  );

  const clearNotice = useCallback(() => setNotice(null), []);

  return { run, pendingId, notice, clearNotice };
}
