import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ActivityFeed, ACTIVITY_POLL_MS } from "@/components/ActivityFeed";
import type { ApiActivity } from "@/types";

const created: ApiActivity = {
  id: "a1",
  project_id: "p_1",
  event: "task_created",
  actor: { id: "u_1", name: "Meera Iyer", email: "meera@taskboard.dev" },
  actor_id: "u_1",
  task_id: "t_1",
  comment_id: null,
  metadata: { title: "Set up analytics", status: "todo" },
  created_at: "2026-09-18T13:00:00.000Z",
};

const statusChanged: ApiActivity = {
  ...created,
  id: "a2",
  event: "task_status_changed",
  metadata: { title: "Set up analytics", from_status: "todo", to_status: "in_progress" },
};

const commented: ApiActivity = {
  ...created,
  id: "a3",
  event: "comment_added",
  metadata: { task_title: "Set up analytics" },
};

function jsonResponse(data: unknown): Response {
  return {
    ok: true,
    text: async () => JSON.stringify(data),
  } as Response;
}

function renderFeed() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ActivityFeed projectId="p_1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("<ActivityFeed />", () => {
  it("renders human-readable activity rows", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ activities: [commented, statusChanged, created] }),
    );

    renderFeed();

    expect(await screen.findByText('Meera Iyer commented on "Set up analytics"')).toBeInTheDocument();
    expect(screen.getByText('Meera Iyer moved "Set up analytics" from todo to in_progress')).toBeInTheDocument();
    expect(screen.getByText('Meera Iyer created "Set up analytics"')).toBeInTheDocument();
  });

  it("shows an empty state when there is no activity", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ activities: [] }));

    renderFeed();

    expect(await screen.findByText("no activity yet")).toBeInTheDocument();
  });

  it("polls the project activity endpoint", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ activities: [created] }));

    renderFeed();
    await screen.findByText('Meera Iyer created "Set up analytics"');

    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe("/api/projects/p_1/activity");
    expect(ACTIVITY_POLL_MS).toBe(5000);
  });
});
