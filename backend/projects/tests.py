import pytest
from rest_framework.test import APIClient
from users.models import User
from projects.models import Project, Membership, Task, Comment, Activity


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


@pytest.mark.django_db
class TestProjects:
    def test_create_project(self, auth_client, user):
        response = auth_client.post('/api/projects', {'name': 'My Project'}, format='json')
        assert response.status_code == 201
        assert response.data['project']['name'] == 'My Project'

    def test_list_only_returns_member_projects(self, auth_client, user):
        p1 = Project.objects.create(name='Mine', owner=user)
        Membership.objects.create(user=user, project=p1, role='admin')
        other = User.objects.create_user(email='other@example.com', name='Other', password='password123')
        p2 = Project.objects.create(name='Not Mine', owner=other)
        Membership.objects.create(user=other, project=p2, role='admin')

        response = auth_client.get('/api/projects')
        assert response.status_code == 200
        names = [p['name'] for p in response.data['projects']]
        assert 'Mine' in names
        assert 'Not Mine' not in names

    def test_get_project_detail(self, auth_client, user):
        project = Project.objects.create(name='My Project', owner=user)
        Membership.objects.create(user=user, project=project, role='admin')

        response = auth_client.get(f'/api/projects/{project.id}')
        assert response.status_code == 200
        assert response.data['project']['name'] == 'My Project'

    def test_non_member_cannot_view_project(self, client, user):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        project = Project.objects.create(name='Private', owner=owner)
        Membership.objects.create(user=owner, project=project, role='admin')

        resp = client.post('/api/auth/login', {'email': 'meera@taskboard.dev', 'password': 'password123'}, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")

        response = client.get(f'/api/projects/{project.id}')
        assert response.status_code == 403


@pytest.mark.django_db
class TestTasks:
    def test_create_task(self, auth_client, user):
        project = Project.objects.create(name='P', owner=user)
        Membership.objects.create(user=user, project=project, role='admin')

        response = auth_client.post(f'/api/projects/{project.id}/tasks', {'title': 'Do a thing'}, format='json')
        assert response.status_code == 201
        assert response.data['task']['title'] == 'Do a thing'

    def test_viewers_cannot_create_tasks(self, client, user):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        project = Project.objects.create(name='P', owner=owner)
        Membership.objects.create(user=owner, project=project, role='admin')
        Membership.objects.create(user=user, project=project, role='viewer')

        resp = client.post('/api/auth/login', {'email': 'meera@taskboard.dev', 'password': 'password123'}, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")

        response = client.post(f'/api/projects/{project.id}/tasks', {'title': 'A task'}, format='json')
        assert response.status_code == 403

    def test_delete_task_requires_membership(self, client, user):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        project = Project.objects.create(name='P', owner=owner)
        Membership.objects.create(user=owner, project=project, role='admin')
        task = Task.objects.create(project=project, title='A task', created_by=owner)

        resp = client.post('/api/auth/login', {'email': 'meera@taskboard.dev', 'password': 'password123'}, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")

        response = client.delete(f'/api/tasks/{task.id}')
        assert response.status_code == 403

    def test_patch_task_requires_membership(self, client, user):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        project = Project.objects.create(name='P', owner=owner)
        Membership.objects.create(user=owner, project=project, role='admin')
        task = Task.objects.create(project=project, title='A task', created_by=owner)

        resp = client.post('/api/auth/login', {'email': 'meera@taskboard.dev', 'password': 'password123'}, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")

        response = client.patch(f'/api/tasks/{task.id}', {'title': 'Hijacked'}, format='json')
        assert response.status_code == 403
        task.refresh_from_db()
        assert task.title == 'A task'

    def test_viewers_cannot_patch_tasks(self, client, user):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        project = Project.objects.create(name='P', owner=owner)
        Membership.objects.create(user=owner, project=project, role='admin')
        Membership.objects.create(user=user, project=project, role='viewer')
        task = Task.objects.create(project=project, title='A task', created_by=owner)

        resp = client.post('/api/auth/login', {'email': 'meera@taskboard.dev', 'password': 'password123'}, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")

        response = client.patch(f'/api/tasks/{task.id}', {'title': 'Viewer edit'}, format='json')
        assert response.status_code == 403
        task.refresh_from_db()
        assert task.title == 'A task'

    def test_member_can_patch_task(self, auth_client, user):
        project = Project.objects.create(name='P', owner=user)
        Membership.objects.create(user=user, project=project, role='member')
        task = Task.objects.create(project=project, title='A task', created_by=user)

        response = auth_client.patch(f'/api/tasks/{task.id}', {'title': 'Updated title'}, format='json')
        assert response.status_code == 200
        assert response.data['task']['title'] == 'Updated title'
        task.refresh_from_db()
        assert task.title == 'Updated title'

    def test_task_search_does_not_leak_other_project_tasks(self, auth_client, user):
        mine = Project.objects.create(name='Mine', owner=user)
        Membership.objects.create(user=user, project=mine, role='admin')
        Task.objects.create(project=mine, title='Visible task', created_by=user)

        other = User.objects.create_user(email='other@example.com', name='Other', password='password123')
        secret = Project.objects.create(name='Secret', owner=other)
        Membership.objects.create(user=other, project=secret, role='admin')
        Task.objects.create(project=secret, title='Secret other project task', created_by=other)

        response = auth_client.get(
            f'/api/projects/{mine.id}/tasks',
            {'q': "' OR 1=1 --"},
        )
        assert response.status_code == 200
        titles = [task['title'] for task in response.data['tasks']]
        assert titles == []
        assert 'Secret other project task' not in titles

        response = auth_client.get(
            f'/api/projects/{mine.id}/tasks',
            {'q': 'Visible'},
        )
        assert response.status_code == 200
        titles = [task['title'] for task in response.data['tasks']]
        assert titles == ['Visible task']
        assert 'Secret other project task' not in titles


@pytest.mark.django_db
class TestComments:
    def _project_with_task(self, owner, extra_user=None, extra_role='member'):
        project = Project.objects.create(name='P', owner=owner)
        Membership.objects.create(user=owner, project=project, role='admin')
        if extra_user:
            Membership.objects.create(user=extra_user, project=project, role=extra_role)
        task = Task.objects.create(project=project, title='A task', created_by=owner)
        return project, task

    def test_member_can_list_and_create_comments(self, auth_client, user):
        _project, task = self._project_with_task(user)
        Comment.objects.create(task=task, author=user, body='First note')

        listed = auth_client.get(f'/api/tasks/{task.id}/comments')
        assert listed.status_code == 200
        assert [c['body'] for c in listed.data['comments']] == ['First note']

        created = auth_client.post(
            f'/api/tasks/{task.id}/comments',
            {'body': '  Follow-up  '},
            format='json',
        )
        assert created.status_code == 201
        assert created.data['comment']['body'] == 'Follow-up'
        assert created.data['comment']['author_id'] == str(user.id)

        listed = auth_client.get(f'/api/tasks/{task.id}/comments')
        assert [c['body'] for c in listed.data['comments']] == ['First note', 'Follow-up']

    def test_viewer_can_list_but_not_create_comments(self, client, user):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        _project, task = self._project_with_task(owner, extra_user=user, extra_role='viewer')
        Comment.objects.create(task=task, author=owner, body='Owner note')

        resp = client.post('/api/auth/login', {'email': 'meera@taskboard.dev', 'password': 'password123'}, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")

        listed = client.get(f'/api/tasks/{task.id}/comments')
        assert listed.status_code == 200
        assert [c['body'] for c in listed.data['comments']] == ['Owner note']

        created = client.post(f'/api/tasks/{task.id}/comments', {'body': 'Viewer note'}, format='json')
        assert created.status_code == 403
        assert Comment.objects.filter(task=task).count() == 1

    def test_non_member_cannot_list_or_create_comments(self, client, user):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        _project, task = self._project_with_task(owner)
        Comment.objects.create(task=task, author=owner, body='Private note')

        resp = client.post('/api/auth/login', {'email': 'meera@taskboard.dev', 'password': 'password123'}, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")

        listed = client.get(f'/api/tasks/{task.id}/comments')
        assert listed.status_code == 403

        created = client.post(f'/api/tasks/{task.id}/comments', {'body': 'Intruder'}, format='json')
        assert created.status_code == 403
        assert Comment.objects.filter(body='Intruder').count() == 0

    def test_empty_body_is_rejected(self, auth_client, user):
        _project, task = self._project_with_task(user)
        response = auth_client.post(f'/api/tasks/{task.id}/comments', {'body': '   '}, format='json')
        assert response.status_code == 400
        assert Comment.objects.filter(task=task).count() == 0

    def test_comments_are_append_only(self, auth_client, user):
        _project, task = self._project_with_task(user)
        comment = Comment.objects.create(task=task, author=user, body='Original')

        patched = auth_client.patch(
            f'/api/tasks/{task.id}/comments',
            {'body': 'Edited'},
            format='json',
        )
        assert patched.status_code == 405

        deleted = auth_client.delete(f'/api/tasks/{task.id}/comments')
        assert deleted.status_code == 405

        comment.body = 'Edited'
        with pytest.raises(ValueError, match='append-only'):
            comment.save()
        comment.refresh_from_db()
        assert comment.body == 'Original'


@pytest.mark.django_db
class TestActivity:
    def test_creating_a_task_writes_activity(self, auth_client, user):
        project = Project.objects.create(name='P', owner=user)
        Membership.objects.create(user=user, project=project, role='admin')

        response = auth_client.post(f'/api/projects/{project.id}/tasks', {'title': 'Do a thing'}, format='json')
        assert response.status_code == 201

        events = list(Activity.objects.filter(project=project).values_list('event', 'metadata'))
        assert events == [('task_created', {'title': 'Do a thing', 'status': 'todo'})]

    def test_status_change_writes_activity_title_change_does_not(self, auth_client, user):
        project = Project.objects.create(name='P', owner=user)
        Membership.objects.create(user=user, project=project, role='admin')
        task = Task.objects.create(project=project, title='A task', created_by=user, status='todo')

        renamed = auth_client.patch(f'/api/tasks/{task.id}', {'title': 'Renamed'}, format='json')
        assert renamed.status_code == 200
        assert Activity.objects.filter(project=project).count() == 0

        moved = auth_client.patch(f'/api/tasks/{task.id}', {'status': 'done'}, format='json')
        assert moved.status_code == 200
        activity = Activity.objects.get(project=project)
        assert activity.event == 'task_status_changed'
        assert activity.metadata == {
            'title': 'Renamed',
            'from_status': 'todo',
            'to_status': 'done',
        }

    def test_comment_writes_activity(self, auth_client, user):
        project = Project.objects.create(name='P', owner=user)
        Membership.objects.create(user=user, project=project, role='admin')
        task = Task.objects.create(project=project, title='A task', created_by=user)

        response = auth_client.post(f'/api/tasks/{task.id}/comments', {'body': 'Hello'}, format='json')
        assert response.status_code == 201
        activity = Activity.objects.get(project=project)
        assert activity.event == 'comment_added'
        assert activity.metadata == {'task_title': 'A task'}
        assert str(activity.comment_id) == response.data['comment']['id']

    def test_members_can_list_activity_non_members_cannot(self, client, user):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        project = Project.objects.create(name='P', owner=owner)
        Membership.objects.create(user=owner, project=project, role='admin')
        Membership.objects.create(user=user, project=project, role='viewer')
        task = Task.objects.create(project=project, title='A task', created_by=owner)
        Activity.log(
            project_id=project.id,
            actor=owner,
            event=Activity.EVENT_TASK_CREATED,
            task=task,
            metadata={'title': 'A task', 'status': 'todo'},
        )

        resp = client.post('/api/auth/login', {'email': 'meera@taskboard.dev', 'password': 'password123'}, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")
        listed = client.get(f'/api/projects/{project.id}/activity')
        assert listed.status_code == 200
        assert listed.data['activities'][0]['event'] == 'task_created'

        outsider = User.objects.create_user(email='out@example.com', name='Out', password='password123')
        resp = client.post('/api/auth/login', {'email': outsider.email, 'password': 'password123'}, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")
        forbidden = client.get(f'/api/projects/{project.id}/activity')
        assert forbidden.status_code == 403

    def test_failed_activity_write_rolls_back_task_create(self, auth_client, user, monkeypatch):
        project = Project.objects.create(name='P', owner=user)
        Membership.objects.create(user=user, project=project, role='admin')

        def fail_log(**_kwargs):
            raise RuntimeError('audit write failed')

        monkeypatch.setattr('projects.views.Activity.log', fail_log)
        with pytest.raises(RuntimeError, match='audit write failed'):
            auth_client.post(f'/api/projects/{project.id}/tasks', {'title': 'Do a thing'}, format='json')

        assert Task.objects.filter(project=project).count() == 0
        assert Activity.objects.filter(project=project).count() == 0
