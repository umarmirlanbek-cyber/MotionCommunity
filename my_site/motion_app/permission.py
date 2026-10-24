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
            is_admin(request.user)
        )


def project_role(request, view):
    if not hasattr(request, 'project_role'):
        request.project_role = ProjectMember.objects.filter(
            project_id=view.kwargs.get('project_id') or view.kwargs.get('pk'), user=request.user
        ).values_list('role', flat=True).first()
    return request.project_role


class IsAdminOr(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (is_admin(user) or self.allows(request, view)))

    def allows(self, request, view):
        return False


class IsAdminOrTeamLead(IsAdminOr):
    def allows(self, request, view):
        return TeamMember.objects.filter(
            team_id=view.kwargs.get('team_id'), user=request.user, role=MemberRoleChoices.TEAM_LEAD
        ).exists()


class IsAdminOrProjectTeamLead(IsAdminOr):
    def allows(self, request, view):
        return project_role(request, view) == MemberRoleChoices.TEAM_LEAD


class IsAdminOrProjectMember(IsAdminOr):
    def allows(self, request, view):
        return project_role(request, view) is not None


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
