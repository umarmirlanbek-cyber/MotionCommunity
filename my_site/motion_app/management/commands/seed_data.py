"""
Полностью очищает БД (кроме структуры таблиц) и заполняет тестовыми данными:
1 Admin, 2 Team Lead, 10 Developer, 5 команд, 5 проектов, 3 заявки клиентов.

Использование:
    python manage.py seed_data
Каждый запуск ПОЛНОСТЬЮ пересоздаёт данные (сначала delete, потом create).
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from motion_app.models import (
    UserProfile, Team, TeamMember, Project, ProjectMember, ClientRequest,
    RoleChoices, MemberRoleChoices, StatusChoices,
)


class Command(BaseCommand):
    help = 'Очищает БД и заполняет тестовыми пользователями, командами, проектами и заявками'

    @transaction.atomic
    def handle(self, *args, **options):
        self.clear_all()

        admin = self.create_admin()
        leads = self.create_team_leads()
        developers = self.create_developers()
        teams = self.create_teams()
        projects = self.create_projects()
        self.distribute(leads, developers, teams, projects)
        self.create_client_requests()

        self.stdout.write(self.style.SUCCESS(
            f'Готово: 1 admin, {len(leads)} team lead, {len(developers)} developer, '
            f'{len(teams)} команд, {len(projects)} проектов.'
        ))

    # ---------- очистка ----------

    def clear_all(self):
        ClientRequest.objects.all().delete()
        ProjectMember.objects.all().delete()
        TeamMember.objects.all().delete()
        Project.objects.all().delete()
        Team.objects.all().delete()
        UserProfile.objects.all().delete()
        self.stdout.write(self.style.WARNING('БД очищена.'))

    # ---------- Users ----------

    def create_admin(self):
        user = UserProfile.objects.create_superuser(
            username='admin',
            email='admin@motion.community',
            password='Admin12345!',
        )
        user.role = RoleChoices.ADMIN
        user.status = StatusChoices.ACTIVE
        user.first_name = 'Admin'
        user.save()
        return user

    def create_team_leads(self):
        data = [
            ('lead1', 'Нурлан', 'Асанов', 'Fullstack_Developer'),
            ('lead2', 'Айгерим', 'Токтогулова', 'Backend_Developer'),
        ]
        leads = []
        for username, first, last, position in data:
            user = UserProfile.objects.create_user(
                username=username,
                email=f'{username}@motion.community',
                password='TeamLead12345!',
                first_name=first,
                last_name=last,
                position=position,
                role=RoleChoices.TEAM_LEAD,
                status=StatusChoices.ACTIVE,
                bio=f'{first} {last} — тимлид в Motion Community, ведёт несколько проектов одновременно.',
            )
            leads.append(user)
        return leads

    def create_developers(self):
        data = [
            ('dev1', 'Азамат', 'Кубанычбеков', 'Frontend_Developer'),
            ('dev2', 'Диана', 'Осмонова', 'Frontend_Developer'),
            ('dev3', 'Тимур', 'Жумабеков', 'Backend_Developer'),
            ('dev4', 'Камила', 'Сыдыкова', 'Backend_Developer'),
            ('dev5', 'Эрлан', 'Абдразаков', 'Fullstack_Developer'),
            ('dev6', 'Жаннат', 'Мамытова', 'Fullstack_Developer'),
            ('dev7', 'Бекзат', 'Орозалиев', 'UI/UX_Designer'),
            ('dev8', 'Мээрим', 'Курманбекова', 'UI/UX_Designer'),
            ('dev9', 'Данияр', 'Сатыбалдиев', 'QA_Engineer'),
            ('dev10', 'Нургуль', 'Бекова', 'Mobile_Developer'),
        ]
        developers = []
        for username, first, last, position in data:
            user = UserProfile.objects.create_user(
                username=username,
                email=f'{username}@motion.community',
                password='Developer12345!',
                first_name=first,
                last_name=last,
                position=position,
                role=RoleChoices.DEVELOPER,
                status=StatusChoices.ACTIVE,
                bio=f'{first} {last} — участник Motion Community, специализация: {position.replace("_", " ")}.',
            )
            developers.append(user)
        return developers

    # ---------- Teams ----------

    def create_teams(self):
        data = [
            ('Alpha Team', 'Команда, работающая над образовательными продуктами.'),
            ('Beta Team', 'Команда, отвечающая за клиентские веб-приложения.'),
            ('Gamma Team', 'Команда мобильной разработки.'),
            ('Delta Team', 'Команда аналитики и внутренних инструментов.'),
            ('Omega Team', 'Команда, работающая над маркетплейс-проектами.'),
        ]
        return [Team.objects.create(team_name=name, description=desc) for name, desc in data]

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
            Project.objects.create(name=name, project_status=status, category=category, description=desc)
            for name, status, category, desc in data
        ]

    # ---------- Распределение по командам/проектам ----------

    def distribute(self, leads, developers, teams, projects):
        chunks = [developers[i::5] for i in range(5)]  # 10 разработчиков на 5 групп

        for i, (team, project) in enumerate(zip(teams, projects)):
            lead = leads[i % len(leads)]
            group = chunks[i]

            TeamMember.objects.create(team=team, user=lead, role=MemberRoleChoices.TEAM_LEAD)
            ProjectMember.objects.create(project=project, user=lead, role=MemberRoleChoices.TEAM_LEAD)

            for dev in group:
                TeamMember.objects.create(team=team, user=dev, role=MemberRoleChoices.DEVELOPER)
                ProjectMember.objects.create(project=project, user=dev, role=MemberRoleChoices.DEVELOPER)

    # ---------- Client requests ----------

    def create_client_requests(self):
        data = [
            ('Марат Осмонов', 'ТОО Финтех', 'marat@fintech.kg', '+996700123456',
             'Нужен CRM для отдела продаж', 'CRM', 500000),
            ('Айнура Дуйшеева', 'EduTech LLC', 'ainura@edutech.kg', '+996555987654',
             'Платформа для онлайн-курсов', 'LMS', 800000),
            ('Бакыт Жумалиев', 'ShopKG', 'bakyt@shopkg.kg', '+996700555222',
             'Интернет-магазин с доставкой', 'E-commerce', 350000),
        ]
        for name, company, email, phone, title, ptype, budget in data:
            ClientRequest.objects.create(
                name=name, company=company, email=email, phone=phone,
                title=title, description=f'{title} — подробности обсудим на созвоне.',
                project_type=ptype, budget=budget,
            )