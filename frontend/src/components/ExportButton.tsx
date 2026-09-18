import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";

export type ExportResult = {
  exported: number;
  created: number;
  updated: number;
  failed: Array<{ task_id: string; title: string; error: string }>;
};

type Props = {
  projectId: string;
  canExport: boolean;
};

export function ExportButton({ projectId, canExport }: Props) {
  const exportTasks = useMutation({
    mutationFn: () =>
      apiFetch<ExportResult>(`/api/projects/${projectId}/export`, { method: "POST" }),
  });

  if (!canExport) {
    return null;
  }

  const result = exportTasks.data;
  const errorMessage =
    exportTasks.error instanceof Error ? exportTasks.error.message : null;

  return (
    <div className="shrink-0 text-right">
      <button
        type="button"
        onClick={() => exportTasks.mutate()}
        disabled={exportTasks.isPending}
        className="text-sm px-4 py-2 rounded-md border border-border hover:border-accent disabled:opacity-50"
      >
        {exportTasks.isPending ? "exporting…" : "export to Airtable"}
      </button>
      {errorMessage && (
        <p className="text-xs text-red-400 mt-2" role="alert">
          {errorMessage}
        </p>
      )}
      {result && (
        <div className="mt-2 text-left">
          <p className="text-xs text-muted" role="status">
            exported {result.exported} ({result.created} created, {result.updated} updated)
            {result.failed.length > 0 ? `, ${result.failed.length} failed` : ""}
          </p>
          {result.failed.length > 0 && (
            <ul className="text-xs text-red-400 mt-1 space-y-1">
              {result.failed.map((item) => (
                <li key={item.task_id}>
                  {item.title}: {item.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
