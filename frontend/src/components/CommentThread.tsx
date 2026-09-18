import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";
import type { ApiComment } from "@/types";

type Props = {
  taskId: string;
  projectId?: string;
  canPost: boolean;
};

export function CommentThread({ taskId, projectId, canPost }: Props) {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["comments", taskId],
    queryFn: () => apiFetch<{ comments: ApiComment[] }>(`/api/tasks/${taskId}/comments`),
  });

  const postComment = useMutation({
    mutationFn: (nextBody: string) =>
      apiFetch<{ comment: ApiComment }>(`/api/tasks/${taskId}/comments`, {
        method: "POST",
        body: JSON.stringify({ body: nextBody }),
      }),
    onSuccess: () => {
      setBody("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["comments", taskId] });
      if (projectId) {
        queryClient.invalidateQueries({ queryKey: ["activity", projectId] });
      }
    },
    onError: (err) => setError(err instanceof Error ? err.message : "could not post comment"),
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = body.trim();
    if (!trimmed) return;
    postComment.mutate(trimmed);
  }

  const comments = data?.comments ?? [];

  return (
    <section className="mt-6 border-t border-border pt-4">
      <h3 className="text-sm font-medium mb-3">comments</h3>

      {isLoading && <p className="text-xs text-muted">loading comments…</p>}

      {!isLoading && comments.length === 0 && (
        <p className="text-xs text-muted mb-3">no comments yet</p>
      )}

      {comments.length > 0 && (
        <ul className="space-y-3 mb-4 max-h-48 overflow-y-auto">
          {comments.map((comment) => (
            <li key={comment.id} className="text-sm">
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-medium">{comment.author.name}</span>
                <time className="text-xs text-muted" dateTime={comment.created_at}>
                  {new Date(comment.created_at).toLocaleString()}
                </time>
              </div>
              <p className="text-sm text-muted mt-1 whitespace-pre-wrap">{comment.body}</p>
            </li>
          ))}
        </ul>
      )}

      {canPost ? (
        <form onSubmit={onSubmit} className="space-y-2">
          <label className="block">
            <span className="sr-only">write a comment</span>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="write a comment"
              rows={3}
              maxLength={2000}
              className="mt-1 block w-full rounded-md bg-bg border border-border px-3 py-2 text-sm focus:border-accent focus:outline-none"
            />
          </label>
          {error && (
            <p className="text-sm text-red-400" role="alert">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={postComment.isPending || !body.trim()}
            className="text-sm px-4 py-2 rounded-md bg-accent text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {postComment.isPending ? "posting…" : "post"}
          </button>
        </form>
      ) : (
        <p className="text-xs text-muted">viewers can read comments but cannot post</p>
      )}
    </section>
  );
}
