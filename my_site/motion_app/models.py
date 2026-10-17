from django.db import models
from django.contrib.auth.models import AbstractUser
from phonenumber_field.modelfields import PhoneNumberField


class RoleChoices(models.TextChoices):
    ADMIN = 'Admin', 'Администратор'
    TEAM_LEAD = 'Team_Lead', 'Тим Лид'
    DEVELOPER = 'Developer', 'Разработчик'

class MemberRoleChoices(models.TextChoices):
    TEAM_LEAD = 'Team_Lead', 'Тим Лид'
    DEVELOPER = 'Developer', 'Разработчик'

class StatusChoices(models.TextChoices):
    ACTIVE = 'Active', 'Active'
    INACTIVE = 'Inactive', 'Inactive'


class UserProfile(AbstractUser):
    avatar = models.ImageField('Аватар участника', upload_to='members_image/', blank=True, null=True)
    bio = models.TextField(blank=True)

    PositionChoices = (
        ('Frontend_Developer', 'Frontend Developer'),
        ('Backend_Developer', 'Backend Developer'),
        ('Fullstack_Developer', 'Fullstack Developer'),
        ('UI/UX_Designer', 'UI/UX Designer'),
        ('QA_Engineer', 'QA Engineer'),
        ('Mobile_Developer', 'Mobile Developer'),
    )

    position = models.CharField(max_length=150, choices=PositionChoices, default='Backend_Developer')
    skills = models.TextField(blank=True)
    github = models.URLField('Гитхаб', blank=True, null=True)
    linkedin = models.URLField('Линкедин', blank=True, null=True)
    portfolio = models.URLField('Портфолио', blank=True, null=True)
    resume = models.FileField('Резюме', upload_to='resume/', blank=True, null=True)
    role = models.CharField(max_length=150, choices=RoleChoices.choices, default=RoleChoices.DEVELOPER)
    status = models.CharField(max_length=150, choices=StatusChoices.choices, default=StatusChoices.INACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.first_name} {self.last_name}'




class Team(models.Model):
    team_name = models.CharField('Название команды', max_length=255)
    description = models.TextField(blank=True)
    team_image = models.ImageField('Фото Команды', upload_to='team_image/', blank=True, null=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    def __str__(self):
        return self.team_name


class TeamMember(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(UserProfile, on_delete=models.PROTECT, related_name='team_memberships')
    role = models.CharField(max_length=20, choices=MemberRoleChoices.choices, default=MemberRoleChoices.DEVELOPER)

    class Meta:
        unique_together = ('team', 'user')  # запрет дублей

    def __str__(self):
        return f'{self.user} - {self.team}'


class Project(models.Model):
    team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name='projects', null=True, blank=True)
    name = models.CharField(max_length=150)
    description = models.TextField()
    ProjectStatus = (
        ('Planned', 'Planned'),
        ('In_progress', 'In progress'),
        ('Completed', 'Completed'),
        ('Paused', 'Paused'),
    )
    project_status = models.CharField(max_length=20, choices=ProjectStatus, default='Planned')
    category = models.CharField(max_length=150)
    preview_image = models.ImageField('Изображение', upload_to='preview_image/', blank=True, null=True)
    demo_url = models.URLField('Демо', blank=True, null=True)
    github_url = models.URLField('Гитхаб', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ProjectMember(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(UserProfile, on_delete=models.PROTECT, related_name='project_memberships')
    role = models.CharField(max_length=20, choices=MemberRoleChoices.choices, default=MemberRoleChoices.DEVELOPER)

    class Meta:
        unique_together = ('project', 'user')  # запрет дублей

    def __str__(self):
        return f'{self.user} - {self.project}'


class ClientRequest(models.Model):
    name = models.CharField(max_length=150)
    company = models.CharField(max_length=150)
    email = models.EmailField()
    phone = PhoneNumberField()
    title = models.CharField(max_length=150)
    description = models.TextField()
    project_type = models.CharField(max_length=150)
    budget = models.PositiveIntegerField(null=True, blank=True)

    Client_Status = (
        ('New', 'New'),
        ('Reviewing', 'Reviewing'),
    )

    status = models.CharField(max_length=20, choices=Client_Status, default='New')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.name} - {self.title}'



class WorkExperience(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='work_user')
    company = models.CharField(max_length=150)
    position = models.CharField(max_length=150)
    start_time = models.DateField()
    end_time = models.DateField(null=True, blank=True)
    WorkingChoices = (
        ('office', 'В офисе'),
        ('remote', 'Удалённо'),
        ('hybrid', 'Гибрид'),
        ('freelance', 'Фриланс'),
        ('part_time', 'Неполный рабочий день'),
        ('full_time', 'Полный рабочий день'),
        ('contract', 'По контракту'),
        ('internship', 'Стажировка'),
        ('flexible', 'Гибкий график'),
    )
    working_format = models.CharField(max_length=150, choices=WorkingChoices, default='office')
    achievements = models.TextField()

class Education(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='education_user')
    educational_institution = models.CharField(max_length=150)
    specialization = models.CharField(max_length=150)
    start_year = models.DateField()
    end_year = models.DateField(null=True, blank=True)
    studying_now = models.BooleanField()
    responsibilities = models.TextField()


class Languages(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='language_user')
    Languages_Choices = (
        ('A1', 'Начальный'),
        ('A2', 'Базовый'),
        ('B1', 'Средний'),
        ('B2', 'Выше среднего'),
        ('C1', 'Продвинутый'),
        ('C2', 'Свободный'),
        ('Родной язык', 'Родной язык'),
    )
    Level = models.CharField(max_length=150, choices=Languages_Choices, default='A1')
    languages = models.CharField(max_length=150)


class Certificates(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='certificate_user')
    title = models.CharField(max_length=150)
    organization = models.CharField(max_length=150)
    given_date = models.DateField()
    text = models.TextField()
    certificate_image = models.ImageField(upload_to='certificates/')

