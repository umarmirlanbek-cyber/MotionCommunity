import os
import tempfile
from unittest import mock

from django.contrib.admin import site
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase

from .choices import (
    RoleChoices, StatusChoices, MemberRoleChoices, ClientStatusChoices, TaskStatusChoices, TaskTypeChoices,
    NotificationTypeChoices,
)
from .admin import TaskAdmin, TaskAttachmentInline
from .models import (
    UserProfile, WorkExperience, Team, TeamMember, Project, ProjectMember, Task, TaskComment, TaskAttachment,
    TaskHistory, Notification, ClientRequest,
)
from .swagger import TAG_NAMES


def make_user(username, role=RoleChoices.MEMBER, user_status=StatusChoices.ACTIVE, **kwargs):
    return UserProfile.objects.create_user(
        username=username, password='Pass12345!word', role=role, status=user_status, **kwargs
    )


@override_settings(
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], MEDIA_ROOT=tempfile.mkdtemp()
)
class MotionTestCase(APITestCase):
    def setUp(self):
        cache.clear()


class ProjectTestCase(MotionTestCase):
    def setUp(self):
        super().setUp()
        self.lead = make_user('lead1')
        self.member = make_user('dev1')
        self.other_member = make_user('dev2')
        self.outsider = make_user('dev3')
        self.project = Project.objects.create(name='LMS', description='d', category='Web')
        ProjectMember.objects.create(project=self.project, user=self.lead, role=MemberRoleChoices.TEAM_LEAD)
        ProjectMember.objects.create(project=self.project, user=self.member)
        ProjectMember.objects.create(project=self.project, user=self.other_member)


