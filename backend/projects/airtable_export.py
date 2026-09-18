import time

from django.conf import settings
from pyairtable import Api


class TransientAirtableError(Exception):
    """Retryable Airtable failure (timeouts, 429, 5xx)."""


class PermanentAirtableError(Exception):
    """Non-retryable Airtable failure; skip this task and continue."""


TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
INITIAL_BACKOFF_SECONDS = 0.1
MAX_ATTEMPTS = 3

AIRTABLE_STATUS = {
    'todo': 'Todo',
    'in_progress': 'In Progress',
    'review': 'Review',
    'done': 'Done',
}


def fields_for_task(task):
    assignee = ''
    if getattr(task, 'assignee', None) is not None:
        assignee = task.assignee.email
    status_key = task.status
    if status_key in AIRTABLE_STATUS:
        status = AIRTABLE_STATUS[status_key]
    else:
        status = status_key
    return {
        'External ID': str(task.id),
        'Title': task.title,
        'Description': task.description or '',
        'Status': status,
        'Assignee': assignee,
        'Position': getattr(task, 'position', 0) or 0,
    }


def is_transient(exc):
    if isinstance(exc, TransientAirtableError):
        return True
    if isinstance(exc, PermanentAirtableError):
        return False
    status = getattr(getattr(exc, 'response', None), 'status_code', None)
    if status in TRANSIENT_STATUS_CODES:
        return True
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    return False


def call_with_retry(fn, *, sleep=time.sleep, max_attempts=MAX_ATTEMPTS, backoff=INITIAL_BACKOFF_SECONDS):
    delay = backoff
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if not is_transient(exc) or attempt == max_attempts:
                if isinstance(exc, (TransientAirtableError, PermanentAirtableError)):
                    raise
                raise PermanentAirtableError(str(exc)) from exc
            sleep(delay)
            delay *= 2
    raise last_error


def _persist_record_id(task, record_id):
    if task.airtable_record_id == record_id:
        return
    task.airtable_record_id = record_id
    task.save(update_fields=['airtable_record_id'])


def _export_one(task, client, sleep, max_attempts):
    fields = fields_for_task(task)
    if task.airtable_record_id:
        record = call_with_retry(
            lambda: client.update(task.airtable_record_id, fields),
            sleep=sleep,
            max_attempts=max_attempts,
        )
        action = 'updated'
    else:
        record = call_with_retry(
            lambda: client.create(fields),
            sleep=sleep,
            max_attempts=max_attempts,
        )
        action = 'created'
    record_id = record['id']
    _persist_record_id(task, record_id)
    return action


def export_tasks(tasks, client, *, sleep=time.sleep, max_attempts=MAX_ATTEMPTS):
    created = 0
    updated = 0
    failed = []
    for task in tasks:
        try:
            action = _export_one(task, client, sleep, max_attempts)
            if action == 'created':
                created += 1
            else:
                updated += 1
        except (TransientAirtableError, PermanentAirtableError) as exc:
            failed.append({
                'task_id': str(task.id),
                'title': task.title,
                'error': str(exc),
            })
    return {
        'exported': created + updated,
        'created': created,
        'updated': updated,
        'failed': failed,
    }


class PyAirtableClient:
    def __init__(self, table):
        self.table = table

    def create(self, fields):
        try:
            return self.table.create(fields)
        except Exception as exc:
            _raise_classified(exc)
            raise

    def update(self, record_id, fields):
        try:
            return self.table.update(record_id, fields)
        except Exception as exc:
            _raise_classified(exc)
            raise


def _raise_classified(exc):
    if is_transient(exc):
        raise TransientAirtableError(str(exc)) from exc
    raise PermanentAirtableError(str(exc)) from exc


def get_airtable_client():
    api_key = getattr(settings, 'AIRTABLE_API_KEY', '') or ''
    base_id = getattr(settings, 'AIRTABLE_BASE_ID', '') or ''
    table_name = getattr(settings, 'AIRTABLE_TABLE_NAME', 'Tasks') or 'Tasks'
    if not api_key or not base_id:
        raise PermanentAirtableError('airtable is not configured')
    table = Api(api_key).table(base_id, table_name)
    return PyAirtableClient(table)
