from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from .choices import RoleChoices, StatusChoices, ClientStatusChoices
from .models import (
    MAX_LABELS, MAX_LABEL_LENGTH, ASSIGNEE_NOT_MEMBER, can_be_assignee,
    UserProfile, WorkExperience, Education, Language, Certificate, validate_label,
    Team, TeamMember, Project, ProjectMember, Task, TaskComment, TaskAttachment, TaskHistory, Notification,
    ClientRequest,
)
from .services import check_not_last_admin, task_file_url


# ---------- Вход и выход ----------

class LoginSerializer(TokenObtainPairSerializer):
    default_error_messages = {'no_active_account': 'Неверный логин или пароль'}

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'role': self.user.role,
            'status': self.user.status,
        }
        return data


class RefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except UserProfile.DoesNotExist:
            raise InvalidToken('Пользователь удалён')


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('Неверный текущий пароль')
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context['request'].user)
        return value


# ---------- Резюме ----------

def check_end_after_start(serializer, attrs, start_field, end_field, message):
    start = attrs.get(start_field, getattr(serializer.instance, start_field, None))
    end = attrs.get(end_field, getattr(serializer.instance, end_field, None))
    if start and end and end < start:
        raise serializers.ValidationError({end_field: message})
    return attrs


class WorkExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkExperience
        fields = (
            'id', 'company', 'position', 'start_date', 'end_date',
            'working_format', 'achievements'
        )

    def validate(self, attrs):
        return check_end_after_start(self, attrs, 'start_date', 'end_date', 'Дата окончания раньше даты начала')


class EducationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Education
        fields = (
            'id', 'institution', 'specialization', 'start_year',
            'end_year', 'studying_now', 'description'
        )

    def validate(self, attrs):
        return check_end_after_start(self, attrs, 'start_year', 'end_year', 'Год окончания раньше года начала')


class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = ('id', 'name', 'level')


class CertificateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Certificate
        fields = (
            'id', 'title', 'organization', 'issue_date', 'description', 'image'
        )


# ---------- Участники (публично) ----------

class MemberShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ('id', 'first_name', 'last_name', 'position', 'avatar')


class MemberTeamSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='team.id')
    name = serializers.CharField(source='team.name')
    image = serializers.ImageField(source='team.image')

    class Meta:
        model = TeamMember
        fields = ('id', 'name', 'image', 'role')


class MemberProjectSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='project.id')
    name = serializers.CharField(source='project.name')
    status = serializers.CharField(source='project.status')
    image = serializers.ImageField(source='project.image')

    class Meta:
        model = ProjectMember
        fields = ('id', 'name', 'status', 'image', 'role')


class MemberDetailSerializer(serializers.ModelSerializer):
    work = WorkExperienceSerializer(many=True, read_only=True)
    education = EducationSerializer(many=True, read_only=True)
    languages = LanguageSerializer(many=True, read_only=True)
    certificates = CertificateSerializer(many=True, read_only=True)
    teams = MemberTeamSerializer(source='team_memberships', many=True, read_only=True)
    projects = MemberProjectSerializer(source='project_memberships', many=True, read_only=True)

    class Meta:
        model = UserProfile
        fields = (
            'id', 'first_name', 'last_name', 'avatar', 'bio', 'position',
            'skills', 'github', 'linkedin', 'portfolio', 'resume',
            'work', 'education', 'languages', 'certificates', 'teams', 'projects',
        )


# ---------- Личный кабинет ----------

class MeSerializer(MemberDetailSerializer):
    class Meta:
        model = UserProfile
        fields = MemberDetailSerializer.Meta.fields + ('username', 'email', 'role', 'status', 'created_at')
        read_only_fields = ('username', 'role', 'status')

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if instance.status == StatusChoices.INACTIVE and (instance.first_name or instance.bio or instance.skills):
            instance.status = StatusChoices.ACTIVE
        instance.save(update_fields=[*validated_data, 'status'])
        return instance


# ---------- Пользователи (только админ) ----------

class UserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ('id', 'username', 'first_name', 'last_name', 'role', 'status', 'is_active')


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = UserProfile
        fields = ('id', 'username', 'password', 'role')

    def create(self, validated_data):
        return UserProfile.objects.create_user(**validated_data)


class UserDetailSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, validators=[validate_password])

    class Meta:
        model = UserProfile
        fields = (
            'id', 'username', 'password', 'email', 'first_name', 'last_name',
            'role', 'status', 'is_active', 'created_at',
        )
        read_only_fields = ('status',)

    def validate(self, attrs):
        demoted = attrs.get('role', self.instance.role) != RoleChoices.ADMIN
        if demoted or not attrs.get('is_active', self.instance.is_active):
            check_not_last_admin(self.instance)
        return attrs

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)
        return super().update(instance, validated_data)


# ---------- Команды ----------

class GroupMemberSerializer(serializers.ModelSerializer):
    user = MemberShortSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        source='user', queryset=UserProfile.objects.filter(is_active=True), write_only=True
    )

    class Meta:
        fields = ('user', 'user_id', 'role')


class TeamMemberSerializer(GroupMemberSerializer):
    class Meta(GroupMemberSerializer.Meta):
        model = TeamMember


class TeamMemberUpdateSerializer(TeamMemberSerializer):
    class Meta(TeamMemberSerializer.Meta):
        fields = ('user', 'role')


class TeamShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ('id', 'name', 'image')


class TeamListSerializer(serializers.ModelSerializer):
    members_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Team
        fields = ('id', 'name', 'image', 'members_count')


class TeamProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ('id', 'name', 'status', 'image')