class AuthTests(MotionTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user('dev1')

    def test_login_returns_tokens_and_user(self):
        response = self.client.post('/api/ru/auth/login/', {'username': 'dev1', 'password': 'Pass12345!word'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertEqual(response.data['user']['username'], 'dev1')

    def test_login_wrong_password(self):
        response = self.client.post('/api/ru/auth/login/', {'username': 'dev1', 'password': 'wrong'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def login(self, password='Pass12345!word'):
        return self.client.post('/api/ru/auth/login/', {'username': 'dev1', 'password': password}).data

    def refresh_status(self, refresh):
        self.client.force_authenticate(None)
        return self.client.post('/api/ru/auth/refresh/', {'refresh': refresh}).status_code

    def test_password_change_revokes_refresh_tokens(self):
        refresh = self.login()['refresh']
        self.client.force_authenticate(self.user)
        self.client.post('/api/ru/me/password/', {'old_password': 'Pass12345!word', 'new_password': 'NewPass12345!'})
        self.assertEqual(self.refresh_status(refresh), status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.refresh_status(self.login('NewPass12345!')['refresh']), status.HTTP_200_OK)

    def test_admin_password_reset_revokes_refresh_tokens(self):
        refresh = self.login()['refresh']
        self.client.force_authenticate(make_user('admin', role=RoleChoices.ADMIN))
        self.client.patch(f'/api/ru/users/{self.user.id}/', {'password': 'NewPass12345!'})
        self.assertEqual(self.refresh_status(refresh), status.HTTP_401_UNAUTHORIZED)

    def test_refresh_of_deleted_user(self):
        refresh = self.login()['refresh']
        self.user.delete()
        self.assertEqual(self.refresh_status(refresh), status.HTTP_401_UNAUTHORIZED)

    def test_login_is_limited(self):
        for _ in range(10):
            self.client.post('/api/ru/auth/login/', {'username': 'dev1', 'password': 'wrong'})
        response = self.client.post('/api/ru/auth/login/', {'username': 'dev1', 'password': 'wrong'})
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class MeTests(MotionTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user('dev1', user_status=StatusChoices.INACTIVE)
        self.client.force_authenticate(self.user)

    def test_me_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/ru/me/').status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.delete('/api/ru/me/').status_code, status.HTTP_401_UNAUTHORIZED)

    def test_member_cannot_make_himself_admin(self):
        self.client.patch('/api/ru/me/', {'role': RoleChoices.ADMIN, 'status': StatusChoices.ACTIVE})
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, RoleChoices.MEMBER)
        self.assertEqual(self.user.status, StatusChoices.INACTIVE)

    def test_profile_becomes_active_after_filling(self):
        response = self.client.patch('/api/ru/me/', {'first_name': 'Азамат'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], StatusChoices.ACTIVE)

    def test_resume_rejects_html(self):
        html = SimpleUploadedFile('cv.html', b'<script>alert(1)</script>', content_type='text/html')
        response = self.client.patch('/api/ru/me/', {'resume': html}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('resume', response.data)

    def test_resume_accepts_pdf(self):
        pdf = SimpleUploadedFile('cv.pdf', b'%PDF-1.4 test', content_type='application/pdf')
        response = self.client.patch('/api/ru/me/', {'resume': pdf}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_files_get_random_names_and_old_ones_are_deleted(self):
        def upload(name):
            pdf = SimpleUploadedFile(name, b'%PDF-1.4 test', content_type='application/pdf')
            with self.captureOnCommitCallbacks(execute=True):
                self.client.patch('/api/ru/me/', {'resume': pdf}, format='multipart')
            self.user.refresh_from_db()
            return self.user.resume.path

        first = upload('Иванов CV.pdf')
        self.assertNotIn('CV', os.path.basename(first))
        second = upload('cv2.pdf')
        self.assertFalse(os.path.exists(first))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.delete('/api/ru/me/')
        self.assertFalse(os.path.exists(second))

    def test_me_queries_do_not_grow(self):
        def count():
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get('/api/ru/me/').status_code, status.HTTP_200_OK)
            return len(queries)

        def join(times):
            for i in range(times):
                TeamMember.objects.create(team=Team.objects.create(name=f'T{i}'), user=self.user)
                project = Project.objects.create(name=f'P{i}', description='d', category='Web')
                ProjectMember.objects.create(project=project, user=self.user)

        join(1)
        before = count()
        join(5)
        self.assertEqual(count(), before)

    def test_change_password_needs_old_password(self):
        response = self.client.post('/api/ru/me/password/', {'old_password': 'wrong', 'new_password': 'NewPass12345!'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post('/api/ru/me/password/', {'old_password': 'Pass12345!word', 'new_password': 'NewPass12345!'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass12345!'))

    def test_delete_me_when_in_team(self):
        TeamMember.objects.create(team=Team.objects.create(name='Alpha'), user=self.user)
        self.assertEqual(self.client.delete('/api/ru/me/').status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(UserProfile.objects.filter(username='dev1').exists())


class ResumeTests(MotionTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user('dev1')
        self.other = make_user('dev2')
        self.client.force_authenticate(self.user)

    def test_create_and_see_only_own_work(self):
        WorkExperience.objects.create(user=self.other, company='Чужая', position='QA', start_date='2024-01-01')
        response = self.client.post('/api/ru/me/work/', {
            'company': 'Motion', 'position': 'Frontend', 'start_date': '2024-09-01',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.client.get('/api/ru/me/')
        self.assertEqual([work['company'] for work in response.data['work']], ['Motion'])

    def test_resume_is_read_from_me(self):
        work = WorkExperience.objects.create(user=self.user, company='Motion', position='QA', start_date='2024-01-01')
        self.assertEqual(self.client.get('/api/ru/me/work/').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.get(f'/api/ru/me/work/{work.id}/').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_edit_and_delete_own_work(self):
        work = WorkExperience.objects.create(user=self.user, company='Motion', position='QA', start_date='2024-01-01')
        response = self.client.patch(f'/api/ru/me/work/{work.id}/', {'position': 'Frontend'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['position'], 'Frontend')
        self.assertEqual(self.client.delete(f'/api/ru/me/work/{work.id}/').status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(WorkExperience.objects.filter(id=work.id).exists())

    def test_work_end_before_start(self):
        response = self.client.post('/api/ru/me/work/', {
            'company': 'Motion', 'position': 'Frontend', 'start_date': '2024-09-01', 'end_date': '2024-01-01',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('end_date', response.data)

    def test_cannot_edit_someone_elses_work(self):
        work = WorkExperience.objects.create(user=self.other, company='Чужая', position='QA', start_date='2024-01-01')
        response = self.client.patch(f'/api/ru/me/work/{work.id}/', {'company': 'Моя'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class MembersTests(MotionTestCase):
    def setUp(self):
        super().setUp()
        self.active = make_user('dev1', first_name='Азамат')
        self.inactive = make_user('dev2', user_status=StatusChoices.INACTIVE)
        self.admin = make_user('admin', role=RoleChoices.ADMIN)
        WorkExperience.objects.create(user=self.active, company='Motion', position='Frontend', start_date='2024-09-01')

    def test_public_list_shows_only_filled_profiles(self):
        response = self.client.get('/api/ru/members/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([member['id'] for member in response.data['results']], [self.active.id])

    def test_public_profile_has_resume(self):
        response = self.client.get(f'/api/ru/members/{self.active.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['work'][0]['company'], 'Motion')
        self.assertNotIn('role', response.data)


class UsersAdminTests(MotionTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user('admin', role=RoleChoices.ADMIN)
        self.member = make_user('dev1')

    def test_admin_creates_user_with_hashed_password(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/ru/users/', {'username': 'new', 'password': 'NewPass12345!'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = UserProfile.objects.get(username='new')
        self.assertTrue(user.check_password('NewPass12345!'))
        self.assertEqual(user.status, StatusChoices.INACTIVE)

    def test_member_cannot_use_users_api(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get('/api/ru/users/').status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_deletes_user_in_team(self):
        TeamMember.objects.create(team=Team.objects.create(name='Alpha'), user=self.member)
        self.client.force_authenticate(self.admin)
        response = self.client.delete(f'/api/ru/users/{self.member.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class RoleTests(MotionTestCase):
    def test_superuser_is_admin(self):
        user = UserProfile.objects.create_superuser('root', password='Pass12345!word')
        self.assertEqual(user.role, RoleChoices.ADMIN)

    def test_admin_role_opens_django_admin(self):
        user = make_user('boss', role=RoleChoices.ADMIN)
        self.assertTrue(user.is_staff and user.is_superuser)
        user.role = RoleChoices.MEMBER
        user.save()
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_django_admin_add_user_hashes_password(self):
        self.client.force_login(make_user('boss', role=RoleChoices.ADMIN))
        self.assertEqual(self.client.get('/admin/motion_app/userprofile/add/').status_code, 200)
        self.client.post('/admin/motion_app/userprofile/add/', {
            'username': 'fromadmin', 'usable_password': 'true',
            'password1': 'NewPass12345!', 'password2': 'NewPass12345!',
        })
        user = UserProfile.objects.get(username='fromadmin')
        self.assertTrue(user.check_password('NewPass12345!'))
        self.assertEqual(self.client.get(f'/admin/motion_app/userprofile/{user.id}/change/').status_code, 200)


# ---------- Команды ----------

class TeamTests(MotionTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user('admin', role=RoleChoices.ADMIN)
        self.member = make_user('dev1')
        self.team = Team.objects.create(name='Alpha')

    def test_list_needs_login(self):
        self.assertEqual(self.client.get('/api/ru/teams/').status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(self.member)
        response = self.client.get('/api/ru/teams/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['name'], 'Alpha')

    def test_only_admin_creates_team(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.post('/api/ru/teams/', {'name': 'Beta'}).status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post('/api/ru/teams/', {'name': 'Beta'}).status_code, status.HTTP_201_CREATED)

    def test_delete_team_keeps_projects(self):
        project = Project.objects.create(name='LMS', description='d', category='Web', team=self.team)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(f'/api/ru/teams/{self.team.id}/').status_code, status.HTTP_204_NO_CONTENT)
        project.refresh_from_db()
        self.assertIsNone(project.team)

    def test_detail_shows_member_names(self):
        TeamMember.objects.create(team=self.team, user=self.member)
        self.client.force_authenticate(self.member)
        response = self.client.get(f'/api/ru/teams/{self.team.id}/')
        self.assertEqual(response.data['members'][0]['user']['id'], self.member.id)
        self.assertIn('first_name', response.data['members'][0]['user'])


class TeamMemberTests(MotionTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user('admin', role=RoleChoices.ADMIN)
        self.lead = make_user('lead1')
        self.other_lead = make_user('lead2')
        self.member = make_user('dev1')
        self.outsider = make_user('dev2')
        self.team = Team.objects.create(name='Alpha')
        TeamMember.objects.create(team=self.team, user=self.lead, role=MemberRoleChoices.TEAM_LEAD)
        TeamMember.objects.create(team=self.team, user=self.other_lead, role=MemberRoleChoices.TEAM_LEAD)
        TeamMember.objects.create(team=self.team, user=self.member)
        self.url = f'/api/ru/teams/{self.team.id}/members/'

    def test_lead_adds_member(self):
        self.client.force_authenticate(self.lead)
        response = self.client.post(self.url, {'user_id': self.outsider.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user']['id'], self.outsider.id)

    def test_lead_cannot_add_team_lead(self):
        self.client.force_authenticate(self.lead)
        response = self.client.post(self.url, {'user_id': self.outsider.id, 'role': MemberRoleChoices.TEAM_LEAD})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_member_cannot_add(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.post(self.url, {'user_id': self.outsider.id}).status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_member(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(self.url, {'user_id': self.member.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('user_id', response.data)

    def test_team_not_found(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/ru/teams/9999/members/', {'user_id': self.outsider.id})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_lead_removes_member_but_not_lead(self):
        self.client.force_authenticate(self.lead)
        self.assertEqual(self.client.delete(f'{self.url}{self.other_lead.id}/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(f'{self.url}{self.member.id}/').status_code, status.HTTP_204_NO_CONTENT)

    def test_only_admin_changes_role(self):
        self.client.force_authenticate(self.lead)
        response = self.client.patch(f'{self.url}{self.member.id}/', {'role': MemberRoleChoices.TEAM_LEAD})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f'{self.url}{self.member.id}/', {'role': MemberRoleChoices.TEAM_LEAD})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['role'], MemberRoleChoices.TEAM_LEAD)


# ---------- Проекты ----------

class ProjectTests(MotionTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user('admin', role=RoleChoices.ADMIN)
        self.lead = make_user('lead1')
        self.member = make_user('dev1')
        self.team = Team.objects.create(name='Alpha')
        self.project = Project.objects.create(name='LMS', description='d', category='Web', team=self.team)
        ProjectMember.objects.create(project=self.project, user=self.lead, role=MemberRoleChoices.TEAM_LEAD)
        ProjectMember.objects.create(project=self.project, user=self.member)
        self.url = f'/api/ru/projects/{self.project.id}/'

    def test_anyone_sees_projects(self):
        response = self.client.get('/api/ru/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['team']['name'], 'Alpha')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['members']), 2)

    def test_admin_creates_project_with_team(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/ru/projects/', {
            'name': 'CRM', 'description': 'd', 'category': 'Web', 'team_id': self.team.id,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['team']['id'], self.team.id)

    def test_member_cannot_create(self):
        self.client.force_authenticate(self.lead)
        response = self.client.post('/api/ru/projects/', {'name': 'CRM', 'description': 'd', 'category': 'Web'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_lead_edits_own_project(self):
        self.client.force_authenticate(self.lead)
        response = self.client.patch(self.url, {'status': 'Completed'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'Completed')

    def test_member_and_foreign_lead_cannot_edit(self):
        other = Project.objects.create(name='Shop', description='d', category='Web')
        ProjectMember.objects.create(project=other, user=self.member, role=MemberRoleChoices.TEAM_LEAD)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.patch(self.url, {'name': 'X'}).status_code, status.HTTP_403_FORBIDDEN)

    def test_only_admin_deletes(self):
        self.client.force_authenticate(self.lead)
        self.assertEqual(self.client.delete(self.url).status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(self.url).status_code, status.HTTP_204_NO_CONTENT)

    def test_filter_by_status(self):
        Project.objects.create(name='Shop', description='d', category='Web', status='Paused')
        response = self.client.get('/api/ru/projects/', {'status': 'Paused'})
        self.assertEqual([project['name'] for project in response.data['results']], ['Shop'])


class ProjectMemberTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.url = f'/api/ru/projects/{self.project.id}/members/'

    def test_lead_adds_member(self):
        self.client.force_authenticate(self.lead)
        response = self.client.post(self.url, {'user_id': self.outsider.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_outsider_cannot_add(self):
        self.client.force_authenticate(self.outsider)
        response = self.client.post(self.url, {'user_id': self.outsider.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ---------- Задачи ----------

class TaskTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user('admin', role=RoleChoices.ADMIN)
        self.task = Task.objects.create(project=self.project, title='API уроков', assignee=self.member, author=self.lead)
        self.url = f'/api/ru/projects/{self.project.id}/tasks/'

    def test_only_project_members_see_tasks(self):
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.member)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['assignee']['id'], self.member.id)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)

    def test_member_creates_task(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(self.url, {'title': 'Вход через Google', 'assignee_id': self.other_member.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], TaskStatusChoices.TO_DO)
        self.assertEqual(response.data['author']['id'], self.member.id)
        self.assertEqual(response.data['assignee']['id'], self.other_member.id)

    def test_assignee_must_be_in_project(self):
        self.client.force_authenticate(self.lead)
        response = self.client.post(self.url, {'title': 'Вход через Google', 'assignee_id': self.outsider.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('assignee_id', response.data)

    def test_assignee_moves_own_task(self):
        self.client.force_authenticate(self.member)
        response = self.client.patch(f'{self.url}{self.task.id}/', {'status': TaskStatusChoices.IN_PROGRESS, 'order': 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], TaskStatusChoices.IN_PROGRESS)

    def test_member_cannot_edit_someone_elses_task(self):
        self.client.force_authenticate(self.other_member)
        response = self.client.patch(f'{self.url}{self.task.id}/', {'status': TaskStatusChoices.DONE})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.lead)
        response = self.client.patch(f'{self.url}{self.task.id}/', {'assignee_id': self.other_member.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_only_admin_or_lead_deletes(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.delete(f'{self.url}{self.task.id}/').status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.lead)
        self.assertEqual(self.client.delete(f'{self.url}{self.task.id}/').status_code, status.HTTP_204_NO_CONTENT)

    def test_task_from_another_project_not_found(self):
        other = Project.objects.create(name='Shop', description='d', category='Web')
        ProjectMember.objects.create(project=other, user=self.outsider)
        self.client.force_authenticate(self.outsider)
        response = self.client.get(f'/api/ru/projects/{other.id}/tasks/{self.task.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_filter_by_status(self):
        Task.objects.create(project=self.project, title='CI', status=TaskStatusChoices.DONE)
        self.client.force_authenticate(self.member)
        response = self.client.get(self.url, {'status': TaskStatusChoices.DONE})
        self.assertEqual([task['title'] for task in response.data['results']], ['CI'])

    def test_changes_go_to_history(self):
        self.member.first_name = 'Азамат'
        self.member.save()
        self.client.force_authenticate(self.lead)
        url = f'{self.url}{self.task.id}/'
        response = self.client.patch(
            url, {'status': TaskStatusChoices.REVIEW, 'assignee_id': self.other_member.id, 'order': 5}
        )
        self.assertEqual(
            [(item['field'], item['old_value'], item['new_value']) for item in response.data['history']],
            [('status', 'To_do', 'Review'), ('assignee', 'Азамат (@dev1)', 'dev2')],
        )
        self.assertEqual(response.data['history'][0]['user']['id'], self.lead.id)

        self.client.patch(url, {'status': TaskStatusChoices.REVIEW, 'labels': []}, format='json')
        self.assertEqual(TaskHistory.objects.count(), 2)

        response = self.client.patch(url, {'labels': [f'{i}' * 50 for i in range(10)]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['history'][-1]['new_value']), 255)

    def test_namesake_reassign_goes_to_history(self):
        namesake = make_user('dev4', first_name='Азамат')
        ProjectMember.objects.create(project=self.project, user=namesake)
        self.member.first_name = 'Азамат'
        self.member.save()
        self.client.force_authenticate(self.lead)
        self.client.patch(f'{self.url}{self.task.id}/', {'assignee_id': namesake.id})
        self.assertEqual(list(TaskHistory.objects.values_list('field', flat=True)), ['assignee'])

    def test_admin_site_changes_go_to_history(self):
        request = RequestFactory().post('/admin/')
        request.user = self.admin
        self.task.status = TaskStatusChoices.DONE
        self.task.assignee = self.other_member
        TaskAdmin(Task, site).save_model(request, self.task, None, True)
        self.assertEqual(
            list(TaskHistory.objects.values_list('field', 'user')),
            [('status', self.admin.id), ('assignee', self.admin.id)],
        )
        self.assertTrue(Notification.objects.filter(user=self.other_member).exists())

    def test_board_queries_do_not_grow(self):
        self.client.force_authenticate(self.member)
        card_url = f'{self.url}{self.task.id}/'

        def count(url, method='get'):
            self.client.force_authenticate(self.lead if method == 'patch' else self.member)
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(getattr(self.client, method)(url).status_code, status.HTTP_200_OK)
            return len(queries)

        def add_activity(times):
            for i in range(times):
                task = Task.objects.create(project=self.project, title=f'T{i}', assignee=self.other_member)
                comment = TaskComment.objects.create(task=self.task, author=self.other_member, text='x')
                TaskHistory.objects.create(task=self.task, user=self.lead, field='status')
                TaskAttachment.objects.create(task=self.task, author=self.lead, file='task_files/x.png', name='x.png')
                Notification.objects.create(
                    user=self.member, actor=self.other_member, task=task, comment=comment,
                    type=NotificationTypeChoices.COMMENT,
                )

        add_activity(1)
        project_url = f'/api/ru/projects/{self.project.id}/'
        board, card, notifications = count(self.url), count(card_url), count('/api/ru/me/notifications/')
        card_patch, project_patch = count(card_url, 'patch'), count(project_url, 'patch')
        add_activity(10)
        for user in (make_user('dev4'), make_user('dev5')):
            ProjectMember.objects.create(project=self.project, user=user)
        self.assertEqual(count(self.url), board)
        self.assertEqual(count(card_url), card)
        self.assertEqual(count('/api/ru/me/notifications/'), notifications)
        self.assertEqual(count(card_url, 'patch'), card_patch)
        self.assertEqual(count(project_url, 'patch'), project_patch)

    def test_type_and_labels(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(
            self.url, {'title': 'Падает вход', 'type': TaskTypeChoices.BUG, 'labels': ['backend', 'auth', 'backend']},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['labels'], ['backend', 'auth'])
        self.assertEqual(Task.objects.get(pk=self.task.pk).type, TaskTypeChoices.TASK)

        response = self.client.get(self.url, {'type': TaskTypeChoices.BUG, 'label': 'auth'})
        self.assertEqual([task['title'] for task in response.data['results']], ['Падает вход'])
        self.assertEqual(self.client.get(self.url, {'label': 'auth2'}).data['count'], 0)
        self.assertEqual(self.client.get(f'{self.url}labels/').data, ['auth', 'backend'])

    def test_labels_are_limited(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(self.url, {'title': 'X', 'labels': [f'l{i}' for i in range(11)]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(self.url, {'title': 'X', 'labels': ['a' * 51]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_outsider_cannot_see_labels(self):
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(f'{self.url}labels/').status_code, status.HTTP_403_FORBIDDEN)

    def test_labels_cannot_contain_commas(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(self.url, {'title': 'X', 'labels': ['ui, ux']}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_model_rejects_assignee_outside_project(self):
        Task(project=self.project, title='X', author=self.lead, assignee=self.member).full_clean()
        with self.assertRaises(ValidationError) as error:
            Task(project=self.project, title='X', author=self.lead, assignee=self.outsider).full_clean()
        self.assertEqual(list(error.exception.message_dict), ['assignee'])
        with self.assertRaises(ValidationError) as error:
            Task(project=self.project, title='X', author=self.lead, labels=[f'l{i}' for i in range(11)]).full_clean()
        self.assertEqual(list(error.exception.message_dict), ['labels'])

    def test_unchanged_assignee_can_be_sent_again(self):
        ProjectMember.objects.filter(user=self.member).delete()
        self.client.force_authenticate(self.lead)
        response = self.client.patch(f'{self.url}{self.task.id}/', {'assignee_id': self.member.id, 'title': 'X'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_ids_in_urls_must_be_numbers(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.patch('/api/ru/projects/abc/', {'name': 'X'}).status_code, 404)

    def test_my_tasks(self):
        other = Project.objects.create(name='Shop', description='d', category='Web')
        ProjectMember.objects.create(project=other, user=self.member)
        Task.objects.create(project=other, title='Корзина', assignee=self.member)
        left = Project.objects.create(name='Old', description='d', category='Web')
        Task.objects.create(project=left, title='Старая', assignee=self.member)
        Task.objects.create(project=self.project, title='Чужая', assignee=self.other_member)
        self.client.force_authenticate(self.member)
        response = self.client.get('/api/ru/me/tasks/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            sorted((task['title'], task['project']['name']) for task in response.data['results']),
            [('API уроков', 'LMS'), ('Корзина', 'Shop')],
        )


class TaskCommentTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.task = Task.objects.create(project=self.project, title='API уроков')
        self.url = f'/api/ru/projects/{self.project.id}/tasks/{self.task.id}/comments/'

    def test_member_comments_and_sees_it_in_task(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(self.url, {'text': 'Начал'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.client.get(f'/api/ru/projects/{self.project.id}/tasks/{self.task.id}/')
        self.assertEqual(response.data['comments'][0]['author']['id'], self.member.id)

    def test_comment_is_rolled_back_if_notifications_fail(self):
        self.client.force_authenticate(self.member)
        with mock.patch('motion_app.views.comment_created', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError), self.assertLogs('django.request', 'ERROR'):
                self.client.post(self.url, {'text': 'Начал'})
        self.assertFalse(TaskComment.objects.exists())

    def test_outsider_cannot_comment(self):
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.post(self.url, {'text': 'Привет'}).status_code, status.HTTP_403_FORBIDDEN)

    def test_only_author_edits_comment(self):
        comment = TaskComment.objects.create(task=self.task, author=self.member, text='Начал')
        self.client.force_authenticate(self.other_member)
        self.assertEqual(self.client.patch(f'{self.url}{comment.id}/', {'text': 'X'}).status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.patch(f'{self.url}{comment.id}/', {'text': 'Готово'}).status_code, status.HTTP_200_OK)

    def test_lead_deletes_someone_elses_comment(self):
        comment = TaskComment.objects.create(task=self.task, author=self.member, text='Начал')
        self.client.force_authenticate(self.other_member)
        self.assertEqual(self.client.delete(f'{self.url}{comment.id}/').status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.lead)
        self.assertEqual(self.client.delete(f'{self.url}{comment.id}/').status_code, status.HTTP_204_NO_CONTENT)


class TaskAttachmentTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.task = Task.objects.create(project=self.project, title='API уроков')
        self.task_url = f'/api/ru/projects/{self.project.id}/tasks/{self.task.id}/'
        self.url = f'{self.task_url}attachments/'

    def upload(self, name='screen.png'):
        return self.client.post(self.url, {'file': SimpleUploadedFile(name, b'data')}, format='multipart')

    def test_member_uploads_and_sees_it_in_task(self):
        self.client.force_authenticate(self.member)
        response = self.upload()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        attachment = self.client.get(self.task_url).data['attachments'][0]
        self.assertEqual(attachment['name'], 'screen.png')
        self.assertEqual(attachment['author']['id'], self.member.id)

    def test_file_link_is_signed_and_expires(self):
        self.client.force_authenticate(self.member)
        link = self.upload().data['file']
        self.assertIn('/api/ru/task-files/', link)
        self.client.force_authenticate(None)
        response = self.client.get(link)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(b''.join(response.streaming_content), b'data')
        self.assertIn('attachment', response['Content-Disposition'])

        tampered = link[:-2] + ('A' if link[-2] != 'A' else 'B') + '/'
        self.assertEqual(self.client.get(tampered).status_code, status.HTTP_404_NOT_FOUND)
        with mock.patch('motion_app.services.TASK_FILE_LINK_MAX_AGE', -1):
            self.assertEqual(self.client.get(link).status_code, status.HTTP_403_FORBIDDEN)

    def test_long_name_missing_file_and_admin_link(self):
        self.client.force_authenticate(self.member)
        response = self.upload('а' * 150 + '.pdf')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        attachment = TaskAttachment.objects.get(pk=response.data['id'])
        self.assertEqual(attachment.name, 'а' * 150 + '.pdf')
        self.assertIn('/api/ru/task-files/', TaskAttachmentInline(Task, site).download(attachment))

        os.remove(attachment.file.path)
        self.assertEqual(self.client.get(response.data['file']).status_code, status.HTTP_404_NOT_FOUND)

    def test_wrong_type_and_outsider(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.upload('page.html').status_code, status.HTTP_400_BAD_REQUEST)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.upload().status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_removes_file(self):
        self.client.force_authenticate(self.member)
        attachment = TaskAttachment.objects.get(pk=self.upload().data['id'])
        path = attachment.file.path
        self.client.force_authenticate(self.other_member)
        self.assertEqual(self.client.delete(f'{self.url}{attachment.id}/').status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.lead)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(f'{self.url}{attachment.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(os.path.exists(path))


class NotificationTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.url = f'/api/ru/projects/{self.project.id}/tasks/'

    def received(self, user):
        return list(Notification.objects.filter(user=user).values_list('type', flat=True))

    def test_assignee_is_notified(self):
        self.client.force_authenticate(self.lead)
        task_id = self.client.post(self.url, {'title': 'API', 'assignee_id': self.member.id}).data['id']
        self.client.post(self.url, {'title': 'Себе', 'assignee_id': self.lead.id})
        self.client.patch(f'{self.url}{task_id}/', {'assignee_id': self.other_member.id})
        self.client.patch(f'{self.url}{task_id}/', {'title': 'API уроков'})
        self.assertEqual(self.received(self.member), [NotificationTypeChoices.ASSIGNED])
        self.assertEqual(self.received(self.other_member), [NotificationTypeChoices.ASSIGNED])
        self.assertEqual(self.received(self.lead), [])

    def test_comment_and_mention(self):
        task = Task.objects.create(project=self.project, title='API', assignee=self.member, author=self.lead)
        self.client.force_authenticate(self.member)
        self.client.post(f'{self.url}{task.id}/comments/', {'text': '@dev2, @dev3 и @lead1. гляньте'})
        self.assertEqual(self.received(self.member), [])
        self.assertEqual(self.received(self.lead), [NotificationTypeChoices.MENTION])
        self.assertEqual(self.received(self.other_member), [NotificationTypeChoices.MENTION])
        self.assertEqual(self.received(self.outsider), [])

        self.client.post(f'{self.url}{task.id}/comments/', {'text': 'Пиши на support@dev2 или (@dev3)'})
        self.assertEqual(self.received(self.other_member), [NotificationTypeChoices.MENTION])

        self.client.force_authenticate(self.other_member)
        self.client.post(f'{self.url}{task.id}/comments/', {'text': 'Готово'})
        self.assertEqual(self.received(self.member), [NotificationTypeChoices.COMMENT])
        self.assertEqual(
            self.received(self.lead),
            [NotificationTypeChoices.COMMENT, NotificationTypeChoices.COMMENT, NotificationTypeChoices.MENTION],
        )

    def test_removed_member_loses_tasks_and_comments(self):
        task = Task.objects.create(project=self.project, title='API', assignee=self.member, author=self.member)
        self.client.force_authenticate(self.lead)
        self.client.delete(f'/api/ru/projects/{self.project.id}/members/{self.member.id}/')
        task.refresh_from_db()
        self.assertIsNone(task.assignee)
        self.assertEqual(
            list(TaskHistory.objects.values_list('field', 'old_value', 'new_value', 'user')),
            [('assignee', 'dev1', '', self.lead.id)],
        )
        self.client.post(f'{self.url}{task.id}/comments/', {'text': 'бюджет 500k'})
        self.assertEqual(self.received(self.member), [])
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get('/api/ru/me/tasks/').data['count'], 0)

    def test_my_notifications(self):
        task = Task.objects.create(project=self.project, title='API')
        mine = Notification.objects.create(user=self.member, actor=self.lead, task=task, type=NotificationTypeChoices.ASSIGNED)
        Notification.objects.create(user=self.member, actor=self.lead, task=task, type=NotificationTypeChoices.COMMENT)
        others = Notification.objects.create(user=self.lead, task=task, type=NotificationTypeChoices.COMMENT)

        self.client.force_authenticate(self.member)
        response = self.client.get('/api/ru/me/notifications/', {'is_read': 'false'})
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][1]['task']['project']['id'], self.project.id)

        response = self.client.patch(f'/api/ru/me/notifications/{mine.id}/', {'is_read': True, 'type': 'Mention'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['type'], NotificationTypeChoices.ASSIGNED)
        self.assertEqual(self.client.get('/api/ru/me/notifications/', {'is_read': 'false'}).data['count'], 1)
        self.assertEqual(self.client.patch(f'/api/ru/me/notifications/{others.id}/', {'is_read': True}).status_code, 404)

        self.assertEqual(self.client.post('/api/ru/me/notifications/read-all/').data, {'updated': 1})
        others.refresh_from_db()
        self.assertFalse(others.is_read)


# ---------- Заявки клиентов ----------

REQUEST_DATA = {
    'name': 'Марат', 'company': 'ТОО Финтех', 'email': 'marat@fintech.kg', 'phone': '+996700123456',
    'title': 'CRM', 'description': 'Нужен CRM', 'project_type': 'CRM',
}


class ClientRequestTests(MotionTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user('admin', role=RoleChoices.ADMIN)
        self.member = make_user('dev1')

    def test_anyone_sends_request_and_cannot_set_status(self):
        response = self.client.post('/api/ru/client-requests/', {**REQUEST_DATA, 'status': ClientStatusChoices.ACCEPTED})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ClientRequest.objects.get().status, ClientStatusChoices.NEW)

    def test_only_admin_reads_requests(self):
        self.assertEqual(self.client.get('/api/ru/client-requests/').status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get('/api/ru/client-requests/').status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get('/api/ru/client-requests/').status_code, status.HTTP_200_OK)

    def test_admin_changes_status(self):
        request = ClientRequest.objects.create(**REQUEST_DATA)
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f'/api/ru/client-requests/{request.id}/', {'status': ClientStatusChoices.ACCEPTED})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_makes_project_from_request(self):
        request = ClientRequest.objects.create(**REQUEST_DATA)
        url = f'/api/ru/client-requests/{request.id}/project/'
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.post(url).status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.admin)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual((response.data['name'], response.data['category']), ('CRM', 'CRM'))
        request.refresh_from_db()
        self.assertEqual(request.status, ClientStatusChoices.ACCEPTED)
        self.assertEqual(request.project_id, response.data['id'])
        self.assertEqual(self.client.get(f'/api/ru/client-requests/{request.id}/').data['project']['name'], 'CRM')

        self.assertEqual(self.client.post(url).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Project.objects.count(), 1)

    def test_project_from_request_keeps_russian_description(self):
        request = ClientRequest.objects.create(**REQUEST_DATA)
        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/en/client-requests/{request.id}/project/')
        self.assertEqual(Project.objects.get(pk=response.data['id']).description_ru, 'Нужен CRM')

    def test_rejected_request_cannot_become_project(self):
        request = ClientRequest.objects.create(status=ClientStatusChoices.REJECTED, **REQUEST_DATA)
        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/ru/client-requests/{request.id}/project/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        request.refresh_from_db()
        self.assertEqual(request.status, ClientStatusChoices.REJECTED)
        self.assertFalse(Project.objects.exists())

    def test_requests_are_limited(self):
        for _ in range(10):
            self.client.post('/api/ru/client-requests/', REQUEST_DATA)
        response = self.client.post('/api/ru/client-requests/', REQUEST_DATA)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


# ---------- Статистика и справочники ----------

class StatsTests(MotionTestCase):
    def test_stats_count_only_real_things(self):
        make_user('dev1')
        make_user('dev2', user_status=StatusChoices.INACTIVE)
        make_user('admin', role=RoleChoices.ADMIN)
        data = {
            'name': 'n', 'email': 'a@b.kg', 'phone': '+996700123456',
            'title': 't', 'description': 'd', 'project_type': 'p',
        }
        ClientRequest.objects.create(company='Финтех', status=ClientStatusChoices.ACCEPTED, **data)
        ClientRequest.objects.create(company='Спам', **data)

        response = self.client.get('/api/ru/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['members_count'], 1)
        self.assertEqual(response.data['companies_count'], 1)


class ChoicesTests(MotionTestCase):
    def test_choices(self):
        response = self.client.get('/api/ru/choices/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn({'value': 'UI_UX_Designer', 'label': 'UI/UX Designer'}, response.data['positions'])


class HealthTests(MotionTestCase):
    def test_health(self):
        response = self.client.get('/api/ru/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'status': 'ok'})


class ThrottleTests(MotionTestCase):
    def test_anonymous_requests_are_limited(self):
        for _ in range(120):
            self.client.get('/api/ru/choices/')
        self.assertEqual(self.client.get('/api/ru/choices/').status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class DocsTests(MotionTestCase):
    def test_swagger_works(self):
        response = self.client.get('/api/docs.json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('/api/{lang}/teams/', response.json()['paths'])
        self.assertEqual(self.client.get('/api/docs/').status_code, status.HTTP_200_OK)

    def test_every_operation_has_section_and_unique_name(self):
        paths = self.client.get('/api/docs.json').json()['paths']
        operations = [operation for item in paths.values() for method, operation in item.items() if method != 'parameters']
        summaries = [operation['summary'] for operation in operations]
        self.assertEqual(len(summaries), len(set(summaries)))
        for operation in operations:
            self.assertIn(operation['tags'][0], TAG_NAMES.values())
            self.assertNotIn('_', operation['summary'])


class LanguageTests(MotionTestCase):
    def test_language_from_url(self):
        project = Project.objects.create(
            name='LMS', category='Web', description_ru='Платформа', description_en='Platform'
        )
        response = self.client.get(f'/api/en/projects/{project.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Language'], 'en')
        self.assertEqual(response.data['description'], 'Platform')
        response = self.client.get(f'/api/ru/projects/{project.id}/')
        self.assertEqual(response.data['description'], 'Платформа')

    def test_language_does_not_leak_between_requests(self):
        self.client.get('/api/en/choices/')
        self.assertContains(self.client.get('/admin/login/'), 'lang="ru"')

    def test_english_falls_back_to_russian(self):
        project = Project.objects.create(name='LMS', category='Web', description_ru='Платформа')
        response = self.client.get(f'/api/en/projects/{project.id}/')
        self.assertEqual(response.data['description'], 'Платформа')
