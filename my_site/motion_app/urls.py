from django.urls import path, include
from rest_framework import routers
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    LoginView, LogoutView, VerifyTokenView,
    MeView, ChangePasswordView,
    WorkExperienceViewSet, EducationViewSet, LanguageViewSet, CertificateViewSet,
    MemberListAPIView, MemberDetailAPIView,
    UserViewSet,
    TeamViewSet, TeamMemberViewSet,
    ProjectViewSet, ProjectMemberViewSet,
    TaskViewSet, TaskLabelListAPIView, TaskCommentViewSet, TaskAttachmentViewSet, MyTaskListAPIView,
    NotificationViewSet, NotificationReadAllView,
    ClientRequestListCreateAPIView, ClientRequestDetailAPIView,
    CommunityStatsView, ChoicesView, HealthView,
)
router = routers.SimpleRouter()
router.register(r'me/work', WorkExperienceViewSet, basename='me-work')
router.register(r'me/education', EducationViewSet, basename='me-education')
router.register(r'me/languages', LanguageViewSet, basename='me-languages')
router.register(r'me/certificates', CertificateViewSet, basename='me-certificates')
router.register(r'me/notifications', NotificationViewSet, basename='me-notifications')
router.register(r'users', UserViewSet, basename='users')
router.register(r'teams', TeamViewSet, basename='teams')
router.register(r'projects', ProjectViewSet, basename='projects')

urlpatterns = [
    path('auth/login/', LoginView.as_view()),
    path('auth/refresh/', TokenRefreshView.as_view()),
    path('auth/logout/', LogoutView.as_view()),
    path('auth/verify/', VerifyTokenView.as_view()),

    path('me/', MeView.as_view()),
    path('me/password/', ChangePasswordView.as_view()),
    path('me/tasks/', MyTaskListAPIView.as_view()),
    path('me/notifications/read-all/', NotificationReadAllView.as_view()),

    path('members/', MemberListAPIView.as_view()),
    path('members/<int:pk>/', MemberDetailAPIView.as_view()),

    path('teams/<int:team_id>/members/', TeamMemberViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('teams/<int:team_id>/members/<int:user_id>/', TeamMemberViewSet.as_view({'patch': 'partial_update', 'delete': 'destroy'})),

    path('projects/<int:project_id>/members/', ProjectMemberViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('projects/<int:project_id>/members/<int:user_id>/', ProjectMemberViewSet.as_view({'patch': 'partial_update', 'delete': 'destroy'})),

    path('projects/<int:project_id>/tasks/', TaskViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('projects/<int:project_id>/tasks/labels/', TaskLabelListAPIView.as_view()),
    path('projects/<int:project_id>/tasks/<int:pk>/', TaskViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'})),
    path('projects/<int:project_id>/tasks/<int:task_id>/comments/', TaskCommentViewSet.as_view({'post': 'create'})),
    path('projects/<int:project_id>/tasks/<int:task_id>/comments/<int:pk>/', TaskCommentViewSet.as_view({'patch': 'partial_update', 'delete': 'destroy'})),
    path('projects/<int:project_id>/tasks/<int:task_id>/attachments/', TaskAttachmentViewSet.as_view({'post': 'create'})),
    path('projects/<int:project_id>/tasks/<int:task_id>/attachments/<int:pk>/', TaskAttachmentViewSet.as_view({'delete': 'destroy'})),

    path('client-requests/', ClientRequestListCreateAPIView.as_view()),
    path('client-requests/<int:pk>/', ClientRequestDetailAPIView.as_view()),

    path('stats/', CommunityStatsView.as_view()),
    path('choices/', ChoicesView.as_view()),
    path('health/', HealthView.as_view()),

    path('', include(router.urls)),
]
