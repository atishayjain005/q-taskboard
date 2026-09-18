import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CommentThread } from "@/components/CommentThread";
import type { ApiComment } from "@/types";

const comment: ApiComment = {
  id: "c1",
  task_id: "t_1",
  body: "Locked the date",
  author_id: "u_1",
  author: { id: "u_1", name: "Meera Iyer", email: "meera@taskboard.dev" },
  created_at: "2026-09-18T13:00:00.000Z",
};

function renderThread(canPost = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <CommentThread taskId="t_1" canPost={canPost} />
    </QueryClientProvider>,
  );
}

function jsonResponse(data: unknown): Response {
  return {
    ok: true,
    text: async () => JSON.stringify(data),
  } as Response;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("<CommentThread />", () => {
  it("renders comments from the API", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ comments: [comment] }));

    renderThread();

    expect(await screen.findByText("Locked the date")).toBeInTheDocument();
    expect(screen.getByText("Meera Iyer")).toBeInTheDocument();
  });

  it("posts a comment when canPost is true", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ comments: [] }))
      .mockResolvedValueOnce(jsonResponse({ comment: { ...comment, body: "New note" } }))
      .mockResolvedValueOnce(jsonResponse({ comments: [{ ...comment, body: "New note" }] }));

    renderThread(true);
    const input = await screen.findByPlaceholderText("write a comment");
    fireEvent.change(input, { target: { value: "New note" } });
    fireEvent.click(screen.getByRole("button", { name: "post" }));

    await waitFor(() => {
      const posted = vi.mocked(fetch).mock.calls.some((call) => {
        const init = call[1] as RequestInit | undefined;
        return init?.method === "POST" && String(init.body).includes("New note");
      });
      expect(posted).toBe(true);
    });
  });

  it("hides the composer for viewers", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ comments: [comment] }));

    renderThread(false);

    expect(await screen.findByText("Locked the date")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("write a comment")).not.toBeInTheDocument();
    expect(screen.getByText("viewers can read comments but cannot post")).toBeInTheDocument();
  });
});
