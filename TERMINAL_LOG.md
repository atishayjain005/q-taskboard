# Terminal log — TaskBoard assignment

Session: 18 Sep 2026. Stack: Docker Compose (backend :8000, frontend :3001, Postgres 16). Login used throughout: `meera@taskboard.dev` / `password123`. Airtable secrets are not logged. JWT tokens are redacted.

---

## 1. Setup

```text
$ docker --version
Docker version 29.6.2, build dfc4efb

$ docker compose version
Docker Compose version v5.3.1

$ node --version
v22.23.2

$ python3 --version
Python 3.13.2

$ docker compose exec -T backend python --version
Python 3.12.14

$ docker compose exec -T db postgres --version
postgres (PostgreSQL) 16.14
```

No host Postgres. App images were already built, so Compose was faster than a manual venv.

```text
$ docker compose up -d
# backend raced Postgres on first start (connection refused)
$ docker compose restart backend
$ docker compose exec -T backend python manage.py migrate
$ docker compose exec -T backend python manage.py seed
```

Vite inside the frontend container was proxying `/api` to `127.0.0.1:8000`. `API_PROXY_TARGET=http://backend:8000` was added so the UI can reach Django.

```text
$ docker compose ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}'
NAME                     STATUS          PORTS
q-taskboard-backend-1    Up              0.0.0.0:8000->8000/tcp
q-taskboard-db-1         Up              0.0.0.0:5432->5432/tcp
q-taskboard-frontend-1   Up              0.0.0.0:3001->3000/tcp
```

Applied migrations by the end of the session:

```text
projects
 [X] 0001_initial
 [X] 0002_comment
 [X] 0003_activity
 [X] 0004_airtable_record_id
users
 [X] 0001_initial
```

Frontend is on **http://localhost:3001** (Compose maps `3001:3000`). API is **http://localhost:8000**.

---

## 2. Initial test run (starting state, before feature work)

```text
$ docker compose exec -T backend python -m pytest -q
...............                                                          [100%]
15 passed, ... warnings in ~5s

$ docker compose exec -T frontend npm test
 Test Files  2 passed (2)
      Tests  9 passed (9)
```

JWT warnings only: HMAC key is 20 bytes (`dev-secret-change-me`), below the 32-byte recommendation.

---

## 3. Before / after curl proofs (search SQLi + PATCH IDOR)

