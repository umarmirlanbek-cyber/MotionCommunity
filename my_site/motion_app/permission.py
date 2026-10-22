from rest_framework.permissions import BasePermission
from .choices import RoleChoices, MemberRoleChoices
from .models import TeamMember, ProjectMember


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == RoleChoices.ADMIN
        )


class IsAdminOrTeamLead(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == RoleChoices.ADMIN:
            return True

        team_id = view.kwargs.get('team_id')
        return TeamMember.objects.filter(
            team_id=team_id, user=user, role=MemberRoleChoices.TEAM_LEAD
        ).exists()


class IsAdminOrProjectTeamLead(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == RoleChoices.ADMIN:
            return True

        project_id = view.kwargs.get('project_id') or view.kwargs.get('pk')
        return ProjectMember.objects.filter(
            project_id=project_id, user=user, role=MemberRoleChoices.TEAM_LEAD
        ).exists()


class IsAdminOrProjectMember(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == RoleChoices.ADMIN:
            return True

        return ProjectMember.objects.filter(project_id=view.kwargs.get('project_id'), user=user).exists()
