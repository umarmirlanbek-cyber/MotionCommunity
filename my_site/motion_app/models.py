import os
import uuid
from functools import cache

from django.conf import settings
from django.db import models, transaction
from django.contrib.auth.models import AbstractUser, UserManager
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.core.validators import FileExtensionValidator, RegexValidator
from django.db.models.signals import post_delete, pre_save
from django.utils import timezone
from django.utils.deconstruct import deconstructible
from phonenumber_field.modelfields import PhoneNumberField
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from .choices import (
    RoleChoices, StatusChoices, PositionChoices, MemberRoleChoices, ProjectStatusChoices,
    TaskStatusChoices, TaskPriorityChoices, TaskTypeChoices, NotificationTypeChoices, ClientStatusChoices,
    WorkingFormatChoices, LanguageLevelChoices,
)


MAX_FILE_SIZE_MB = 5
MAX_LABELS = 10
MAX_LABEL_LENGTH = 50
ASSIGNEE_NOT_MEMBER = 'Исполнитель должен состоять в проекте'
ATTACHMENT_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip']


def validate_file_size(file):
    if file.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValidationError(f'Файл больше {MAX_FILE_SIZE_MB} МБ')


validate_label = RegexValidator(r'^[^,]+$', 'Метка не может содержать запятую')


@deconstructible
class RandomName:
    def __init__(self, folder):
        self.folder = folder

    def __call__(self, instance, filename):
        return f'{self.folder}/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}'

    def __eq__(self, other):
        return isinstance(other, RandomName) and self.folder == other.folder


task_file_path = RandomName('task_files')


@deconstructible
class PrivateStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(base_url='/private/')

    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)


class UserProfileManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', RoleChoices.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)

    def public(self):
        return self.filter(role=RoleChoices.MEMBER, status=StatusChoices.ACTIVE, is_active=True)


class UserProfile(AbstractUser):
    avatar = models.ImageField(
        'Аватар участника', upload_to=RandomName('members_image'), blank=True, null=True, validators=[validate_file_size]
    )
    bio = models.TextField('О себе', blank=True)
    position = models.CharField(
        'Должность', max_length=50, choices=PositionChoices.choices, default=PositionChoices.BACKEND_DEVELOPER
    )
    skills = models.TextField('Навыки', blank=True)
    github = models.URLField('Гитхаб', blank=True, null=True)
    linkedin = models.URLField('Линкедин', blank=True, null=True)
    portfolio = models.URLField('Портфолио', blank=True, null=True)
    resume = models.FileField(
        'Резюме', upload_to=RandomName('resume'), blank=True, null=True,
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx']), validate_file_size],
    )
    role = models.CharField(max_length=20, choices=RoleChoices.choices, default=RoleChoices.MEMBER)
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.INACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserProfileManager()

    class Meta(AbstractUser.Meta):
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.username

    def save(self, *args, **kwargs):
        self.is_staff = self.role == RoleChoices.ADMIN
        self.is_superuser = self.role == RoleChoices.ADMIN
        password_changed = self.pk is not None and self._password is not None
        super().save(*args, **kwargs)
        if password_changed or not self.is_active:
            revoke_tokens(self)


def revoke_tokens(user):
    tokens = OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True, expires_at__gt=timezone.now())
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token_id=pk) for pk in tokens.values_list('pk', flat=True)], ignore_conflicts=True
    )


# ---------- Резюме: опыт, образование, языки, сертификаты ----------

class WorkExperience(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='work')
    company = models.CharField('Компания', max_length=150)
    position = models.CharField('Должность', max_length=150)
    start_date = models.DateField('Начало работы')
    end_date = models.DateField('Конец работы', null=True, blank=True)
    working_format = models.CharField(
        max_length=20, choices=WorkingFormatChoices.choices, default=WorkingFormatChoices.OFFICE
    )
    achievements = models.TextField('Достижения', blank=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f'{self.user} - {self.company}'


class Education(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='education')
    institution = models.CharField('Учебное заведение', max_length=150)
    specialization = models.CharField('Специальность', max_length=150)
    start_year = models.PositiveSmallIntegerField('Год начала')
    end_year = models.PositiveSmallIntegerField('Год окончания', null=True, blank=True)
    studying_now = models.BooleanField('Учусь сейчас', default=False)
    description = models.TextField('Описание', blank=True)

    class Meta:
        ordering = ['-start_year']

    def __str__(self):
        return f'{self.user} - {self.institution}'


class Language(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='languages')
    name = models.CharField('Язык', max_length=150)
    level = models.CharField(max_length=20, choices=LanguageLevelChoices.choices, default=LanguageLevelChoices.A1)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.name} - {self.level}'


class Certificate(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='certificates')
    title = models.CharField('Название', max_length=150)
    organization = models.CharField('Организация', max_length=150)
    issue_date = models.DateField('Дата выдачи')
    description = models.TextField('Описание', blank=True)
    image = models.ImageField('Скан сертификата', upload_to=RandomName('certificates'), validators=[validate_file_size])

    class Meta:
        ordering = ['-issue_date']

    def __str__(self):
        return self.title


# ---------- Команды ----------

class Team(models.Model):
    name = models.CharField('Название команды', max_length=255)
    description = models.TextField('Описание', blank=True)
    image = models.ImageField(
        'Фото команды', upload_to=RandomName('team_image'), blank=True, null=True, validators=[validate_file_size]
    )
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class TeamMember(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='team_memberships')
    role = models.CharField(max_length=20, choices=MemberRoleChoices.choices, default=MemberRoleChoices.MEMBER)

    class Meta:
        unique_together = ('team', 'user')  # запрет дублей
        ordering = ['id']

    def __str__(self):
        return f'{self.user} - {self.team}'


