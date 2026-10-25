from rest_framework.permissions import BasePermission
from .choices import RoleChoices, MemberRoleChoices
from .models import TeamMember, ProjectMember


def is_admin(user):
    return user.role == RoleChoices.ADMIN


def project_role(request, view):
    project_id = view.kwargs[getattr(view, 'project_lookup_kwarg', 'project_id')]
    if not hasattr(request, 'project_roles'):
        request.project_roles = {}
    if project_id not in request.project_roles:
        request.project_roles[project_id] = ProjectMember.objects.filter(
            project_id=project_id, user=request.user
        ).values_list('role', flat=True).first()
    return request.project_roles[project_id]


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (is_admin(user) or self.allows(request, view)))

    def allows(self, request, view):
        return False


class IsAdminOrTeamLead(IsAdmin):
    def allows(self, request, view):
        return TeamMember.objects.filter(
            team_id=view.kwargs.get('team_id'), user=request.user, role=MemberRoleChoices.TEAM_LEAD
        ).exists()


class IsAdminOrProjectTeamLead(IsAdmin):
    def allows(self, request, view):
        return project_role(request, view) == MemberRoleChoices.TEAM_LEAD


class IsAdminOrProjectMember(IsAdmin):
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


class CanEditTask(IsAuthorOrProjectTeamLead):
    message = 'Менять можно только свои задачи'

    def has_object_permission(self, request, view, obj):
        return obj.assignee_id == request.user.id or super().has_object_permission(request, view, obj)
