from django.db import models
from django.contrib.auth.models import AbstractUser, UserManager
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from phonenumber_field.modelfields import PhoneNumberField
from .choices import (
    RoleChoices, StatusChoices, PositionChoices, MemberRoleChoices, ProjectStatusChoices,
    TaskStatusChoices, TaskPriorityChoices, TaskTypeChoices, ClientStatusChoices, WorkingFormatChoices, LanguageLevelChoices
)


MAX_FILE_SIZE_MB = 5


def validate_file_size(file):
    if file.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValidationError(f'Файл больше {MAX_FILE_SIZE_MB} МБ')


class UserProfileManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', RoleChoices.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class UserProfile(AbstractUser):
    avatar = models.ImageField(
        'Аватар участника', upload_to='members_image/', blank=True, null=True, validators=[validate_file_size]
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
        'Резюме', upload_to='resume/', blank=True, null=True,
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
        super().save(*args, **kwargs)


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
    image = models.ImageField('Скан сертификата', upload_to='certificates/', validators=[validate_file_size])

    class Meta:
        ordering = ['-issue_date']

    def __str__(self):
        return self.title


# ---------- Команды ----------

class Team(models.Model):
    name = models.CharField('Название команды', max_length=255)
    description = models.TextField('Описание', blank=True)
    image = models.ImageField(
        'Фото команды', upload_to='team_image/', blank=True, null=True, validators=[validate_file_size]
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
        'Изображение', upload_to='preview_image/', blank=True, null=True, validators=[validate_file_size]
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
    labels = ArrayField(models.CharField(max_length=50), verbose_name='Метки', blank=True, default=list)
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

    def __str__(self):
        return self.title


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, related_name='task_comments', null=True)
    text = models.TextField('Текст')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.author} - {self.task}'


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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} - {self.title}'
