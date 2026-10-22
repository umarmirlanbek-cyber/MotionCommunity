from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from modeltranslation.admin import TabbedTranslationAdmin
from .models import (
    UserProfile, WorkExperience, Education, Language, Certificate,
    Team, TeamMember, Project, ProjectMember, Task, TaskComment, ClientRequest
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


@admin.register(UserProfile)
class UserProfileAdmin(TabbedTranslationAdmin, UserAdmin):
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


class TaskCommentInline(admin.TabularInline):
    model = TaskComment
    extra = 0
    autocomplete_fields = ('author',)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'status', 'priority', 'assignee', 'due_date')
    list_filter = ('status', 'priority', 'project')
    search_fields = ('title',)
    autocomplete_fields = ('assignee', 'author')
    inlines = [TaskCommentInline]


@admin.register(ClientRequest)
class ClientRequestAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'title', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('name', 'company', 'title')
