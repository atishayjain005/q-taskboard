from rest_framework import serializers
from users.serializers import UserSerializer
from .models import Project, Membership, Task, Comment, Activity


class TaskSerializer(serializers.ModelSerializer):
    assignee = UserSerializer(read_only=True)
    assignee_id = serializers.SerializerMethodField()
    project_id = serializers.SerializerMethodField()
    created_by_id = serializers.SerializerMethodField()

    def get_assignee_id(self, obj):
        return str(obj.assignee_id) if obj.assignee_id else None

    def get_project_id(self, obj):
        return str(obj.project_id)

    def get_created_by_id(self, obj):
        return str(obj.created_by_id)

    class Meta:
        model = Task
        fields = [
            'id', 'project_id', 'title', 'description', 'status',
            'assignee_id', 'created_by_id', 'position', 'created_at', 'updated_at', 'assignee',
        ]


class CommentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    author_id = serializers.SerializerMethodField()
    task_id = serializers.SerializerMethodField()

    def get_author_id(self, obj):
        return str(obj.author_id)

    def get_task_id(self, obj):
        return str(obj.task_id)

    class Meta:
        model = Comment
        fields = ['id', 'task_id', 'body', 'author_id', 'author', 'created_at']


class MembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ['id', 'role', 'user']


class ProjectDetailSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    owner_id = serializers.SerializerMethodField()
    memberships = MembershipSerializer(many=True, read_only=True)
    tasks = TaskSerializer(many=True, read_only=True)

    def get_owner_id(self, obj):
        return str(obj.owner_id)

    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'owner_id', 'owner', 'memberships', 'tasks', 'created_at', 'updated_at']


class ActivitySerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)
    actor_id = serializers.SerializerMethodField()
    project_id = serializers.SerializerMethodField()
    task_id = serializers.SerializerMethodField()
    comment_id = serializers.SerializerMethodField()

    def get_actor_id(self, obj):
        return str(obj.actor_id) if obj.actor_id else None

    def get_project_id(self, obj):
        return str(obj.project_id)

    def get_task_id(self, obj):
        return str(obj.task_id) if obj.task_id else None

    def get_comment_id(self, obj):
        return str(obj.comment_id) if obj.comment_id else None

    class Meta:
        model = Activity
        fields = [
            'id', 'project_id', 'event', 'actor', 'actor_id',
            'task_id', 'comment_id', 'metadata', 'created_at',
        ]
