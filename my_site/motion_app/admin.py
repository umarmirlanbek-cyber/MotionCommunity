from django import forms
from django.contrib import admin, messages
from django.contrib.admin.actions import delete_selected
from django.contrib.admin.utils import unquote
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from modeltranslation.admin import TabbedTranslationAdmin
from .models import (
    UserProfile, WorkExperience, Education, Language, Certificate,
    Team, TeamMember, Project, ProjectMember, Task, TaskComment, TaskAttachment, TaskHistory, ClientRequest
)
from .choices import RoleChoices
from .services import (
    task_created, task_changed, comment_created, member_removed, task_file_url, leaves_no_admin, LAST_ADMIN_ERROR,
)


class WorkExperienceInline(admin.StackedInline):
    model = WorkExperience
    extra = 0


class EducationInline(admin.StackedInline):
    model = Education
    extra = 0


class LanguageInline(admin.TabularInline):
    model = Language
    extra = 0


class CertificateInline(admin.StackedInline):
    model = Certificate
    extra = 0


class UserProfileChangeForm(UserChangeForm):
    def clean(self):
        cleaned_data = super().clean()
        demoted = cleaned_data.get('role', self.instance.role) != RoleChoices.ADMIN
        removed = demoted or not cleaned_data.get('is_active', self.instance.is_active)
        if removed and leaves_no_admin([self.instance], lock=True):
            raise forms.ValidationError(LAST_ADMIN_ERROR)
        return cleaned_data


def delete_selected_users(modeladmin, request, queryset):
    if leaves_no_admin(list(queryset)):
        modeladmin.message_user(request, LAST_ADMIN_ERROR, messages.ERROR)
        return None
    return delete_selected(modeladmin, request, queryset)


@admin.register(UserProfile)
class UserProfileAdmin(TabbedTranslationAdmin, UserAdmin):
    form = UserProfileChangeForm
    list_display = ('username', 'first_name', 'last_name', 'role', 'status', 'is_active')
    list_filter = ('role', 'status', 'is_active')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Личные данные', {'fields': ('first_name', 'last_name', 'email')}),
        ('Доступ', {'fields': ('role', 'status', 'is_active')}),
        ('Профиль', {'fields': ('avatar', 'bio', 'position', 'skills', 'github', 'linkedin', 'portfolio', 'resume')}),
    )
    inlines = [WorkExperienceInline, EducationInline, LanguageInline, CertificateInline]

    def get_inlines(self, request, obj):
        return self.inlines if obj else []

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            actions['delete_selected'] = (delete_selected_users, *actions['delete_selected'][1:])
        return actions

    def delete_view(self, request, object_id, extra_context=None):
        user = self.get_object(request, unquote(object_id))
        if user and leaves_no_admin([user]):
            self.message_user(request, LAST_ADMIN_ERROR, messages.ERROR)
            return HttpResponseRedirect(reverse('admin:motion_app_userprofile_change', args=[user.pk]))
        return super().delete_view(request, object_id, extra_context)


class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 0
    autocomplete_fields = ('user',)


@admin.register(Team)
class TeamAdmin(TabbedTranslationAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)
    inlines = [TeamMemberInline]


class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    extra = 0
    autocomplete_fields = ('user',)


@admin.register(Project)
class ProjectAdmin(TabbedTranslationAdmin):
    list_display = ('name', 'status', 'category', 'team', 'created_at')
    list_filter = ('status', 'category')
    search_fields = ('name',)
    inlines = [ProjectMemberInline]

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if formset.model is ProjectMember:
            for member in formset.deleted_objects:
                member_removed(member, request.user)


class TaskCommentInline(admin.TabularInline):
    model = TaskComment
    extra = 0
    autocomplete_fields = ('author',)


class TaskAttachmentInline(admin.TabularInline):
    model = TaskAttachment
    extra = 0
    fields = ('download', 'author', 'created_at')
    readonly_fields = fields

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('author')

    def has_add_permission(self, request, obj):
        return False

    @admin.display(description='Файл')
    def download(self, attachment):
        return format_html('<a href="{}">{}</a>', task_file_url(attachment), attachment.name)


class TaskHistoryInline(admin.TabularInline):
    model = TaskHistory
    extra = 0
    can_delete = False
    readonly_fields = ('user', 'field', 'old_value', 'new_value', 'created_at')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

    def has_add_permission(self, request, obj):
        return False


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'status', 'priority', 'type', 'assignee', 'due_date')
    list_filter = ('status', 'priority', 'type', 'project')
    search_fields = ('title',)
    autocomplete_fields = ('assignee', 'author')
    inlines = [TaskCommentInline, TaskAttachmentInline, TaskHistoryInline]

    def save_model(self, request, obj, form, change):
        old = Task.objects.get(pk=obj.pk) if change else None
        super().save_model(request, obj, form, change)
        if old:
            task_changed(old, obj, request.user)
        else:
            task_created(obj, request.user)

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if formset.model is TaskComment:
            for comment in formset.new_objects:
                comment_created(comment)


@admin.register(ClientRequest)
class ClientRequestAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'title', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('name', 'company', 'title')
