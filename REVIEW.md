# Production review — TaskBoard

Reviewed the Django/DRF backend and React frontend as they stand today. Ranking is by **real exploitability and blast radius**: security and data integrity first, then performance. Other gaps exist (CORS, 30-day access tokens in `localStorage`, missing rate limits, snake_case API vs camelCase client types); they are not in the top four.

| Rank | Issue | Category | Blast radius |
|------|--------|----------|--------------|
| 1 | SQL injection in task search | Security | Entire `tasks` table (read/modify/delete) |
| 2 | Task `PATCH` has no membership check | Security / integrity | Any authenticated user can rewrite any task |
| 3 | Known JWT signing secret shipped as the default | Security | Forge a token for any user |
| 4 | Project list N+1 plus loading every task to count them | Performance | Dashboard latency and memory grow with every task |

---

## 1. SQL injection in `GET /api/projects/:id/tasks?q=`

**Impact:** Critical. An authenticated project member can run arbitrary SQL through the `q` query parameter. That is full read (and likely write) access to the database, including tasks in projects the caller is not a member of.

**Where:** `backend/projects/views.py` lines 110–123

```110:123:backend/projects/views.py
        q = request.query_params.get('q')
        if q:
            with connection.cursor() as cursor:
                sql = (
                    f"SELECT id, project_id, title, description, status, assignee_id, created_by_id, position, created_at, updated_at "
                    f"FROM tasks "
                    f"WHERE project_id = '{project_id}' "
                    f"AND (title ILIKE '%{q}%' OR description ILIKE '%{q}%') "
                    f"ORDER BY position ASC"
                )
                cursor.execute(sql)
                columns = [col[0] for col in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return Response({'tasks': rows})
```

`q` is interpolated into the statement. A value such as `' OR 1=1 --` breaks out of the `ILIKE` predicate and returns every row in `tasks`. Follow-on payloads can `UNION` other tables or issue DML. Membership is checked *before* this block, so any member (including a viewer) can fire it.

The raw-SQL path also skips `TaskSerializer`, so search results do not match the JSON shape of the ORM path.

**Fix:** Delete the cursor. Filter with the ORM and parameterized lookups; keep the same serializer as the unfiltered list.

```python
from django.db.models import Q

class TaskListCreateView(APIView):
    def get(self, request, project_id):
        membership = _get_membership(request.user, project_id)
        if not membership:
            return Response({'error': 'forbidden'}, status=status.HTTP_403_FORBIDDEN)

        tasks = (
            Task.objects
            .filter(project_id=project_id)
            .select_related('assignee')
            .order_by('status', 'position')
        )
        q = request.query_params.get('q')
        if q:
            tasks = tasks.filter(
                Q(title__icontains=q) | Q(description__icontains=q)
            )
        return Response({'tasks': TaskSerializer(tasks, many=True).data})
```

Add a test that `q` containing `' OR 1=1 --` does **not** return another project's tasks. Do not reintroduce `cursor.execute` with f-strings.

---

## 2. `PATCH /api/tasks/:id` is an IDOR — no authorization at all

**Impact:** Critical. Any logged-in user can change title, description, status, and assignee of **any** task if they know (or can guess) the UUID. Viewers can edit. Non-members can edit. Delete on the same view correctly checks membership; patch does not.

**Where:** `backend/projects/views.py` lines 165–185, contrasted with delete at 193–197

```165:185:backend/projects/views.py
    def patch(self, request, task_id):
        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            return Response({'error': 'not found'}, status=status.HTTP_404_NOT_FOUND)

        if 'title' in request.data:
            task.title = request.data['title'].strip()
        if 'description' in request.data:
            task.description = request.data['description'] or None
        if 'status' in request.data:
            new_status = request.data['status']
            if new_status not in ('todo', 'in_progress', 'review', 'done'):
                return Response({'error': 'invalid status'}, status=status.HTTP_400_BAD_REQUEST)
            task.status = new_status
        if 'assigneeId' in request.data:
            task.assignee_id = request.data['assigneeId'] or None
        task.save()
```

Integrity holes on the same path:

