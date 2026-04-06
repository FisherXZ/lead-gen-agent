"use client";

interface TodoTask {
  id: number;
  description: string;
  status: "pending" | "in_progress" | "done" | "skipped";
  result_summary?: string;
}

interface TodoPlanCardProps {
  data: {
    tasks?: TodoTask[];
    summary?: {
      total: number;
      done: number;
      skipped: number;
      pending: number;
      in_progress: number;
      completion_rate: number;
    };
    status?: string;
    task_count?: number;
    message?: string;
    error?: string;
  };
  operation?: string;
}

function StatusDot({ status }: { status: TodoTask["status"] }) {
  if (status === "done") {
    return (
      <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round"
        className="shrink-0 text-status-green"
      >
        <polyline points="20 6 9 17 4 12" />
      </svg>
    );
  }
  if (status === "skipped") {
    return (
      <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
        className="shrink-0 text-text-tertiary"
      >
        <line x1="5" y1="12" x2="19" y2="12" />
      </svg>
    );
  }
  if (status === "in_progress") {
    return (
      <span className="inline-flex shrink-0">
        <span className="h-3 w-3 animate-spin rounded-full border-2 border-border-default border-t-accent-amber" />
      </span>
    );
  }
  // pending
  return (
    <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center">
      <span className="h-2 w-2 rounded-full bg-text-tertiary" />
    </span>
  );
}

export default function TodoPlanCard({ data, operation }: TodoPlanCardProps) {
  if (data.error) {
    return (
      <div className="px-3 py-2 text-sm text-status-red">{data.error}</div>
    );
  }

  // "created" confirmation (no tasks in output, just status)
  if (data.status === "created" && !data.tasks) {
    return (
      <div className="px-3 py-2 text-sm text-text-secondary">
        Plan created with {data.task_count ?? 0} tasks
      </div>
    );
  }

  // "updated" confirmation
  if (data.status === "updated" && !data.tasks) {
    return null; // Update confirmations are shown in the header label
  }

  // No plan yet
  if (data.message && (!data.tasks || data.tasks.length === 0)) {
    return (
      <div className="px-3 py-2 text-sm text-text-tertiary italic">
        {data.message}
      </div>
    );
  }

  const tasks = data.tasks || [];
  const summary = data.summary;

  return (
    <div className="px-3 py-2">
      {/* Task list */}
      <ul className="space-y-1.5">
        {tasks.map((task) => (
          <li key={task.id} className="flex items-start gap-2">
            <span className="mt-0.5">
              <StatusDot status={task.status} />
            </span>
            <div className="min-w-0 flex-1">
              <span className={`text-sm ${
                task.status === "skipped"
                  ? "text-text-tertiary line-through"
                  : task.status === "done"
                    ? "text-text-secondary"
                    : "text-text-primary"
              }`}>
                {task.description}
              </span>
              {task.result_summary && task.status === "done" && (
                <p className="mt-0.5 text-xs text-text-tertiary">
                  {task.result_summary}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>

      {/* Progress bar */}
      {summary && summary.total > 0 && (
        <div className="mt-3 flex items-center gap-2">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-surface-overlay">
            <div
              className="h-full rounded-full bg-accent-amber transition-all duration-300"
              style={{ width: `${Math.round(summary.completion_rate * 100)}%` }}
            />
          </div>
          <span className="shrink-0 text-[11px] tabular-nums text-text-tertiary">
            {summary.done}/{summary.total}
          </span>
        </div>
      )}
    </div>
  );
}
