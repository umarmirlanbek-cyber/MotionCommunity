from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import TeamMember, ProjectMember, MemberRoleChoices, RoleChoices


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == RoleChoices.ADMIN
        )


class IsOwnerProfileOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj == request.user


class IsAdminOrOwnTeamLead(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == RoleChoices.ADMIN:
            return True

        team_id = view.kwargs.get('teamId')
        return TeamMember.objects.filter(
            team_id=team_id, user=user, role=MemberRoleChoices.TEAM_LEAD
        ).exists()


class IsAdminOrProjectTeamLead(BasePermission):

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == RoleChoices.ADMIN:
            return True

        return ProjectMember.objects.filter(
            project=obj, user=user, role=MemberRoleChoices.TEAM_LEAD
        ).exists()


class IsAdminOrOwnProjectTeamLead(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == RoleChoices.ADMIN:
            return True

        project_id = view.kwargs.get('projectId')
        return ProjectMember.objects.filter(
            project_id=project_id, user=user, role=MemberRoleChoices.TEAM_LEAD
        ).exists()


class IsProjectMemberForChat(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == RoleChoices.ADMIN:
            return True

        project_id = view.kwargs.get('projectId')
        return ProjectMember.objects.filter(project_id=project_id, user=user).exists()


class IsAdminOrOwnProjectTeamLeadForChatMembers(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == RoleChoices.ADMIN:
            return True

        project_id = view.kwargs.get('projectId')
        return ProjectMember.objects.filter(
            project_id=project_id, user=user, role=MemberRoleChoices.TEAM_LEAD).exists()