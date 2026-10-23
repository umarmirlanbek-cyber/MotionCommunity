from copy import copy

from django.core.signing import BadSignature, SignatureExpired
from django.db import DatabaseError, connection, transaction
from django.db.models import CharField, Count, F, Func
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, generics, mixins, status
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .choices import (
    RoleChoices, StatusChoices, PositionChoices, MemberRoleChoices, ProjectStatusChoices, TaskStatusChoices,
    TaskPriorityChoices, TaskTypeChoices, NotificationTypeChoices, ClientStatusChoices, WorkingFormatChoices,
    LanguageLevelChoices,
)
from .models import (
    UserProfile, WorkExperience, Education, Language, Certificate,
    Team, TeamMember, Project, ProjectMember, Task, TaskComment, TaskAttachment, Notification, ClientRequest
)
from .filters import TaskFilter
from .permission import (
    is_admin, IsAdmin, IsAdminOrTeamLead, IsAdminOrProjectTeamLead, IsAdminOrProjectMember,
    IsAuthor, IsAuthorOrProjectTeamLead, CanEditTask,
)
from .services import task_created, task_changed, comment_created, task_file_id
from .serializers import (
    LoginSerializer, LogoutSerializer, ChangePasswordSerializer,
    MemberShortSerializer, MemberDetailSerializer, MeSerializer,
    UserListSerializer, UserCreateSerializer, UserDetailSerializer,
    WorkExperienceSerializer, EducationSerializer, LanguageSerializer, CertificateSerializer,
    TeamListSerializer, TeamDetailSerializer, TeamMemberSerializer, TeamMemberUpdateSerializer,
    ProjectListSerializer, ProjectDetailSerializer, ProjectMemberSerializer, ProjectMemberUpdateSerializer,
    TaskListSerializer, TaskDetailSerializer, TaskCommentSerializer, TaskAttachmentSerializer, MyTaskSerializer,
    NotificationSerializer,
    ClientRequestListSerializer, ClientRequestCreateSerializer, ClientRequestDetailSerializer,
)


# ---------- Вход и выход ----------

class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except AuthenticationFailed:
            return Response({'detail': 'Неверный логин или пароль'}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LogoutView(generics.GenericAPIView):
    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data['refresh']).blacklist()
        except TokenError:
            return Response({'detail': 'Неверный refresh token'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class VerifyTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user

        return Response({
            'id': user.id,
            'username': user.username,
            'role': user.role,
        })


# ---------- Личный кабинет ----------

class MeView(generics.RetrieveUpdateDestroyAPIView):
    queryset = UserProfile.objects.all()
    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'delete']

    def get_object(self):
        return self.request.user


class ChangePasswordView(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()
        return Response({'detail': 'Пароль изменён'})


class MyResumeViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    model = None
    permission_classes = [IsAuthenticated]
    http_method_names = ['post', 'patch', 'delete']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.model.objects.none()
        return self.model.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class WorkExperienceViewSet(MyResumeViewSet):
    model = WorkExperience
    serializer_class = WorkExperienceSerializer


class EducationViewSet(MyResumeViewSet):
    model = Education
    serializer_class = EducationSerializer


class LanguageViewSet(MyResumeViewSet):
    model = Language
    serializer_class = LanguageSerializer


class CertificateViewSet(MyResumeViewSet):
    model = Certificate
    serializer_class = CertificateSerializer


# ---------- Участники (публично) ----------

class MemberListAPIView(generics.ListAPIView):
    queryset = UserProfile.objects.filter(role=RoleChoices.MEMBER, status=StatusChoices.ACTIVE, is_active=True)
    serializer_class = MemberShortSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['position']
    search_fields = ['first_name', 'last_name', 'skills']


class MemberDetailAPIView(generics.RetrieveAPIView):
    queryset = UserProfile.objects.filter(
        role=RoleChoices.MEMBER, status=StatusChoices.ACTIVE, is_active=True
    ).prefetch_related(
        'work', 'education', 'languages', 'certificates',
        'team_memberships__team', 'project_memberships__project',
    )
    serializer_class = MemberDetailSerializer
    permission_classes = [AllowAny]


# ---------- Пользователи (только админ) ----------

class UserViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    permission_classes = [IsAdmin]
    http_method_names = ['get', 'post', 'patch', 'delete']
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['role', 'status', 'is_active']
    search_fields = ['username', 'first_name', 'last_name']

    def get_serializer_class(self):
        if self.action == 'list':
            return UserListSerializer
        if self.action == 'create':
            return UserCreateSerializer
        return UserDetailSerializer


# ---------- Команды ----------

class TeamViewSet(viewsets.ModelViewSet):
    http_method_names = ['get', 'post', 'patch', 'delete']
    filter_backends = [SearchFilter]
    search_fields = ['name']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
        return [IsAdmin()]

    def get_serializer_class(self):
        if self.action == 'list':
            return TeamListSerializer
        return TeamDetailSerializer

    def get_queryset(self):
        queryset = Team.objects.annotate(members_count=Count('members'))
        if self.action == 'list':
            return queryset
        return queryset.prefetch_related('members__user', 'projects')

    def perform_update(self, serializer):
        team = serializer.save()
        serializer.instance = self.get_queryset().get(pk=team.pk)


class GroupMemberViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    group_model = None
    group_kwarg = None
    group_name = None
    list_permission = None
    manage_permission = None
    update_serializer_class = None
    lookup_field = 'user_id'
    http_method_names = ['get', 'post', 'patch', 'delete']

    def get_permissions(self):
        if self.action == 'list':
            return [self.list_permission()]
        return [self.manage_permission()]

    def get_serializer_class(self):
        if self.action == 'partial_update':
            return self.update_serializer_class
        return self.serializer_class

    def get_queryset(self):
        return self.queryset.filter(**{self.group_kwarg: self.kwargs.get(self.group_kwarg)}).select_related('user')

    def perform_create(self, serializer):
        group = get_object_or_404(self.group_model, pk=self.kwargs[self.group_kwarg])
        if serializer.validated_data.get('role') == MemberRoleChoices.TEAM_LEAD and not is_admin(self.request.user):
            raise PermissionDenied('Назначать Team Lead может только Admin')
        serializer.save(**{self.group_kwarg: group.pk})

    def perform_update(self, serializer):
        if not is_admin(self.request.user):
            raise PermissionDenied(f'Менять роль в {self.group_name} может только Admin')
        serializer.save()

    def perform_destroy(self, instance):
        if instance.role == MemberRoleChoices.TEAM_LEAD and not is_admin(self.request.user):
            raise PermissionDenied('Убрать Team Lead может только Admin')
        instance.delete()


class TeamMemberViewSet(GroupMemberViewSet):
    queryset = TeamMember.objects.all()
    serializer_class = TeamMemberSerializer
    update_serializer_class = TeamMemberUpdateSerializer
    group_model = Team
    group_kwarg = 'team_id'
    group_name = 'команде'
    list_permission = IsAuthenticated
    manage_permission = IsAdminOrTeamLead


# ---------- Проекты ----------

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.select_related('team')
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'status', 'team']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'name']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'patch', 'delete']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        if self.action in ('create', 'destroy'):
            return [IsAdmin()]
        return [IsAdminOrProjectTeamLead()]

    def get_serializer_class(self):
        if self.action == 'list':
            return ProjectListSerializer
        return ProjectDetailSerializer

    def get_queryset(self):
        if self.action == 'list':
            return self.queryset
        return self.queryset.prefetch_related('members__user')

    def perform_update(self, serializer):
        project = serializer.save()
        serializer.instance = self.get_queryset().get(pk=project.pk)


