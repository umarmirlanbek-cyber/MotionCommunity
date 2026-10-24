"""
Полностью очищает БД (кроме структуры таблиц) и заполняет тестовыми данными:
1 Admin, 2 Team Lead, 10 участников, 5 команд, 5 проектов, задачи в первом проекте, 3 заявки клиентов.

Использование:
    python manage.py seed_data
Каждый запуск ПОЛНОСТЬЮ пересоздаёт данные (сначала delete, потом create).
Работает только при DEBUG=True, чтобы случайно не стереть боевую базу.
"""

from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from motion_app.models import (
    UserProfile, WorkExperience, Education, Language, Team, TeamMember, Project, ProjectMember,
    Task, TaskComment, ClientRequest
)
from motion_app.choices import (
    MemberRoleChoices, StatusChoices, ClientStatusChoices, LanguageLevelChoices,
    TaskStatusChoices, TaskPriorityChoices, TaskTypeChoices
)


class Command(BaseCommand):
    help = 'Очищает БД и заполняет тестовыми пользователями, командами, проектами и заявками'

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('seed_data стирает всю базу. Запускайте только локально, с DEBUG=True.')

        self.clear_all()

        self.create_admin()
        leads = self.create_team_leads()
        developers = self.create_developers()
        teams = self.create_teams()
        projects = self.create_projects()
        self.distribute(leads, developers, teams, projects)
        self.create_resume(developers[0])
        self.create_tasks(projects[0])
        self.create_client_requests()

        self.stdout.write(self.style.SUCCESS(
            f'Готово: 1 admin, {len(leads)} team lead, {len(developers)} участников, '
            f'{len(teams)} команд, {len(projects)} проектов.'
        ))

    # ---------- очистка ----------

    def clear_all(self):
        ClientRequest.objects.all().delete()
        Project.objects.all().delete()
        Team.objects.all().delete()
        UserProfile.objects.all().delete()
        self.stdout.write(self.style.WARNING('БД очищена.'))

    # ---------- Users ----------

    def create_admin(self):
        return UserProfile.objects.create_superuser(
            username='admin',
            email='admin@motion.community',
            password='Admin12345!',
            first_name='Admin',
            status=StatusChoices.ACTIVE,
        )

    def create_members(self, data, password, bio):
        return [
            UserProfile.objects.create_user(
                username=username,
                email=f'{username}@motion.community',
                password=password,
                first_name=first,
                last_name=last,
                position=position,
                status=StatusChoices.ACTIVE,
                bio=bio.format(first=first, last=last, position=position.replace('_', ' ')),
            )
            for username, first, last, position in data
        ]

    def create_team_leads(self):
        data = [
            ('lead1', 'Нурлан', 'Асанов', 'Fullstack_Developer'),
            ('lead2', 'Айгерим', 'Токтогулова', 'Backend_Developer'),
        ]
        return self.create_members(
            data, 'TeamLead12345!', '{first} {last} - тимлид в Motion Community, ведёт несколько проектов одновременно.'
        )

    def create_developers(self):
        data = [
            ('dev1', 'Азамат', 'Кубанычбеков', 'Frontend_Developer'),
            ('dev2', 'Диана', 'Осмонова', 'Frontend_Developer'),
            ('dev3', 'Тимур', 'Жумабеков', 'Backend_Developer'),
            ('dev4', 'Камила', 'Сыдыкова', 'Backend_Developer'),
            ('dev5', 'Эрлан', 'Абдразаков', 'Fullstack_Developer'),
            ('dev6', 'Жаннат', 'Мамытова', 'Fullstack_Developer'),
            ('dev7', 'Бекзат', 'Орозалиев', 'UI_UX_Designer'),
            ('dev8', 'Мээрим', 'Курманбекова', 'UI_UX_Designer'),
            ('dev9', 'Данияр', 'Сатыбалдиев', 'QA_Engineer'),
            ('dev10', 'Нургуль', 'Бекова', 'Mobile_Developer'),
        ]
        return self.create_members(
            data, 'Developer12345!', '{first} {last} - участник Motion Community, специализация: {position}.'
        )

    # ---------- Teams ----------

    def create_teams(self):
        data = [
            ('Alpha Team', 'Команда, работающая над образовательными продуктами.'),
            ('Beta Team', 'Команда, отвечающая за клиентские веб-приложения.'),
            ('Gamma Team', 'Команда мобильной разработки.'),
            ('Delta Team', 'Команда аналитики и внутренних инструментов.'),
            ('Omega Team', 'Команда, работающая над маркетплейс-проектами.'),
        ]
        return [Team.objects.create(name=name, description=desc) for name, desc in data]

    # ---------- Projects ----------

    def create_projects(self):
        data = [
            ('Motion LMS Platform', 'Planned', 'Education',
                'Платформа для онлайн-обучения студентов Motion с курсами и тестами.'),
            ('Motion Community Portal', 'In_progress', 'Web',
                'Портал сообщества с профилями участников и проектами.'),
            ('Motion Mobile Companion', 'In_progress', 'Mobile',
                'Мобильное приложение-компаньон для участников Motion.'),
            ('Motion Analytics Dashboard', 'Completed', 'Analytics',
                'Дашборд аналитики успеваемости и активности студентов.'),
            ('Motion Marketplace', 'Paused', 'E-commerce',
                'Маркетплейс для продажи цифровых продуктов выпускников.'),
        ]
        return [
            Project.objects.create(name=name, status=status, category=category, description=desc)
            for name, status, category, desc in data
        ]

    # ---------- Распределение по командам/проектам ----------

    def distribute(self, leads, developers, teams, projects):
        chunks = [developers[i::5] for i in range(5)]  # 10 разработчиков на 5 групп

        for i, (team, project) in enumerate(zip(teams, projects)):
            lead = leads[i % len(leads)]
            group = chunks[i]

            project.team = team
            project.save()

            TeamMember.objects.create(team=team, user=lead, role=MemberRoleChoices.TEAM_LEAD)
            ProjectMember.objects.create(project=project, user=lead, role=MemberRoleChoices.TEAM_LEAD)

            for dev in group:
                TeamMember.objects.create(team=team, user=dev)
                ProjectMember.objects.create(project=project, user=dev)

    # ---------- Резюме (одному участнику, чтобы фронту было что показать) ----------

    def create_resume(self, user):
        WorkExperience.objects.create(
            user=user, company='Motion Web', position='Frontend Developer',
            start_date=date(2024, 9, 1), achievements='Сделал личный кабинет участника.',
        )
        Education.objects.create(
            user=user, institution='КГТУ им. Раззакова', specialization='Информатика',
            start_year=2021, end_year=2025,
        )
        Language.objects.create(user=user, name='Английский', level=LanguageLevelChoices.B2)

    # ---------- Задачи (доска одного проекта) ----------

    def create_tasks(self, project):
        members = [member.user for member in project.members.order_by('id')]
        lead = members[0]
        data = [
            ('Сверстать страницу курса', TaskStatusChoices.TO_DO, TaskPriorityChoices.MEDIUM,
             TaskTypeChoices.FEATURE, ['frontend']),
            ('Тесты для модуля оплаты', TaskStatusChoices.TO_DO, TaskPriorityChoices.LOW,
             TaskTypeChoices.TASK, ['backend', 'tests']),
            ('API списка уроков', TaskStatusChoices.IN_PROGRESS, TaskPriorityChoices.HIGH,
             TaskTypeChoices.FEATURE, ['backend']),
            ('Вход через Google', TaskStatusChoices.REVIEW, TaskPriorityChoices.MEDIUM,
             TaskTypeChoices.BUG, ['backend', 'frontend']),
            ('Настроить CI', TaskStatusChoices.DONE, TaskPriorityChoices.CRITICAL,
             TaskTypeChoices.IMPROVEMENT, ['devops']),
        ]
        for i, (title, task_status, priority, task_type, labels) in enumerate(data):
            task = Task.objects.create(
                project=project, title=title, status=task_status, priority=priority,
                type=task_type, labels=labels, assignee=members[i % len(members)], author=lead,
            )
            if task_status == TaskStatusChoices.REVIEW:
                TaskComment.objects.create(task=task, author=lead, text='Посмотрю сегодня вечером.')

    # ---------- Client requests ----------

    def create_client_requests(self):
        data = [
            ('Марат Осмонов', 'ТОО Финтех', 'marat@fintech.kg', '+996700123456',
             'Нужен CRM для отдела продаж', 'CRM', 500000, ClientStatusChoices.ACCEPTED),
            ('Айнура Дуйшеева', 'EduTech LLC', 'ainura@edutech.kg', '+996555987654',
             'Платформа для онлайн-курсов', 'LMS', 800000, ClientStatusChoices.REVIEWING),
            ('Бакыт Жумалиев', 'ShopKG', 'bakyt@shopkg.kg', '+996700555222',
             'Интернет-магазин с доставкой', 'E-commerce', 350000, ClientStatusChoices.NEW),
        ]
        for name, company, email, phone, title, ptype, budget, status in data:
            ClientRequest.objects.create(
                name=name, company=company, email=email, phone=phone,
                title=title, description=f'{title} - подробности обсудим на созвоне.',
                project_type=ptype, budget=budget, status=status,
            )
