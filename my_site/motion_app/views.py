import mimetypes
from copy import copy

from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired
from django.conf import settings
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import CharField, Count, F, Func, Prefetch
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import translation
from django.utils.http import content_disposition_header
from django.views.defaults import page_not_found
from urllib.parse import quote
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, generics, mixins, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .choices import (
    RoleChoices, StatusChoices, PositionChoices, MemberRoleChoices, ProjectStatusChoices, TaskStatusChoices,
    TaskPriorityChoices, TaskTypeChoices, NotificationTypeChoices, ClientStatusChoices, WorkingFormatChoices,
    LanguageLevelChoices,
)
from .models import (
    UserProfile, WorkExperience, Education, Language, Certificate,
    Team, TeamMember, Project, ProjectMember, Task, TaskComment, TaskAttachment, ClientRequest,
    revoke_tokens,
)
from .filters import TaskFilter, MyTaskFilter
from .permission import (
    is_admin, IsAdmin, IsAdminOrTeamLead, IsAdminOrProjectTeamLead, IsAdminOrProjectMember,
    IsAuthor, IsAuthorOrProjectTeamLead, CanEditTask,
)
from .services import (
    task_created, task_changed, comment_created, member_removed, task_file_id, visible_notifications,
    check_not_last_admin,
)
from .serializers import (
    LoginSerializer, RefreshSerializer, LogoutSerializer, ChangePasswordSerializer,
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
    throttle_scope = 'login'


class RefreshView(TokenRefreshView):
    serializer_class = RefreshSerializer


class LogoutView(generics.GenericAPIView):
    serializer_class = LogoutSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

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

PROFILE_PREFETCH = (
    'work', 'education', 'languages', 'certificates',
    Prefetch('team_memberships', queryset=TeamMember.objects.select_related('team')),
    Prefetch('project_memberships', queryset=ProjectMember.objects.select_related('project')),
)


class MeView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'delete']

    def get_object(self):
        if self.request.method == 'GET':
            return self.with_details()
        return self.request.user

    def with_details(self):
        return UserProfile.objects.prefetch_related(*PROFILE_PREFETCH).get(pk=self.request.user.pk)

    def perform_update(self, serializer):
        serializer.save()
        serializer.instance = self.with_details()

    def perform_destroy(self, instance):
        check_not_last_admin(instance)
        revoke_tokens(instance)
        instance.delete()


