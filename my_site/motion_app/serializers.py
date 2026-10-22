from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .choices import StatusChoices
from .models import (
    UserProfile, WorkExperience, Education, Language, Certificate,
    Team, TeamMember, Project, ProjectMember, Task, TaskComment, ClientRequest
)


# ---------- Вход и выход ----------

class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'role': self.user.role,
            'status': self.user.status,
        }
        return data


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

class WorkExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkExperience
        fields = (
            'id', 'company', 'position', 'start_date', 'end_date',
            'working_format', 'achievements'
        )

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if start and end and end < start:
            raise serializers.ValidationError({'end_date': 'Дата окончания раньше даты начала'})
        return attrs


class EducationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Education
        fields = (
            'id', 'institution', 'specialization', 'start_year',
            'end_year', 'studying_now', 'description'
        )

    def validate(self, attrs):
        start = attrs.get('start_year', getattr(self.instance, 'start_year', None))
        end = attrs.get('end_year', getattr(self.instance, 'end_year', None))
        if start and end and end < start:
            raise serializers.ValidationError({'end_year': 'Год окончания раньше года начала'})
        return attrs


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
        read_only_fields = ('username', 'role', 'status', 'created_at')

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if instance.status == StatusChoices.INACTIVE and (instance.first_name or instance.bio or instance.skills):
            instance.status = StatusChoices.ACTIVE
        instance.save()
        return instance


# ---------- Пользователи (только админ) ----------

class UserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ('id', 'username', 'first_name', 'last_name', 'role', 'status', 'is_active')


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = UserProfile
        fields = ('id', 'username', 'password', 'role')

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        return UserProfile.objects.create_user(**validated_data)


class UserDetailSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = UserProfile
        fields = (
            'id', 'username', 'password', 'email', 'first_name', 'last_name',
            'role', 'status', 'is_active', 'created_at',
        )
        read_only_fields = ('status', 'created_at')

    def validate_password(self, value):
        validate_password(value)
        return value

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


# ---------- Команды ----------

class TeamMemberSerializer(serializers.ModelSerializer):
    user = MemberShortSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(source='user', queryset=UserProfile.objects.all(), write_only=True)

    class Meta:
        model = TeamMember
        fields = ('user', 'user_id', 'role')

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except IntegrityError:
            raise serializers.ValidationError({'user_id': 'Этот пользователь уже состоит в команде.'})


class TeamMemberUpdateSerializer(serializers.ModelSerializer):
    user = MemberShortSerializer(read_only=True)

    class Meta:
        model = TeamMember
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

class ProjectMemberSerializer(serializers.ModelSerializer):
    user = MemberShortSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(source='user', queryset=UserProfile.objects.all(), write_only=True)

    class Meta:
        model = ProjectMember
        fields = ('user', 'user_id', 'role')

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except IntegrityError:
            raise serializers.ValidationError({'user_id': 'Этот пользователь уже состоит в проекте.'})


class ProjectMemberUpdateSerializer(serializers.ModelSerializer):
    user = MemberShortSerializer(read_only=True)

    class Meta:
        model = ProjectMember
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


class TaskListSerializer(serializers.ModelSerializer):
    assignee = MemberShortSerializer(read_only=True)

    class Meta:
        model = Task
        fields = ('id', 'title', 'status', 'priority', 'assignee', 'due_date', 'order')


class TaskDetailSerializer(serializers.ModelSerializer):
    assignee = MemberShortSerializer(read_only=True)
    assignee_id = serializers.PrimaryKeyRelatedField(
        source='assignee', queryset=UserProfile.objects.all(), write_only=True, required=False, allow_null=True
    )
    author = MemberShortSerializer(read_only=True)
    comments = TaskCommentSerializer(many=True, read_only=True)

    class Meta:
        model = Task
        fields = (
            'id', 'title', 'description', 'status', 'priority', 'assignee', 'assignee_id', 'author',
            'due_date', 'order', 'created_at', 'updated_at', 'comments',
        )

    def validate_assignee_id(self, user):
        project_id = self.context['view'].kwargs['project_id']
        if user and not ProjectMember.objects.filter(project_id=project_id, user=user).exists():
            raise serializers.ValidationError('Исполнитель должен состоять в проекте')
        return user


class MyTaskSerializer(TaskListSerializer):
    project = ProjectShortSerializer(read_only=True)

    class Meta(TaskListSerializer.Meta):
        fields = TaskListSerializer.Meta.fields + ('project',)


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
        read_only_fields = ('id', 'created_at')


class ClientRequestDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientRequest
        fields = (
            'id', 'name', 'company', 'email', 'phone', 'title', 'description',
            'project_type', 'budget', 'status', 'created_at',
        )