# ---------- Проекты ----------

class Project(models.Model):
    team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, related_name='projects', null=True, blank=True
    )
    name = models.CharField('Название', max_length=150)
    description = models.TextField('Описание')
    status = models.CharField(max_length=20, choices=ProjectStatusChoices.choices, default=ProjectStatusChoices.PLANNED)
    category = models.CharField('Категория', max_length=150)
    image = models.ImageField(
        'Изображение', upload_to=RandomName('preview_image'), blank=True, null=True, validators=[validate_file_size]
    )
    demo_url = models.URLField('Демо', blank=True, null=True)
    github_url = models.URLField('Гитхаб', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class ProjectMember(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='project_memberships')
    role = models.CharField(max_length=20, choices=MemberRoleChoices.choices, default=MemberRoleChoices.MEMBER)

    class Meta:
        unique_together = ('project', 'user')  # запрет дублей
        ordering = ['id']

    def __str__(self):
        return f'{self.user} - {self.project}'


# ---------- Задачи ----------

class Task(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField('Название', max_length=255)
    description = models.TextField('Описание', blank=True)
    status = models.CharField(max_length=20, choices=TaskStatusChoices.choices, default=TaskStatusChoices.TO_DO)
    priority = models.CharField(max_length=20, choices=TaskPriorityChoices.choices, default=TaskPriorityChoices.MEDIUM)
    type = models.CharField(max_length=20, choices=TaskTypeChoices.choices, default=TaskTypeChoices.TASK)
    labels = ArrayField(
        models.CharField(max_length=MAX_LABEL_LENGTH, validators=[validate_label]), size=MAX_LABELS,
        verbose_name='Метки', blank=True, default=list,
    )
    assignee = models.ForeignKey(
        UserProfile, on_delete=models.SET_NULL, related_name='assigned_tasks', null=True, blank=True
    )
    author = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, related_name='created_tasks', null=True)
    due_date = models.DateField('Срок', null=True, blank=True)
    order = models.PositiveIntegerField('Порядок в колонке', default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'id']
        indexes = [GinIndex(fields=['labels'])]

    def __str__(self):
        return self.title

    def clean(self):
        current = Task.objects.filter(pk=self.pk).values_list('assignee_id', flat=True).first()
        if not can_be_assignee(self.project_id, self.assignee_id, current):
            raise ValidationError({'assignee': ASSIGNEE_NOT_MEMBER})


def can_be_assignee(project_id, user_id, current_assignee_id=None, lock=False):
    if not user_id or user_id == current_assignee_id:
        return True
    members = ProjectMember.objects.select_for_update() if lock else ProjectMember.objects
    return members.filter(project_id=project_id, user_id=user_id).exists()


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, related_name='task_comments', null=True)
    text = models.TextField('Текст')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.author} - {self.task}'


class TaskAttachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments')
    author = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, related_name='task_attachments', null=True)
    file = models.FileField(
        'Файл', upload_to=task_file_path, storage=PrivateStorage(), max_length=255,
        validators=[FileExtensionValidator(ATTACHMENT_EXTENSIONS), validate_file_size],
    )
    name = models.CharField('Имя файла', max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = os.path.basename(self.file.name)[:255]
        super().save(*args, **kwargs)


class TaskHistory(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='history')
    user = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, related_name='task_changes', null=True)
    field = models.CharField('Поле', max_length=30)
    old_value = models.CharField('Было', max_length=255, blank=True)
    new_value = models.CharField('Стало', max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.task} - {self.field}'


# ---------- Уведомления ----------

class Notification(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='notifications')
    actor = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, related_name='+', null=True)
    type = models.CharField(max_length=20, choices=NotificationTypeChoices.choices)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='notifications')
    comment = models.ForeignKey(TaskComment, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['user', 'is_read', '-created_at'])]

    def __str__(self):
        return f'{self.user} - {self.type}'


# ---------- Заявки клиентов ----------

class ClientRequest(models.Model):
    name = models.CharField('Имя', max_length=150)
    company = models.CharField('Компания', max_length=150)
    email = models.EmailField()
    phone = PhoneNumberField('Телефон')
    title = models.CharField('Тема', max_length=150)
    description = models.TextField('Описание')
    project_type = models.CharField('Тип проекта', max_length=150)
    budget = models.PositiveIntegerField('Бюджет', null=True, blank=True)
    status = models.CharField(max_length=20, choices=ClientStatusChoices.choices, default=ClientStatusChoices.NEW)
    project = models.OneToOneField(
        Project, on_delete=models.SET_NULL, related_name='client_request', null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} - {self.title}'


# ---------- Файлы ----------

@cache
def file_fields(model):
    return [field.name for field in model._meta.concrete_fields if isinstance(field, models.FileField)]


def delete_file_on_commit(storage, name):
    if name:
        transaction.on_commit(lambda: storage.delete(name))


def delete_replaced_files(sender, instance, update_fields=None, **kwargs):
    fields = [field for field in file_fields(sender) if update_fields is None or field in update_fields]
    if not instance.pk or not fields:
        return
    old = sender._default_manager.filter(pk=instance.pk).values(*fields).first() or {}
    for field in fields:
        file = getattr(instance, field)
        if old.get(field) and old[field] != file.name:
            delete_file_on_commit(file.storage, old[field])


def delete_files(sender, instance, **kwargs):
    for field in file_fields(sender):
        file = getattr(instance, field)
        delete_file_on_commit(file.storage, file.name)


pre_save.connect(delete_replaced_files)
post_delete.connect(delete_files)