class ChangePasswordView(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save(update_fields=['password'])
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
    lookup_value_regex = r'\d+'

    def get_queryset(self):
        return self.model.objects.filter(user_id=self.request.user.id)

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
    queryset = UserProfile.objects.public()
    serializer_class = MemberShortSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['position']
    search_fields = ['first_name', 'last_name', 'skills']


class MemberDetailAPIView(generics.RetrieveAPIView):
    queryset = UserProfile.objects.public().prefetch_related(*PROFILE_PREFETCH)
    serializer_class = MemberDetailSerializer
    permission_classes = [AllowAny]


# ---------- Пользователи (только админ) ----------

class UserViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    permission_classes = [IsAdmin]
    http_method_names = ['get', 'post', 'patch', 'delete']
    lookup_value_regex = r'\d+'
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['role', 'status', 'is_active']
    search_fields = ['username', 'first_name', 'last_name']

    def get_serializer_class(self):
        if self.action == 'list':
            return UserListSerializer
        if self.action == 'create':
            return UserCreateSerializer
        return UserDetailSerializer

    def perform_destroy(self, instance):
        check_not_last_admin(instance)
        revoke_tokens(instance)
        instance.delete()


# ---------- Команды ----------

class TeamViewSet(viewsets.ModelViewSet):
    http_method_names = ['get', 'post', 'patch', 'delete']
    lookup_value_regex = r'\d+'
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
        if self.action == 'list':
            return Team.objects.annotate(members_count=Count('members'))
        if self.action == 'retrieve':
            return self.with_details(Team.objects.all())
        return Team.objects.all()

    @staticmethod
    def with_details(queryset):
        return queryset.prefetch_related(
            Prefetch('members', queryset=TeamMember.objects.select_related('user')), 'projects'
        )

    def perform_update(self, serializer):
        team = serializer.save()
        serializer.instance = self.with_details(Team.objects.all()).get(pk=team.pk)


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
        try:
            with transaction.atomic():
                serializer.save(**{self.group_kwarg: group.pk})
        except IntegrityError:
            raise ValidationError({'user_id': f'Этот пользователь уже состоит в {self.group_name}.'})

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
    lookup_value_regex = r'\d+'
    project_lookup_kwarg = 'pk'

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
        if self.action == 'retrieve':
            return self.with_details(self.queryset)
        return self.queryset

    @staticmethod
    def with_details(queryset):
        return queryset.prefetch_related(Prefetch('members', queryset=ProjectMember.objects.select_related('user')))

    def perform_update(self, serializer):
        team = serializer.validated_data.get('team', serializer.instance.team)
        if getattr(team, 'pk', None) != serializer.instance.team_id and not is_admin(self.request.user):
            raise PermissionDenied('Менять команду проекта может только Admin')
        project = serializer.save()
        serializer.instance = self.with_details(self.queryset).get(pk=project.pk)


class ProjectMemberViewSet(GroupMemberViewSet):
    queryset = ProjectMember.objects.all()
    serializer_class = ProjectMemberSerializer
    update_serializer_class = ProjectMemberUpdateSerializer
    group_model = Project
    group_kwarg = 'project_id'
    group_name = 'проекте'
    list_permission = AllowAny
    manage_permission = IsAdminOrProjectTeamLead

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        member_removed(instance, self.request.user)


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
        if self.action == 'partial_update':
            return queryset.select_for_update(of=('self',))
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
        serializer.instance = self.with_details(Task.objects.select_related('assignee')).get(pk=task.pk)


class TaskLabelListAPIView(APIView):
    permission_classes = [IsAdminOrProjectMember]

    def get(self, request, *args, **kwargs):
        labels = Task.objects.filter(project_id=self.kwargs['project_id']).annotate(
            label=Func(F('labels'), function='unnest', output_field=CharField())
        ).values_list('label', flat=True).distinct().order_by('label')
        return Response(list(labels))


class TaskChildViewSet(
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    model = None

    def get_permissions(self):
        if self.action == 'destroy':
            return [IsAdminOrProjectMember(), IsAuthorOrProjectTeamLead()]
        return [IsAdminOrProjectMember()]

    def get_queryset(self):
        return self.model.objects.filter(
            task_id=self.kwargs.get('task_id'), task__project_id=self.kwargs.get('project_id')
        ).select_related('author')

    def perform_create(self, serializer):
        task = get_object_or_404(
            Task.objects.select_related('assignee', 'author'),
            pk=self.kwargs['task_id'], project_id=self.kwargs['project_id'],
        )
        serializer.save(task=task, author=self.request.user)


class TaskCommentViewSet(mixins.UpdateModelMixin, TaskChildViewSet):
    model = TaskComment
    serializer_class = TaskCommentSerializer
    http_method_names = ['post', 'patch', 'delete']

    def get_permissions(self):
        if self.action == 'partial_update':
            return [IsAdminOrProjectMember(), IsAuthor()]
        return super().get_permissions()

    def perform_create(self, serializer):
        super().perform_create(serializer)
        comment_created(serializer.instance)


class TaskAttachmentViewSet(TaskChildViewSet):
    model = TaskAttachment
    serializer_class = TaskAttachmentSerializer
    parser_classes = [MultiPartParser]
    http_method_names = ['post', 'delete']


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
        if not attachment.file.storage.exists(attachment.file.name):
            raise NotFound()
        if settings.TASK_FILES_X_ACCEL:
            content_type = mimetypes.guess_type(attachment.file.name)[0] or 'application/octet-stream'
            response = HttpResponse(content_type=content_type)
            response['X-Accel-Redirect'] = f'/private/{quote(attachment.file.name)}'
            response['Content-Disposition'] = content_disposition_header(True, attachment.name)
            return response
        return FileResponse(attachment.file.open('rb'), as_attachment=True, filename=attachment.name)


class MyTaskListAPIView(generics.ListAPIView):
    serializer_class = MyTaskSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = MyTaskFilter

    def get_queryset(self):
        return Task.objects.filter(
            assignee_id=self.request.user.id, project__members__user_id=self.request.user.id
        ).select_related('assignee', 'project')


# ---------- Уведомления ----------

class NotificationViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch']
    lookup_value_regex = r'\d+'
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_read', 'type']

    def get_queryset(self):
        return visible_notifications(self.request.user.id).select_related('actor', 'task__project', 'comment')


class NotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        updated = visible_notifications(request.user.id).filter(is_read=False).update(is_read=True)
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

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        client_request = get_object_or_404(ClientRequest.objects.select_for_update(), pk=kwargs['pk'])
        if client_request.project_id:
            return Response({'detail': 'По этой заявке проект уже создан'}, status=status.HTTP_400_BAD_REQUEST)
        if client_request.status == ClientStatusChoices.REJECTED:
            return Response({'detail': 'Заявка отклонена'}, status=status.HTTP_400_BAD_REQUEST)
        with translation.override(settings.LANGUAGE_CODE):
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

STATS_CACHE_SECONDS = 60


def community_stats():
    return {
        'members_count': UserProfile.objects.public().count(),
        'teams_count': Team.objects.count(),
        'projects_count': Project.objects.count(),
        'companies_count': ClientRequest.objects.filter(status=ClientStatusChoices.ACCEPTED)
            .values('company').distinct().count(),
    }


class CommunityStatsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        return Response(cache.get_or_set('community_stats', community_stats, STATS_CACHE_SECONDS))


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


def api_not_found(request, exception):
    if request.path.startswith('/api/'):
        return JsonResponse({'detail': str(NotFound.default_detail)}, status=status.HTTP_404_NOT_FOUND)
    return page_not_found(request, exception)


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
        except DatabaseError:
            return Response({'status': 'db_error'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'status': 'ok'})