class ProjectMemberViewSet(GroupMemberViewSet):
    queryset = ProjectMember.objects.all()
    serializer_class = ProjectMemberSerializer
    update_serializer_class = ProjectMemberUpdateSerializer
    group_model = Project
    group_kwarg = 'project_id'
    group_name = 'проекте'
    list_permission = AllowAny
    manage_permission = IsAdminOrProjectTeamLead


# ---------- Задачи ----------

class TaskViewSet(viewsets.ModelViewSet):
    http_method_names = ['get', 'post', 'patch', 'delete']
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = TaskFilter
    search_fields = ['title']

    def get_permissions(self):
        if self.action == 'destroy':
            return [IsAdminOrProjectTeamLead()]
        if self.action == 'partial_update':
            return [IsAdminOrProjectMember(), CanEditTask()]
        return [IsAdminOrProjectMember()]

    def get_serializer_class(self):
        if self.action == 'list':
            return TaskListSerializer
        return TaskDetailSerializer

    def get_queryset(self):
        queryset = Task.objects.filter(project_id=self.kwargs.get('project_id')).select_related('assignee')
        if self.action == 'retrieve':
            return self.with_details(queryset)
        return queryset

    @staticmethod
    def with_details(queryset):
        return queryset.select_related('author').prefetch_related(
            'comments__author', 'attachments__author', 'history__user'
        )

    def perform_create(self, serializer):
        project = get_object_or_404(Project, pk=self.kwargs['project_id'])
        task = serializer.save(project=project, author=self.request.user)
        task_created(task, self.request.user)

    def perform_update(self, serializer):
        old = copy(serializer.instance)
        task = serializer.save()
        task_changed(old, task, self.request.user)
        serializer.instance = self.with_details(self.get_queryset()).get(pk=task.pk)


class TaskLabelListAPIView(APIView):
    permission_classes = [IsAdminOrProjectMember]

    def get(self, request, *args, **kwargs):
        labels = Task.objects.filter(project_id=self.kwargs['project_id']).annotate(
            label=Func(F('labels'), function='unnest', output_field=CharField())
        ).values_list('label', flat=True).distinct().order_by('label')
        return Response(list(labels))


class TaskCommentViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = TaskCommentSerializer
    http_method_names = ['post', 'patch', 'delete']

    def get_permissions(self):
        if self.action == 'partial_update':
            return [IsAdminOrProjectMember(), IsAuthor()]
        if self.action == 'destroy':
            return [IsAdminOrProjectMember(), IsAuthorOrProjectTeamLead()]
        return [IsAdminOrProjectMember()]

    def get_queryset(self):
        return TaskComment.objects.filter(
            task_id=self.kwargs.get('task_id'), task__project_id=self.kwargs.get('project_id')
        ).select_related('author')

    def perform_create(self, serializer):
        task = get_object_or_404(Task, pk=self.kwargs['task_id'], project_id=self.kwargs['project_id'])
        comment = serializer.save(task=task, author=self.request.user)
        comment_created(comment)


class TaskAttachmentViewSet(
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = TaskAttachmentSerializer
    parser_classes = [MultiPartParser]
    http_method_names = ['post', 'delete']

    def get_permissions(self):
        if self.action == 'destroy':
            return [IsAdminOrProjectMember(), IsAuthorOrProjectTeamLead()]
        return [IsAdminOrProjectMember()]

    def get_queryset(self):
        return TaskAttachment.objects.filter(
            task_id=self.kwargs.get('task_id'), task__project_id=self.kwargs.get('project_id')
        ).select_related('author')

    def perform_create(self, serializer):
        task = get_object_or_404(Task, pk=self.kwargs['task_id'], project_id=self.kwargs['project_id'])
        serializer.save(task=task, author=self.request.user)


class TaskFileView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    swagger_schema = None

    def get(self, request, *args, **kwargs):
        try:
            attachment_id = task_file_id(kwargs['token'])
        except SignatureExpired:
            raise PermissionDenied('Ссылка устарела, откройте задачу заново')
        except (BadSignature, ValueError):
            raise NotFound()
        attachment = get_object_or_404(TaskAttachment, pk=attachment_id)
        return FileResponse(attachment.file.open('rb'), as_attachment=True, filename=attachment.name)


class MyTaskListAPIView(generics.ListAPIView):
    serializer_class = MyTaskSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'priority', 'type']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Task.objects.none()
        return Task.objects.filter(assignee=self.request.user).select_related('assignee', 'project')


# ---------- Уведомления ----------

class NotificationViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch']
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_read', 'type']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user).select_related('actor', 'task__project', 'comment')


class NotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        updated = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'updated': updated})


# ---------- Заявки клиентов ----------

class ClientRequestListCreateAPIView(generics.ListCreateAPIView):
    queryset = ClientRequest.objects.all()
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status']
    search_fields = ['name', 'company', 'title']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [AllowAny()]
        return [IsAdmin()]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ClientRequestCreateSerializer   # status клиентке ачылбайт
        return ClientRequestListSerializer

    def get_throttles(self):
        if self.request.method == 'POST':
            self.throttle_scope = 'client_requests'
        return super().get_throttles()


class ClientRequestDetailAPIView(generics.RetrieveUpdateAPIView):
    queryset = ClientRequest.objects.select_related('project')
    serializer_class = ClientRequestDetailSerializer
    permission_classes = [IsAdmin]
    http_method_names = ['get', 'patch']


class ClientRequestProjectView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            client_request = get_object_or_404(ClientRequest.objects.select_for_update(), pk=kwargs['pk'])
            if client_request.project_id:
                return Response({'detail': 'По этой заявке проект уже создан'}, status=status.HTTP_400_BAD_REQUEST)
            if client_request.status == ClientStatusChoices.REJECTED:
                return Response({'detail': 'Заявка отклонена'}, status=status.HTTP_400_BAD_REQUEST)
            project = Project.objects.create(
                name=client_request.title,
                description=client_request.description,
                category=client_request.project_type,
            )
            client_request.project = project
            client_request.status = ClientStatusChoices.ACCEPTED
            client_request.save()
        serializer = ProjectDetailSerializer(project, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ---------- Статистика и справочники ----------

class CommunityStatsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        return Response({
            'members_count': UserProfile.objects.filter(
                role=RoleChoices.MEMBER, status=StatusChoices.ACTIVE, is_active=True
            ).count(),
            'teams_count': Team.objects.count(),
            'projects_count': Project.objects.count(),
            'companies_count': ClientRequest.objects.filter(status=ClientStatusChoices.ACCEPTED)
                .values('company').distinct().count(),
        })


def choices_to_list(choices):
    return [{'value': value, 'label': label} for value, label in choices.choices]


class ChoicesView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        return Response({
            'roles': choices_to_list(RoleChoices),
            'statuses': choices_to_list(StatusChoices),
            'positions': choices_to_list(PositionChoices),
            'member_roles': choices_to_list(MemberRoleChoices),
            'project_statuses': choices_to_list(ProjectStatusChoices),
            'task_statuses': choices_to_list(TaskStatusChoices),
            'task_priorities': choices_to_list(TaskPriorityChoices),
            'task_types': choices_to_list(TaskTypeChoices),
            'notification_types': choices_to_list(NotificationTypeChoices),
            'client_request_statuses': choices_to_list(ClientStatusChoices),
            'working_formats': choices_to_list(WorkingFormatChoices),
            'language_levels': choices_to_list(LanguageLevelChoices),
        })


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
        except DatabaseError:
            return Response({'status': 'db_error'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'status': 'ok'})
