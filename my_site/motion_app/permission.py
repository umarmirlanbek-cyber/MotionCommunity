from rest_framework.permissions import BasePermission
from .choices import RoleChoices, MemberRoleChoices
from .models import TeamMember, ProjectMember


def is_admin(user):
    return user.role == RoleChoices.ADMIN


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


class IsAuthor(BasePermission):
    message = 'Это может только автор'

    def has_object_permission(self, request, view, obj):
        return obj.author_id == request.user.id


class IsAuthorOrProjectTeamLead(BasePermission):
    message = 'Это может только автор, тимлид проекта или Admin'

    def has_object_permission(self, request, view, obj):
        return obj.author_id == request.user.id or IsAdminOrProjectTeamLead().has_permission(request, view)


class CanEditTask(BasePermission):
    message = 'Менять можно только свои задачи'

    def has_object_permission(self, request, view, obj):
        if request.user.id in (obj.assignee_id, obj.author_id):
            return True
        return IsAdminOrProjectTeamLead().has_permission(request, view)
