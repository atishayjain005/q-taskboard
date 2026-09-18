import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ExportButton } from "@/components/ExportButton";

function jsonResponse(data: unknown, ok = true): Response {
  return {
    ok,
    status: ok ? 200 : 403,
    text: async () => JSON.stringify(data),
  } as Response;
}

function renderButton(canExport = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ExportButton projectId="p_1" canExport={canExport} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("<ExportButton />", () => {
  it("is hidden when the user cannot export", () => {
    renderButton(false);
    expect(screen.queryByRole("button", { name: "export to Airtable" })).not.toBeInTheDocument();
  });

  it("posts to the export endpoint and shows the summary", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ exported: 2, created: 1, updated: 1, failed: [] }),
    );

    renderButton(true);
    fireEvent.click(screen.getByRole("button", { name: "export to Airtable" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "exported 2 (1 created, 1 updated)",
    );
    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe("/api/projects/p_1/export");
    expect((vi.mocked(fetch).mock.calls[0]?.[1] as RequestInit).method).toBe("POST");
  });

  it("reports isolated failures", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({
        exported: 1,
        created: 1,
        updated: 0,
        failed: [{ task_id: "t1", title: "Bad", error: "422" }],
      }),
    );

    renderButton(true);
    fireEvent.click(screen.getByRole("button", { name: "export to Airtable" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("1 failed");
    });
  });
});