class TeamDetailSerializer(serializers.ModelSerializer):
    members = TeamMemberSerializer(many=True, read_only=True)
    projects = TeamProjectSerializer(many=True, read_only=True)

    class Meta:
        model = Team
        fields = ('id', 'name', 'description', 'image', 'created_at', 'members', 'projects')


# ---------- Проекты ----------

class ProjectMemberSerializer(GroupMemberSerializer):
    class Meta(GroupMemberSerializer.Meta):
        model = ProjectMember


class ProjectMemberUpdateSerializer(ProjectMemberSerializer):
    class Meta(ProjectMemberSerializer.Meta):
        fields = ('user', 'role')


class ProjectShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ('id', 'name')


class ProjectListSerializer(serializers.ModelSerializer):
    team = TeamShortSerializer(read_only=True)

    class Meta:
        model = Project
        fields = ('id', 'name', 'status', 'category', 'image', 'team')


class ProjectDetailSerializer(serializers.ModelSerializer):
    team = TeamShortSerializer(read_only=True)
    team_id = serializers.PrimaryKeyRelatedField(
        source='team', queryset=Team.objects.all(), write_only=True, required=False, allow_null=True
    )
    members = ProjectMemberSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = (
            'id', 'name', 'description', 'status', 'category', 'image',
            'demo_url', 'github_url', 'created_at', 'team', 'team_id', 'members',
        )


# ---------- Задачи ----------

class TaskCommentSerializer(serializers.ModelSerializer):
    author = MemberShortSerializer(read_only=True)

    class Meta:
        model = TaskComment
        fields = ('id', 'author', 'text', 'created_at')


class TaskAttachmentSerializer(serializers.ModelSerializer):
    author = MemberShortSerializer(read_only=True)
    name = serializers.CharField(read_only=True)

    class Meta:
        model = TaskAttachment
        fields = ('id', 'author', 'file', 'name', 'created_at')

    def to_representation(self, attachment):
        data = super().to_representation(attachment)
        data['file'] = self.context['request'].build_absolute_uri(task_file_url(attachment))
        return data


class TaskHistorySerializer(serializers.ModelSerializer):
    user = MemberShortSerializer(read_only=True)

    class Meta:
        model = TaskHistory
        fields = ('id', 'user', 'field', 'old_value', 'new_value', 'created_at')


class TaskListSerializer(serializers.ModelSerializer):
    assignee = MemberShortSerializer(read_only=True)

    class Meta:
        model = Task
        fields = ('id', 'title', 'status', 'priority', 'type', 'labels', 'assignee', 'due_date', 'order')


class TaskDetailSerializer(serializers.ModelSerializer):
    assignee = MemberShortSerializer(read_only=True)
    assignee_id = serializers.PrimaryKeyRelatedField(
        source='assignee', queryset=UserProfile.objects.all(), write_only=True, required=False, allow_null=True
    )
    labels = serializers.ListField(
        child=serializers.CharField(max_length=MAX_LABEL_LENGTH, validators=[validate_label]),
        max_length=MAX_LABELS, required=False,
    )
    author = MemberShortSerializer(read_only=True)
    comments = TaskCommentSerializer(many=True, read_only=True)
    attachments = TaskAttachmentSerializer(many=True, read_only=True)
    history = TaskHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Task
        fields = (
            'id', 'title', 'description', 'status', 'priority', 'type', 'labels', 'assignee', 'assignee_id', 'author',
            'due_date', 'order', 'created_at', 'updated_at', 'comments', 'attachments', 'history',
        )

    def validate_assignee_id(self, user):
        project_id = self.context['view'].kwargs['project_id']
        current = self.instance.assignee_id if self.instance else None
        if user and not can_be_assignee(project_id, user.pk, current, lock=True):
            raise serializers.ValidationError(ASSIGNEE_NOT_MEMBER)
        return user

    def validate_labels(self, labels):
        return list(dict.fromkeys(labels))


class MyTaskSerializer(TaskListSerializer):
    project = ProjectShortSerializer(read_only=True)

    class Meta(TaskListSerializer.Meta):
        fields = TaskListSerializer.Meta.fields + ('project',)


# ---------- Уведомления ----------

class NotificationTaskSerializer(serializers.ModelSerializer):
    project = ProjectShortSerializer(read_only=True)

    class Meta:
        model = Task
        fields = ('id', 'title', 'project')


class NotificationCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskComment
        fields = ('id', 'text')


class NotificationSerializer(serializers.ModelSerializer):
    actor = MemberShortSerializer(read_only=True)
    task = NotificationTaskSerializer(read_only=True)
    comment = NotificationCommentSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = ('id', 'type', 'actor', 'task', 'comment', 'is_read', 'created_at')
        read_only_fields = ('type',)


# ---------- Заявки клиентов ----------

class ClientRequestListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientRequest
        fields = ('id', 'name', 'company', 'title', 'status', 'created_at')


class ClientRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientRequest
        fields = (
            'id', 'name', 'company', 'email', 'phone', 'title',
            'description', 'project_type', 'budget', 'created_at',
        )


class ClientRequestDetailSerializer(serializers.ModelSerializer):
    project = ProjectShortSerializer(read_only=True)

    class Meta:
        model = ClientRequest
        fields = (
            'id', 'name', 'company', 'email', 'phone', 'title', 'description',
            'project_type', 'budget', 'status', 'project', 'created_at',
        )

    def validate_status(self, value):
        if value == ClientStatusChoices.REJECTED and self.instance and self.instance.project_id:
            raise serializers.ValidationError('По этой заявке уже создан проект')
        return value
