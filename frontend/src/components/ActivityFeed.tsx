import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";
import type { ApiActivity, ActivityEvent } from "@/types";

export const ACTIVITY_POLL_MS = 5000;

type Props = {
  projectId: string;
};

function activityMessage(activity: ApiActivity): string {
  const name = activity.actor?.name ?? "someone";
  switch (activity.event) {
    case "task_created":
      return `${name} created "${activity.metadata.title ?? "a task"}"`;
    case "task_status_changed":
      return `${name} moved "${activity.metadata.title ?? "a task"}" from ${activity.metadata.from_status} to ${activity.metadata.to_status}`;
    case "comment_added":
      return `${name} commented on "${activity.metadata.task_title ?? "a task"}"`;
    default: {
      const _exhaustive: never = activity.event;
      return _exhaustive;
    }
  }
}

const EVENT_LABELS: Record<ActivityEvent, string> = {
  task_created: "task created",
  task_status_changed: "status changed",
  comment_added: "comment",
};

export function ActivityFeed({ projectId }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["activity", projectId],
    queryFn: () => apiFetch<{ activities: ApiActivity[] }>(`/api/projects/${projectId}/activity`),
    refetchInterval: ACTIVITY_POLL_MS,
  });

  const activities = data?.activities ?? [];

  return (
    <section>
      <h2 className="text-sm font-medium mb-3">activity</h2>
      <div className="bg-surface border border-border rounded-lg">
        {isLoading && <p className="text-xs text-muted px-4 py-3">loading activity…</p>}
        {error && (
          <p className="text-sm text-red-400 px-4 py-3" role="alert">
            {error instanceof Error ? error.message : "failed to load activity"}
          </p>
        )}
        {!isLoading && !error && activities.length === 0 && (
          <p className="text-xs text-muted px-4 py-3">no activity yet</p>
        )}
        {activities.length > 0 && (
          <ul className="divide-y divide-border max-h-80 overflow-y-auto">
            {activities.map((activity) => (
              <li key={activity.id} className="px-4 py-3">
                <p className="text-sm">{activityMessage(activity)}</p>
                <p className="text-xs text-muted mt-1">
                  {EVENT_LABELS[activity.event]} ·{" "}
                  <time dateTime={activity.created_at}>
                    {new Date(activity.created_at).toLocaleString()}
                  </time>
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