- `assigneeId` is not required to be a member of `task.project` (same bug on create at line 156). A caller can attach any user PK, or send a garbage UUID and 500 on FK violation.
- `title` is not re-validated (empty string after `strip()`, or longer than `Task.title`'s 500 chars). Create requires a non-empty title; patch does not.
- Existing tests cover delete membership (`backend/projects/tests.py` 89–99) but never patch, which is why this shipped.

**Fix:** Mirror delete: load the task, require a membership that can edit, then validate fields before save.

```python
def patch(self, request, task_id):
    try:
        task = Task.objects.select_related('project').get(id=task_id)
    except Task.DoesNotExist:
        return Response({'error': 'not found'}, status=status.HTTP_404_NOT_FOUND)

    membership = _get_membership(request.user, str(task.project_id))
    if not membership:
        return Response({'error': 'forbidden'}, status=status.HTTP_403_FORBIDDEN)
    if not _can_edit_tasks(membership.role):
        return Response({'error': 'viewers cannot update tasks'}, status=status.HTTP_403_FORBIDDEN)

    if 'title' in request.data:
        title = (request.data.get('title') or '').strip()
        if not title or len(title) > 500:
            return Response({'error': 'invalid title'}, status=status.HTTP_400_BAD_REQUEST)
        task.title = title
    if 'description' in request.data:
        task.description = request.data['description'] or None
    if 'status' in request.data:
        new_status = request.data['status']
        if new_status not in ('todo', 'in_progress', 'review', 'done'):
            return Response({'error': 'invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        task.status = new_status
    if 'assigneeId' in request.data:
        assignee_id = request.data['assigneeId'] or None
        if assignee_id and not Membership.objects.filter(
            project_id=task.project_id, user_id=assignee_id
        ).exists():
            return Response({'error': 'assignee must be a project member'}, status=status.HTTP_400_BAD_REQUEST)
        task.assignee_id = assignee_id

    task.save()
    task_data = TaskSerializer(Task.objects.select_related('assignee').get(id=task_id)).data
    return Response({'task': task_data})
```

Apply the same assignee-must-be-a-member check in `TaskListCreateView.post` (line 156). Add tests: non-member 403, viewer 403, assignee outside the project 400.

---

## 3. JWT is signed with a committed, guessable secret

**Impact:** High. SimpleJWT signs access tokens with Django `SECRET_KEY`. That key is hardcoded in compose and `.env.example`, and settings fall back to another public string if the env var is missing. Anyone who can hit `/api/*` can mint a Bearer token for any user id and pass every `IsAuthenticated` check. Combined with issue 2, that is a full-data rewrite without stealing a password. Combined with issue 1, it is SQL as any member.

**Where:**

```7:9:backend/taskboard/settings.py
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-secret-change-me-in-production')
DEBUG = os.environ.get('DEBUG', 'true').lower() == 'true'
ALLOWED_HOSTS = ['*']
```

```51:56:backend/taskboard/settings.py
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=30),
    'AUTH_HEADER_TYPES': ('Bearer',),
}
```

```28:29:docker-compose.yml
      DJANGO_SECRET_KEY: dev-secret-change-me
      DEBUG: "true"
```

The HMAC key is 20 bytes; pytest already warns it is below the RFC 7518 minimum of 32. `DEBUG` defaults **on**, so failed requests leak stack traces. `CORS_ALLOW_ALL_ORIGINS = True` (line 56) lets any website call the API; tokens live in `localStorage` (`frontend/src/lib/api-client.ts` 5–24), so XSS on the origin steals a 30-day credential.

**Fix:**

1. Require a strong secret at boot. Never ship a working default.

```python
from django.core.exceptions import ImproperlyConfigured

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY or SECRET_KEY.startswith('dev-secret'):
    raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set to a unique 32+ byte value')

DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
ALLOWED_HOSTS = [h for h in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h]
```

2. Generate the compose secret from the environment (`DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY}`) and keep `.env` out of git. Rotate immediately; every token issued with `dev-secret-change-me` is forged forever until you rotate.

3. Shorten access tokens and issue a refresh token from `RefreshToken.for_user` (you already create a refresh object in `backend/users/views.py` line 11 and then throw it away). Something like 15-minute access / 7-day rotating refresh.

4. Set `CORS_ALLOW_ALL_ORIGINS = False` and list the frontend origin. Turn `DEBUG` off in any deployed environment.

---

## 4. `GET /api/projects` does N+1 COUNT queries and loads every task to do it

**Impact:** High for performance, once a workspace has real data. The dashboard query prefetches **all task rows** for every project the user belongs to, then ignores that cache and issues `COUNT(*)` per project. Ten projects with 2k tasks means ~10 extra round-trips plus pulling 20k task rows into the app server for a number the UI only displays as `12 tasks`.

**Where:** `backend/projects/views.py` lines 23–41

```23:41:backend/projects/views.py
        memberships = (
            Membership.objects
            .filter(user=request.user)
            .select_related('project__owner')
            .prefetch_related('project__tasks')
            .order_by('-project__created_at')
        )
        projects = []
        for m in memberships:
            p = m.project
            projects.append({
                'id': str(p.id),
                'name': p.name,
                'description': p.description,
                'role': m.role,
                'owner': UserSerializer(p.owner).data,
                'taskCount': p.tasks.count(),
                'createdAt': p.created_at.isoformat(),
            })
```

`RelatedManager.count()` always hits the database. `prefetch_related('project__tasks')` is wasted work and the wrong tool for a count. The same unbounded load exists on project detail (`tasks = TaskSerializer(many=True)` in `backend/projects/serializers.py` line 41) with no pagination.

**Fix:** Annotate a single aggregated count and drop the prefetch.

```python
from django.db.models import Count

memberships = (
    Membership.objects
    .filter(user=request.user)
    .select_related('project__owner')
    .annotate(task_count=Count('project__tasks'))
    .order_by('-project__created_at')
)
# ...
'taskCount': m.task_count,
```

That is one SQL statement with a `JOIN`/`COUNT`. For project detail, stop embedding the full task list in `ProjectDetailSerializer` and serve tasks from `GET /api/projects/:id/tasks` with a cap or cursor (the search endpoint already exists). Add a composite index if you filter by `project_id` + `position` under search; `tasks(project, status)` already exists (`backend/projects/models.py` line 62).
