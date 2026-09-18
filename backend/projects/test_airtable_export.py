import pytest
from rest_framework.test import APIClient
from projects.airtable_export import (
    PermanentAirtableError,
    TransientAirtableError,
    call_with_retry,
    export_tasks,
    fields_for_task,
)
from projects.airtable_mock import MockAirtableClient
from projects.models import Membership, Project, Task
from users.models import User


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(email='meera@taskboard.dev', name='Meera Iyer', password='password123')


@pytest.fixture
def auth_client(client, user):
    response = client.post('/api/auth/login', {
        'email': 'meera@taskboard.dev',
        'password': 'password123',
    }, format='json')
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['token']}")
    return client


class FakeTask:
    def __init__(self, task_id, title, description=None, status='todo', assignee=None, airtable_record_id=None, position=0):
        self.id = task_id
        self.title = title
        self.description = description
        self.status = status
        self.assignee = assignee
        self.airtable_record_id = airtable_record_id
        self.position = position
        self.saved = []

    def save(self, update_fields=None):
        self.saved.append(list(update_fields or []))


class FakeUser:
    def __init__(self, email):
        self.email = email


class TestAirtableExport:
    def test_fields_match_airtable_schema(self):
        task = FakeTask(
            't1',
            'Ship it',
            description='do the thing',
            status='in_progress',
            assignee=FakeUser('meera@taskboard.dev'),
            position=3,
        )
        assert fields_for_task(task) == {
            'External ID': 't1',
            'Title': 'Ship it',
            'Description': 'do the thing',
            'Status': 'In Progress',
            'Assignee': 'meera@taskboard.dev',
            'Position': 3,
        }

    def test_create_then_update_is_idempotent(self):
        client = MockAirtableClient()
        task = FakeTask('t1', 'Ship it', description='do the thing', status='todo')

        first = export_tasks([task], client, sleep=lambda _delay: None)
        assert first == {'exported': 1, 'created': 1, 'updated': 0, 'failed': []}
        assert task.airtable_record_id is not None
        assert client.create_calls == [fields_for_task(task)]
        record_id = task.airtable_record_id

        task.title = 'Ship it now'
        second = export_tasks([task], client, sleep=lambda _delay: None)
        assert second == {'exported': 1, 'created': 0, 'updated': 1, 'failed': []}
        assert task.airtable_record_id == record_id
        assert len(client.update_calls) == 1
        assert client.update_calls[0][0] == record_id
        assert client.records[record_id]['Title'] == 'Ship it now'
        assert len(client.create_calls) == 1

    def test_retries_transient_failures_with_exponential_backoff(self):
        client = MockAirtableClient()
        client.queue_create(
            TransientAirtableError('429'),
            TransientAirtableError('503'),
            'ok',
        )
        delays = []
        task = FakeTask('t1', 'Retry me')

        result = export_tasks([task], client, sleep=delays.append)
        assert result['created'] == 1
        assert result['failed'] == []
        assert delays == [0.1, 0.2]
        assert task.airtable_record_id is not None

    def test_exhausted_transient_failures_are_isolated(self):
        client = MockAirtableClient()
        client.queue_create(
            TransientAirtableError('timeout'),
            TransientAirtableError('timeout'),
            TransientAirtableError('timeout'),
        )
        ok = FakeTask('t2', 'Fine')
        bad = FakeTask('t1', 'Flaky')

        # export_tasks iterates in list order: fail first, succeed second
        result = export_tasks([bad, ok], client, sleep=lambda _delay: None)
        assert result['exported'] == 1
        assert result['created'] == 1
        assert result['failed'] == [{
            'task_id': 't1',
            'title': 'Flaky',
            'error': 'timeout',
        }]
        assert bad.airtable_record_id is None
        assert ok.airtable_record_id is not None

    def test_permanent_failure_skips_task_and_continues(self):
        client = MockAirtableClient()
        client.queue_create(PermanentAirtableError('422 Unprocessable'), 'ok')
        bad = FakeTask('t1', 'Bad fields')
        ok = FakeTask('t2', 'Good fields', assignee=FakeUser('meera@taskboard.dev'))

        result = export_tasks([bad, ok], client, sleep=lambda _delay: None)
        assert result['exported'] == 1
        assert result['created'] == 1
        assert result['failed'][0]['task_id'] == 't1'
        assert '422' in result['failed'][0]['error']
        assert bad.airtable_record_id is None
        assert ok.airtable_record_id is not None
        assert client.records[ok.airtable_record_id]['Assignee'] == 'meera@taskboard.dev'

    def test_permanent_errors_are_not_retried(self):
        calls = {'n': 0}

        def fail():
            calls['n'] += 1
            raise PermanentAirtableError('nope')

        with pytest.raises(PermanentAirtableError):
            call_with_retry(fail, sleep=lambda _delay: None)
        assert calls['n'] == 1


@pytest.mark.django_db
class TestExportEndpoint:
    def test_export_uses_mock_client_and_stores_record_id(self, auth_client, user, monkeypatch):
        project = Project.objects.create(name='P', owner=user)
        Membership.objects.create(user=user, project=project, role='admin')
        task = Task.objects.create(project=project, title='Do a thing', created_by=user)
        client = MockAirtableClient()
        monkeypatch.setattr('projects.views.get_airtable_client', lambda: client)

        first = auth_client.post(f'/api/projects/{project.id}/export')
        assert first.status_code == 200
        assert first.data['created'] == 1
        assert first.data['updated'] == 0
        task.refresh_from_db()
        assert task.airtable_record_id
        stored = task.airtable_record_id

        second = auth_client.post(f'/api/projects/{project.id}/export')
        assert second.data['created'] == 0
        assert second.data['updated'] == 1
        task.refresh_from_db()
        assert task.airtable_record_id == stored

    def test_viewers_cannot_export(self, client, user, monkeypatch):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        project = Project.objects.create(name='P', owner=owner)
        Membership.objects.create(user=owner, project=project, role='admin')
        Membership.objects.create(user=user, project=project, role='viewer')
        monkeypatch.setattr('projects.views.get_airtable_client', lambda: MockAirtableClient())

        resp = client.post('/api/auth/login', {'email': 'meera@taskboard.dev', 'password': 'password123'}, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")
        response = client.post(f'/api/projects/{project.id}/export')
        assert response.status_code == 403
