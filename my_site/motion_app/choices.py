from django.db import models


class RoleChoices(models.TextChoices):
    ADMIN = 'Admin', 'Администратор'
    MEMBER = 'Member', 'Участник'


class StatusChoices(models.TextChoices):
    ACTIVE = 'Active', 'Профиль заполнен'
    INACTIVE = 'Inactive', 'Профиль не заполнен'


class PositionChoices(models.TextChoices):
    FRONTEND_DEVELOPER = 'Frontend_Developer', 'Frontend Developer'
    BACKEND_DEVELOPER = 'Backend_Developer', 'Backend Developer'
    FULLSTACK_DEVELOPER = 'Fullstack_Developer', 'Fullstack Developer'
    UI_UX_DESIGNER = 'UI_UX_Designer', 'UI/UX Designer'
    QA_ENGINEER = 'QA_Engineer', 'QA Engineer'
    MOBILE_DEVELOPER = 'Mobile_Developer', 'Mobile Developer'


class MemberRoleChoices(models.TextChoices):
    TEAM_LEAD = 'Team_Lead', 'Тим Лид'
    MEMBER = 'Member', 'Участник'


class ProjectStatusChoices(models.TextChoices):
    PLANNED = 'Planned', 'Запланирован'
    IN_PROGRESS = 'In_progress', 'В работе'
    COMPLETED = 'Completed', 'Завершён'
    PAUSED = 'Paused', 'На паузе'


class ClientStatusChoices(models.TextChoices):
    NEW = 'New', 'Новая'
    REVIEWING = 'Reviewing', 'На рассмотрении'
    ACCEPTED = 'Accepted', 'Принята'
    REJECTED = 'Rejected', 'Отклонена'


class WorkingFormatChoices(models.TextChoices):
    OFFICE = 'office', 'В офисе'
    REMOTE = 'remote', 'Удалённо'
    HYBRID = 'hybrid', 'Гибрид'
    FREELANCE = 'freelance', 'Фриланс'
    PART_TIME = 'part_time', 'Неполный рабочий день'
    FULL_TIME = 'full_time', 'Полный рабочий день'
    CONTRACT = 'contract', 'По контракту'
    INTERNSHIP = 'internship', 'Стажировка'
    FLEXIBLE = 'flexible', 'Гибкий график'


class LanguageLevelChoices(models.TextChoices):
    A1 = 'A1', 'Начальный'
    A2 = 'A2', 'Базовый'
    B1 = 'B1', 'Средний'
    B2 = 'B2', 'Выше среднего'
    C1 = 'C1', 'Продвинутый'
    C2 = 'C2', 'Свободный'
    NATIVE = 'Native', 'Родной язык'
