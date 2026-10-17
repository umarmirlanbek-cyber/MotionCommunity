from rest_framework import viewsets, generics, mixins, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import (
    UserProfile, Team, TeamMember, Project, ProjectMember, ClientRequest,
    MemberRoleChoices, RoleChoices, StatusChoices, WorkExperience, Education, Languages,
    Certificates
)
from .permission import (
    IsAdmin, IsOwnerProfileOrReadOnly,
    IsAdminOrProjectTeamLead, IsAdminOrOwnTeamLead, IsAdminOrOwnProjectTeamLead,
)
from .serializers import (
    UserProfileListSerializer, UserProfileCreateSerializer, UserProfileDetailSerializer,
    MemberProfileListSerializer, MemberProfileDetailSerializer,
    TeamListSerializer, TeamDetailSerializer, TeamMemberSerializer,
    ProjectListSerializer, ProjectDetailSerializer, ProjectMemberSerializer,
    ClientRequestListSerializer, ClientRequestDetailSerializer, ClientRequestCreateSerializer,
    LoginSerializer, UserProfileNameSerializer, WorkExperienceSerializer, EducationSerializer,
    LanguagesSerializer, CertificatesSerializer
)


class CommunityStatsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        return Response({
            'members_count': UserProfile.objects.exclude(role=RoleChoices.ADMIN)
                .filter(status=StatusChoices.ACTIVE).count(),
            'projects_count': Project.objects.count(),
            'companies_count': ClientRequest.objects.values('company').distinct().count(),
        })

class CustomLoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            return Response({"detail": "Неверные учетные данные"}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LogoutView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            token = RefreshToken(request.data["refresh"])
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            return Response({"detail": "Неверный refresh token"}, status=status.HTTP_400_BAD_REQUEST)


class VerifyTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        return Response({
            'id': user.id,
            'username': user.username,
            'role': user.role,
        })



class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    permission_classes = [IsAdmin]
    http_method_names = ['get', 'post', 'patch', 'delete']

    def get_serializer_class(self):
        if self.action == 'list':
            return UserProfileListSerializer
        if self.action == 'create':
            return UserProfileCreateSerializer
        return UserProfileDetailSerializer


class MemberProfileListAPIView(generics.ListAPIView):
    queryset = UserProfile.objects.exclude(role=RoleChoices.ADMIN)
    serializer_class = MemberProfileListSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["position"]
    search_fields = ["first_name", "last_name", "skills"]


class MemberProfileDetailAPIView(generics.RetrieveUpdateAPIView):
    queryset = UserProfile.objects.exclude(role=RoleChoices.ADMIN)
    serializer_class = MemberProfileDetailSerializer
    http_method_names = ['get', 'patch']
    permission_classes = [IsOwnerProfileOrReadOnly]


class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all()
    http_method_names = ['get', 'post', 'patch', 'delete']

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
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = TeamMemberSerializer
    permission_classes = [IsAdminOrOwnTeamLead]
    lookup_field = 'user_id'
    lookup_url_kwarg = 'userId'

    def get_queryset(self):
        return TeamMember.objects.filter(team_id=self.kwargs['teamId'])

    def perform_create(self, serializer):
        if serializer.validated_data.get('role') == MemberRoleChoices.TEAM_LEAD and self.request.user.role != RoleChoices.ADMIN:
            raise PermissionDenied('Назначать Team Lead может только Admin')
        serializer.save(team_id=self.kwargs['teamId'])


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["category", "project_status"]
    search_fields = ["name", "description"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        if self.action == 'create':
            return [IsAdmin()]
        return [IsAdminOrProjectTeamLead()]

    def get_serializer_class(self):
        if self.action == 'list':
            return ProjectListSerializer
        return ProjectDetailSerializer


class ProjectMemberViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ProjectMemberSerializer
    permission_classes = [IsAdminOrOwnProjectTeamLead]
    lookup_field = 'user_id'
    lookup_url_kwarg = 'userId'

    def get_queryset(self):
        return ProjectMember.objects.filter(project_id=self.kwargs['projectId'])

    def perform_create(self, serializer):
        role = serializer.validated_data.get('role')
        if role == MemberRoleChoices.TEAM_LEAD and self.request.user.role != RoleChoices.ADMIN:
            raise PermissionDenied('Назначать Team Lead может только Admin')
        serializer.save(project_id=self.kwargs['projectId'])


class ClientRequestListCreateAPIView(generics.ListCreateAPIView):
    queryset = ClientRequest.objects.all()

    def get_permissions(self):
        if self.request.method == 'POST':
            return [AllowAny()]
        return [IsAdmin()]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ClientRequestCreateSerializer   # status клиентке ачылбайт
        return ClientRequestListSerializer


class ClientRequestDetailAPIView(generics.RetrieveUpdateAPIView):
    queryset = ClientRequest.objects.all()
    serializer_class = ClientRequestDetailSerializer
    permission_classes = [IsAdmin]
    http_method_names = ['get', 'patch']


class UserProfileNameAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileNameSerializer
    permission_classes = [AllowAny]
    http_method_names = ['get', 'patch', 'delete']

    def get_object(self):
        return self.request.user



class WorkExperienceAPIView(viewsets.ModelViewSet):
    serializer_class = WorkExperienceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return WorkExperience.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class EducationAPIView(viewsets.ModelViewSet):
    serializer_class = EducationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Education.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class LanguagesAPIView(viewsets.ModelViewSet):
    serializer_class = LanguagesSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Languages.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class CertificateAPIView(viewsets.ModelViewSet):
    serializer_class = CertificatesSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Certificates.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)