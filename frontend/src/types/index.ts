export type Role = "admin" | "member" | "viewer";
export type TaskStatus = "todo" | "in_progress" | "review" | "done";

export type ApiUser = {
  id: string;
  email: string;
  name: string;
};

export type ApiTask = {
  id: string;
  projectId: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  assigneeId: string | null;
  createdById: string;
  position: number;
  createdAt: string;
  updatedAt: string;
  assignee?: ApiUser | null;
};

export type ApiProjectMember = {
  id: string;
  role: Role;
  user: ApiUser;
};

export type ApiProjectDetail = {
  id: string;
  name: string;
  description: string | null;
  ownerId: string;
  owner: ApiUser;
  memberships: ApiProjectMember[];
  tasks: ApiTask[];
  createdAt: string;
  updatedAt: string;
};

export type ApiComment = {
  id: string;
  task_id: string;
  body: string;
  author_id: string;
  author: ApiUser;
  created_at: string;
};

export type ActivityEvent = "task_created" | "task_status_changed" | "comment_added";

export type ApiActivity = {
  id: string;
  project_id: string;
  event: ActivityEvent;
  actor: ApiUser | null;
  actor_id: string | null;
  task_id: string | null;
  comment_id: string | null;
  metadata: {
    title?: string;
    status?: string;
    from_status?: string;
    to_status?: string;
    task_title?: string;
  };
  created_at: string;
};

export const STATUS_LABELS: Record<TaskStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  review: "In review",
  done: "Done",
};

export const STATUS_ORDER: TaskStatus[] = ["todo", "in_progress", "review", "done"];