Highest-impact review finding was task search interpolating `q` into raw SQL (`REVIEW.md` #1). A live SQL-injection leak PoC was **not** executed. The same `q` value the old query treated as SQL is used below **after** the ORM patch; it is a literal search string and returns no rows.

Q3 Launch project: `e2172119-5181-4c33-8b89-8c3db8d4046d`  
Task “Record demo video”: `1d00ce49-43b5-4c5a-b034-fbb3f13985e7`

### 3a. Search — after the Q-object fix

```bash
TOKEN=$(curl -sS -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"meera@taskboard.dev","password":"password123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
Q3=e2172119-5181-4c33-8b89-8c3db8d4046d

curl -sS -G "http://localhost:8000/api/projects/$Q3/tasks" \
  --data-urlencode "q=' OR 1=1 --" \
  -H "Authorization: Bearer $TOKEN"
```

**Response (after):** HTTP 200. The payload is treated as `ILIKE`, not SQL. No other project’s tasks leak.

```json
{
  "task_count": 0,
  "titles": []
}
```

Legitimate search still works:

```bash
curl -sS -G "http://localhost:8000/api/projects/$Q3/tasks" \
  --data-urlencode "q=demo" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "titles": ["Record demo video"]
}
```

Regression test: `test_task_search_does_not_leak_other_project_tasks`.

### 3b. PATCH IDOR — after membership check

`lina@example.com` is not a member of Q3 Launch. `dev@example.com` is a viewer.

```bash
LINA=$(curl -sS -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"lina@example.com","password":"password123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')

curl -sS -X PATCH http://localhost:8000/api/tasks/1d00ce49-43b5-4c5a-b034-fbb3f13985e7 \
  -H "Authorization: Bearer $LINA" \
  -H 'Content-Type: application/json' \
  -d '{"title":"hijacked"}'
```

**Response (after):**

```json
HTTP 403
{"error": "forbidden"}
```

Viewer:

```bash
curl -sS -X PATCH http://localhost:8000/api/tasks/1d00ce49-43b5-4c5a-b034-fbb3f13985e7 \
  -H "Authorization: Bearer $DEV" \
  -H 'Content-Type: application/json' \
  -d '{"title":"viewer edit"}'
```

```json
HTTP 403
{"error": "viewers cannot update tasks"}
```

Before the patch, this view loaded the task and saved with no membership check (see `REVIEW.md` #2). Live 200s from that path were not captured; the after-fix 403s and `test_patch_task_requires_membership` / `test_viewers_cannot_patch_tasks` are the proof it is closed.

---

## 4. Part 3c — Airtable export (live base, twice)

`POST /api/projects/e2172119-5181-4c33-8b89-8c3db8d4046d/export` as Meera (admin). Credentials from env only.

First UI export after field mapping (empty `airtable_record_id`s): **8 created, 0 updated**.  
Immediate second UI export: **0 created, 8 updated**.

Two consecutive API runs after ids were stored:

```bash
curl -sS -X POST \
  http://localhost:8000/api/projects/e2172119-5181-4c33-8b89-8c3db8d4046d/export \
  -H "Authorization: Bearer $TOKEN"
```

**Run 1**

```json
{
  "exported": 8,
  "created": 0,
  "updated": 8,
  "failed": []
}
```

**Run 2**

```json
{
  "exported": 8,
  "created": 0,
  "updated": 8,
  "failed": []
}
```

Stored Airtable record ids were **identical** across both runs (`identical_record_ids: true`, 8/8, none missing, none changed):

| Task | `airtable_record_id` |
|------|----------------------|
| Draft press release | `recyK6o1GUFF4Nam6` |
| Finalize launch date with marketing | `recUJi1ZOE264YMDv` |
| Prepare customer email blast | `recF92QBMm7yDAUrU` |
| QA the new signup flow end-to-end | `recSdjhyhNJUCr8Mf` |
| Record demo video | `recfgbwnkaKH6lTfs` |
| Set up analytics dashboards | `rec2N3pQE3ypL4AcA` |
| Update pricing page copy | `reclq1u9sf7sDui3J` |
| test_task | `rec2ryzVRrgtYdPMm` |

Rows are in the configured Airtable `Tasks` table (`External ID`, `Title`, `Description`, `Status`, `Assignee`, `Position`). Viewers cannot export (`test_viewers_cannot_export` → 403).

---

## 5. Parts 3a / 3b — comments and activity

Task “Finalize launch date with marketing”: `52adb00d-2775-4fae-aea8-1448a68d0e24`

### Comments (GET members, POST blocked for viewers)

```bash
curl -sS http://localhost:8000/api/tasks/52adb00d-2775-4fae-aea8-1448a68d0e24/comments \
  -H "Authorization: Bearer $TOKEN"
```

```json
HTTP 200
[
  {
    "author": {"email": "meera@taskboard.dev", "name": "Meera Iyer"},
    "body": "Locked the date with marketing — Sept 18.",
    "created_at": "2026-09-18T13:40:41.033769Z"
  },
  {
    "author": {"email": "arjun@taskboard.dev", "name": "Arjun Rao"},
    "body": "Press embargo until the 17th.",
    "created_at": "2026-09-18T13:40:41.034998Z"
  }
]
```

```bash
curl -sS -X POST \
  http://localhost:8000/api/tasks/52adb00d-2775-4fae-aea8-1448a68d0e24/comments \
  -H "Authorization: Bearer $DEV" \
  -H 'Content-Type: application/json' \
  -d '{"body":"viewer should not post"}'
```

```json
HTTP 403
{"error": "viewers cannot comment"}
```

Comments are append-only (no PATCH/DELETE on the API; model `save()` raises if the row already exists).

### Activity feed (project-scoped, newest first)

```bash
curl -sS http://localhost:8000/api/projects/e2172119-5181-4c33-8b89-8c3db8d4046d/activity \
  -H "Authorization: Bearer $TOKEN"
```

```json
HTTP 200
{
  "count": 6,
  "newest": [
    {"event": "comment_added", "actor": "Meera Iyer", "metadata": {"task_title": "test_task"}},
    {"event": "task_created", "actor": "Meera Iyer", "metadata": {"title": "test_task", "status": "review"}},
    {"event": "comment_added", "actor": "Arjun Rao", "metadata": {"task_title": "Finalize launch date with marketing"}},
    {"event": "comment_added", "actor": "Meera Iyer", "metadata": {"task_title": "Finalize launch date with marketing"}},
    {"event": "task_status_changed", "actor": "Kavya Reddy", "metadata": {"title": "Record demo video", "from_status": "todo", "to_status": "in_progress"}},
    {"event": "task_created", "actor": "Meera Iyer", "metadata": {"title": "Finalize launch date with marketing", "status": "done"}}
  ]
}
```

Non-member (`lina@example.com`):

```json
HTTP 403
{"error": "forbidden"}
```

Activity is written in the same `transaction.atomic()` as the mutation. Airtable export is not; see `DESIGN_NOTES.md`.

---

## 6. Final test run (18 Sep 2026, 13:56 UTC)

```text
$ docker compose exec -T backend python -m pytest \
    projects/tests.py users/tests.py projects/test_airtable_export.py -q --tb=line

.....................................                                    [100%]
37 passed, 48 warnings in 8.31s
```

```text
$ docker compose exec -T frontend npm test

 RUN  v2.1.9 /app
 ✓ src/tests/schemas.test.ts (6 tests)
 ✓ src/tests/TaskCard.test.tsx (3 tests)
 ✓ src/tests/ExportButton.test.tsx (3 tests)
 ✓ src/tests/ActivityFeed.test.tsx (3 tests)
 ✓ src/tests/CommentThread.test.tsx (3 tests)

 Test Files  5 passed (5)
      Tests  18 passed (18)
 Duration  1.10s
```

| Suite | Starting | Final |
|-------|----------|-------|
| Backend pytest | 15 passed | **37 passed** |
| Frontend vitest | 9 passed (2 files) | **18 passed (5 files)** |
| Combined | 24 | **55** |

Warnings remain the JWT key-length notices only. Airtable unit tests use `MockAirtableClient`; live export is the section 4 curl, not CI.
