from django.urls import path, include
from rest_framework import routers
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    CommunityStatsView,
    CustomLoginView, LogoutView,
    UserProfileViewSet, VerifyTokenView,
    MemberProfileListAPIView, MemberProfileDetailAPIView,
    TeamViewSet, TeamMemberViewSet,
    ProjectViewSet, ProjectMemberViewSet,
    ClientRequestListCreateAPIView, ClientRequestDetailAPIView, UserProfileNameAPIView,
    WorkExperienceAPIView, EducationAPIView, LanguagesAPIView, CertificateAPIView,
)
router = routers.SimpleRouter()
router.register(r'admin/members', UserProfileViewSet, basename='admin-members')
router.register(r'teams', TeamViewSet, basename='teams')
router.register(r'projects', ProjectViewSet, basename='projects')
router.register(r'personal-account/work', WorkExperienceAPIView, basename='work')
router.register(r'personal-account/education', EducationAPIView, basename='education')
router.register(r'personal-account/languages', LanguagesAPIView, basename='languages')
router.register(r'personal-account/certificates', CertificateAPIView, basename='certificates')

urlpatterns = [
    path('', include(router.urls)),

    path('stats/', CommunityStatsView.as_view()),

    path('auth/login/', CustomLoginView.as_view()),
    path('auth/login/refresh/', TokenRefreshView.as_view()),
    path('auth/logout/', LogoutView.as_view()),
    path('auth/verify/', VerifyTokenView.as_view()),

    path('members/', MemberProfileListAPIView.as_view()),
    path('members/<int:pk>/', MemberProfileDetailAPIView.as_view()),

    path('teams/<int:teamId>/members/', TeamMemberViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('teams/<int:teamId>/members/<int:userId>/', TeamMemberViewSet.as_view({'delete': 'destroy'})),

    path('projects/<int:projectId>/members/', ProjectMemberViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('projects/<int:projectId>/members/<int:userId>/', ProjectMemberViewSet.as_view({'delete': 'destroy'})),

    path('client-requests/', ClientRequestListCreateAPIView.as_view()),
    path('client-requests/<int:pk>/', ClientRequestDetailAPIView.as_view()),

    path('personal-account/', UserProfileNameAPIView.as_view())
]