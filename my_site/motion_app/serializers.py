from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db import IntegrityError
from .models import (
    UserProfile, Team, TeamMember, Project, ProjectMember, ClientRequest,
    RoleChoices, StatusChoices, WorkExperience, Education, Languages, Certificates
)


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'login': self.user.username,
            'role': self.user.role,
            'status': self.user.status,
        }
        return data


class UserProfileListSerializer(serializers.ModelSerializer):
    login = serializers.CharField(source='username')

    class Meta:
        model = UserProfile
        fields = ('id', 'login', 'role', 'status')


class UserProfileCreateSerializer(serializers.ModelSerializer):
    login = serializers.CharField(source='username')
    password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=RoleChoices.choices, required=False, default=RoleChoices.DEVELOPER)

    class Meta:
        model = UserProfile
        fields = ('id', 'login', 'password', 'role')

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = UserProfile.objects.create_user(status=StatusChoices.INACTIVE, **validated_data)
        user.set_password(password)
        user.save()
        return user


class UserProfileDetailSerializer(serializers.ModelSerializer):
    login = serializers.CharField(source='username', required=False)
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = UserProfile
        fields = (
            'id', 'login', 'password', 'role', 'status', 'created_at',
            'first_name', 'last_name', 'avatar', 'bio', 'position',
            'skills', 'github', 'linkedin', 'portfolio', 'resume',
        )
        read_only_fields = ('status',)

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        if instance.status == StatusChoices.INACTIVE and (
            validated_data.get('first_name') or validated_data.get('bio') or validated_data.get('skills')
        ):
            instance.status = StatusChoices.ACTIVE
        instance.save()
        return instance

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = UserProfile.objects.create_user(**validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance




class MemberProfileListSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ('id', 'first_name', 'last_name', 'position', 'avatar', 'status')


class MemberProfileDetailSerializer(serializers.ModelSerializer):
    projects = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = (
            'id', 'first_name', 'last_name', 'avatar', 'bio', 'position',
            'skills', 'github', 'linkedin', 'portfolio', 'resume', 'status', 'projects',
        )

    def get_projects(self, obj):
        projects = Project.objects.filter(members__user=obj).distinct()
        return ProjectListSerializer(projects, many=True).data




class TeamListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ('id', 'team_name', 'team_image')


class TeamMemberSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=UserProfile.objects.all())

    class Meta:
        model = TeamMember
        fields = ('id', 'user', 'role')
        read_only_fields = ('id',)

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except IntegrityError:
            raise serializers.ValidationError('Этот пользователь уже состоит в команде.')


class TeamDetailSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = ('id', 'team_name', 'description', 'team_image', 'created_at', 'members')

    def get_members(self, obj):
        return TeamMemberSerializer(obj.members.all(), many=True).data




class ProjectListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ('id', 'name', 'project_status', 'category', 'preview_image', 'team')


class ProjectMemberSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=UserProfile.objects.all())

    class Meta:
        model = ProjectMember
        fields = ('id', 'project', 'user', 'role')
        read_only_fields = ('project',)

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except IntegrityError:
            raise serializers.ValidationError('Этот пользователь уже состоит в проекте.')


class ProjectDetailSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            'id', 'name', 'description', 'project_status', 'category',
            'preview_image', 'demo_url', 'github_url', 'created_at', 'member', 'members',
        )

    def get_members(self, obj):
        return ProjectMemberSerializer(obj.members.all(), many=True).data




class ClientRequestListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientRequest
        fields = ('id', 'name', 'title', 'status', 'created_at')


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


class WorkExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkExperience
        fields = (
            'id', 'company', 'position', 'start_time', 'end_time',
            'working_format', 'achievements'
        )


class EducationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Education
        fields = (
            'id', 'educational_institution', 'specialization', 'start_year',
            'end_year', 'studying_now', 'responsibilities'
        )


class LanguagesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Languages
        fields = (
            'id', 'Level', 'languages'
        )


class CertificatesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Certificates
        fields = (
            'id', 'title', 'organization', 'given_date', 'text',
            'certificate_image'
        )

class UserProfileNameSerializer(serializers.ModelSerializer):
    login = serializers.CharField(source='username', required=False)
    password = serializers.CharField(write_only=True, required=False)
    work_user = WorkExperienceSerializer(many=True, read_only=True)
    education_user = EducationSerializer(many=True, read_only=True)
    language_user = LanguagesSerializer(many=True, read_only=True)
    certificate_user = CertificatesSerializer(many=True, read_only=True)

    class Meta:
        model = UserProfile
        fields = (
            'id', 'login', 'password', 'role', 'status', 'created_at',
            'first_name', 'last_name', 'avatar', 'bio', 'position',
            'skills', 'github', 'linkedin', 'portfolio', 'resume',
            'work_user', 'education_user', 'language_user', 'certificate_user'
        )
        read_only_fields = ('status',)

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()

        return instance


