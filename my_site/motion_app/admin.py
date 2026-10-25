from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.utils.html import format_html
from modeltranslation.admin import TabbedTranslationAdmin
from .models import (
    UserProfile, WorkExperience, Education, Language, Certificate,
    Team, TeamMember, Project, ProjectMember, Task, TaskComment, TaskAttachment, TaskHistory, ClientRequest
)
from .choices import RoleChoices
from .services import (
    task_created, task_changed, comment_created, member_removed, task_file_url, is_last_admin, LAST_ADMIN_ERROR,
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
        if (demoted or not cleaned_data.get('is_active', self.instance.is_active)) and is_last_admin(self.instance):
            raise forms.ValidationError(LAST_ADMIN_ERROR)
        return cleaned_data


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

    def get_deleted_objects(self, objs, request):
        deleted, model_count, perms_needed, protected = super().get_deleted_objects(objs, request)
        admins_left = UserProfile.objects.filter(role=RoleChoices.ADMIN, is_active=True).exclude(
            pk__in=[user.pk for user in objs]
        )
        if any(user.role == RoleChoices.ADMIN for user in objs) and not admins_left.exists():
            perms_needed.add(LAST_ADMIN_ERROR)
        return deleted, model_count, perms_needed, protected


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
