from django.db.models import Count
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, generics, mixins, status
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .choices import (
    RoleChoices, StatusChoices, PositionChoices, MemberRoleChoices, ProjectStatusChoices,
    ClientStatusChoices, WorkingFormatChoices, LanguageLevelChoices
)
from .models import (
    UserProfile, WorkExperience, Education, Language, Certificate,
    Team, TeamMember, Project, ProjectMember, ClientRequest
)
from .permission import IsAdmin, IsAdminOrTeamLead, IsAdminOrProjectTeamLead
from .serializers import (
    LoginSerializer, LogoutSerializer, ChangePasswordSerializer,
    MemberShortSerializer, MemberDetailSerializer, MeSerializer,
    UserListSerializer, UserCreateSerializer, UserDetailSerializer,
    WorkExperienceSerializer, EducationSerializer, LanguageSerializer, CertificateSerializer,
    TeamListSerializer, TeamDetailSerializer, TeamMemberSerializer, TeamMemberUpdateSerializer,
    ProjectListSerializer, ProjectDetailSerializer, ProjectMemberSerializer, ProjectMemberUpdateSerializer,
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


class MyResumeViewSet(viewsets.ModelViewSet):
    model = None
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'delete']

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
    queryset = Team.objects.annotate(members_count=Count('members')).prefetch_related('members__user', 'projects')
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


class TeamMemberViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    lookup_field = 'user_id'
    http_method_names = ['get', 'post', 'patch', 'delete']

    def get_permissions(self):
        if self.action == 'list':
            return [IsAuthenticated()]
        return [IsAdminOrTeamLead()]

    def get_serializer_class(self):
        if self.action == 'partial_update':
            return TeamMemberUpdateSerializer
        return TeamMemberSerializer

    def get_queryset(self):
        return TeamMember.objects.filter(team_id=self.kwargs.get('team_id')).select_related('user')

    def perform_create(self, serializer):
        team = get_object_or_404(Team, pk=self.kwargs['team_id'])
        if serializer.validated_data.get('role') == MemberRoleChoices.TEAM_LEAD and self.request.user.role != RoleChoices.ADMIN:
            raise PermissionDenied('Назначать Team Lead может только Admin')
        serializer.save(team=team)

    def perform_update(self, serializer):
        if self.request.user.role != RoleChoices.ADMIN:
            raise PermissionDenied('Менять роль в команде может только Admin')
        serializer.save()

    def perform_destroy(self, instance):
        if instance.role == MemberRoleChoices.TEAM_LEAD and self.request.user.role != RoleChoices.ADMIN:
            raise PermissionDenied('Убрать Team Lead может только Admin')
        instance.delete()


# ---------- Проекты ----------

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.select_related('team').prefetch_related('members__user')
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


class ProjectMemberViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    lookup_field = 'user_id'
    http_method_names = ['get', 'post', 'patch', 'delete']

    def get_permissions(self):
        if self.action == 'list':
            return [AllowAny()]
        return [IsAdminOrProjectTeamLead()]

    def get_serializer_class(self):
        if self.action == 'partial_update':
            return ProjectMemberUpdateSerializer
        return ProjectMemberSerializer

    def get_queryset(self):
        return ProjectMember.objects.filter(project_id=self.kwargs.get('project_id')).select_related('user')

    def perform_create(self, serializer):
        project = get_object_or_404(Project, pk=self.kwargs['project_id'])
        if serializer.validated_data.get('role') == MemberRoleChoices.TEAM_LEAD and self.request.user.role != RoleChoices.ADMIN:
            raise PermissionDenied('Назначать Team Lead может только Admin')
        serializer.save(project=project)

    def perform_update(self, serializer):
        if self.request.user.role != RoleChoices.ADMIN:
            raise PermissionDenied('Менять роль в проекте может только Admin')
        serializer.save()

    def perform_destroy(self, instance):
        if instance.role == MemberRoleChoices.TEAM_LEAD and self.request.user.role != RoleChoices.ADMIN:
            raise PermissionDenied('Убрать Team Lead может только Admin')
        instance.delete()


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
    queryset = ClientRequest.objects.all()
    serializer_class = ClientRequestDetailSerializer
    permission_classes = [IsAdmin]
    http_method_names = ['get', 'patch']


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
            'client_request_statuses': choices_to_list(ClientStatusChoices),
            'working_formats': choices_to_list(WorkingFormatChoices),
            'language_levels': choices_to_list(LanguageLevelChoices),
        })
