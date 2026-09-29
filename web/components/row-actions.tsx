"use client";

/**
 * Renders the buttons a row may expose. The list comes from the API's
 * ``allowed_actions``, which the authorization engine computes per row - so the
 * board never shows a button the server would reject.
 */

import type { MemberSummary } from "@/lib/types";

export const ACTION_LABELS: Record<string, string> = {
  pause: "暂停",
  resume: "继续",
  rerun: "重跑",
  cancel: "取消",
  claim: "领取",
  // No member picker exists yet; reassign without a target releases the task
  // back to the pool. Rename once a picker lands.
  reassign: "退回待领取",
  submit: "提交",
  approve: "通过",
  reject: "驳回",
  export: "导出",
  collect: "采集",
  assign: "分派",
};

const PRIMARY_ACTIONS = new Set(["claim", "submit", "approve", "resume", "assign"]);
const NAVIGATION_ACTIONS = new Set(["view"]);

export function RowActions({
  actions,
  pending = false,
  members = [],
  onRun,
}: {
  actions: string[];
  pending?: boolean;
  members?: MemberSummary[];
  onRun: (action: string, assigneeId?: string) => void;
}) {
  const visible = actions.filter((action) => !NAVIGATION_ACTIONS.has(action));
  if (visible.length === 0) return null;

  return (
    <div className="row-actions">
      {visible.map((action) => {
        if (action === "assign") {
          return (
            <AssignPicker
              key={action}
              members={members}
              disabled={pending}
              onRun={onRun}
            />
          );
        }
        return (
          <button
            key={action}
            type="button"
            className={`button ${PRIMARY_ACTIONS.has(action) ? "button-primary" : "button-secondary"}`}
            disabled={pending}
            onClick={() => onRun(action)}
          >
            {pending ? "处理中…" : (ACTION_LABELS[action] ?? action)}
          </button>
        );
      })}
    </div>
  );
}

function AssignPicker({
  members,
  disabled,
  onRun,
}: {
  members: MemberSummary[];
  disabled: boolean;
  onRun: (action: string, assigneeId?: string) => void;
}) {
  if (members.length === 0) {
    return (
      <button
        type="button"
        className="button button-primary"
        disabled={disabled}
        onClick={() => onRun("assign")}
      >
        分派
      </button>
    );
  }
  return (
    <span className="assign-picker">
      <select className="assign-select" defaultValue="" aria-label="选择分派成员" disabled={disabled}>
        <option value="" disabled>分派给…</option>
        {members.map((m) => (
          <option key={m.id} value={m.id}>{m.displayName}（{m.roleLabel}）</option>
        ))}
      </select>
      <button
        type="button"
        className="button button-primary"
        disabled={disabled}
        onClick={(event) => {
          const select = event.currentTarget.previousElementSibling as HTMLSelectElement | null;
          const value = select?.value;
          if (value) onRun("assign", value);
        }}
      >
        确认
      </button>
    </span>
  );
}
