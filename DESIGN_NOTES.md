# Atomic activity vs isolated Airtable export

Two writes look similar — “record that something happened” — but they sit on opposite sides of a consistency boundary. The activity log is a second Postgres row for the same local fact. The Airtable export is a side effect in a system we do not control. That difference is why one path uses `transaction.atomic()` and the other never rolls back the batch.

## Activity log: one fact, two rows

Task create, status change, and comment create each wrap the domain write and `Activity.log(...)` in a single `transaction.atomic()` block (`backend/projects/views.py`).

The activity row is not telemetry. It is the project’s audit trail: who created the task, who moved it, who commented. A successful mutation with no activity (or an activity whose mutation never committed) is a lie the feed will repeat forever.

Both writes are Postgres, so the database can actually give us all-or-nothing:

- If `Activity.log` fails, the task/comment insert is rolled back. Callers see an error, not a half-applied change. `TestActivity.test_failed_activity_write_rolls_back_task_create` locks this in.
- If the request dies after commit, both rows are durable together. The poller on the project page can trust that every listed event has a matching object.

There is no remote call inside that transaction, so we do not hold a DB lock while waiting on the network.

## Airtable export: the remote write is already committed

`export_tasks` walks tasks one at a time. On success it immediately stores `airtable_record_id`. On `TransientAirtableError` / `PermanentAirtableError` it appends that task to `failed` and continues. There is no wrapping transaction around the batch.

Airtable `create` / `update` is not a Postgres write. Once pyairtable returns a record id, that row exists in the base even if we later raise in Python. `transaction.rollback()` cannot un-create it.

If we *did* put the whole batch in one DB transaction and rolled back on task 6 of 8:

1. Tasks 1–5 would already exist (or already be updated) in Airtable.
2. Rolling back would forget the `airtable_record_id` values we just saved.
3. The next export would `create` those five tasks again and duplicate them in the base.

Idempotency depends on remembering the remote id **as soon as the remote write succeeds**. Isolating failures is what keeps that memory intact.

Per-task isolation also matches how Airtable actually fails. A 422 on one record (bad select value, unknown field) is independent of the next record. Transient 429/5xx are retried with exponential backoff on that task only (`0.1s`, then `0.2s`, max 3 attempts). Exhausted transients are reported in `failed` like permanents; they do not abort siblings that already synced.

The HTTP response is a summary, not a promise of atomicity: `{exported, created, updated, failed}`. Partial success is the honest result. The operator retries; stored ids make the retry an update, not a second copy.

## Rule of thumb

Use a database transaction when every participant is in the same database and the rows only make sense together.

Do not pretend an external API is in that transaction. Persist each successful remote effect, skip the row that cannot be synced, and make the next run idempotent.
