from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from .choices import RoleChoices, StatusChoices, MemberRoleChoices, ClientStatusChoices, TaskStatusChoices
from .models import (
    UserProfile, WorkExperience, Team, TeamMember, Project, ProjectMember, Task, TaskComment, ClientRequest
)


def make_user(username, role=RoleChoices.MEMBER, user_status=StatusChoices.ACTIVE, **kwargs):
    return UserProfile.objects.create_user(
        username=username, password='Pass12345!word', role=role, status=user_status, **kwargs
    )


class AuthTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user('dev1')

    def test_login_returns_tokens_and_user(self):
        response = self.client.post('/api/ru/auth/login/', {'username': 'dev1', 'password': 'Pass12345!word'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertEqual(response.data['user']['username'], 'dev1')

    def test_login_wrong_password(self):
        response = self.client.post('/api/ru/auth/login/', {'username': 'dev1', 'password': 'wrong'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_is_limited(self):
        for _ in range(10):
            self.client.post('/api/ru/auth/login/', {'username': 'dev1', 'password': 'wrong'})
        response = self.client.post('/api/ru/auth/login/', {'username': 'dev1', 'password': 'wrong'})
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class MeTests(APITestCase):
    def setUp(self):
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


class ResumeTests(APITestCase):
    def setUp(self):
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


class MembersTests(APITestCase):
    def setUp(self):
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


class UsersAdminTests(APITestCase):
    def setUp(self):
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


class RoleTests(APITestCase):
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

class TeamTests(APITestCase):
    def setUp(self):
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


class TeamMemberTests(APITestCase):
    def setUp(self):
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

class ProjectTests(APITestCase):
    def setUp(self):
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


class ProjectMemberTests(APITestCase):
    def setUp(self):
        self.lead = make_user('lead1')
        self.outsider = make_user('dev2')
        self.project = Project.objects.create(name='LMS', description='d', category='Web')
        ProjectMember.objects.create(project=self.project, user=self.lead, role=MemberRoleChoices.TEAM_LEAD)
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

class TaskTests(APITestCase):
    def setUp(self):
        self.admin = make_user('admin', role=RoleChoices.ADMIN)
        self.lead = make_user('lead1')
        self.member = make_user('dev1')
        self.other_member = make_user('dev2')
        self.outsider = make_user('dev3')
        self.project = Project.objects.create(name='LMS', description='d', category='Web')
        ProjectMember.objects.create(project=self.project, user=self.lead, role=MemberRoleChoices.TEAM_LEAD)
        ProjectMember.objects.create(project=self.project, user=self.member)
        ProjectMember.objects.create(project=self.project, user=self.other_member)
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

    def test_my_tasks(self):
        other = Project.objects.create(name='Shop', description='d', category='Web')
        Task.objects.create(project=other, title='Корзина', assignee=self.member)
        Task.objects.create(project=self.project, title='Чужая', assignee=self.other_member)
        self.client.force_authenticate(self.member)
        response = self.client.get('/api/ru/me/tasks/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            sorted((task['title'], task['project']['name']) for task in response.data['results']),
            [('API уроков', 'LMS'), ('Корзина', 'Shop')],
        )


class TaskCommentTests(APITestCase):
    def setUp(self):
        self.lead = make_user('lead1')
        self.member = make_user('dev1')
        self.other_member = make_user('dev2')
        self.outsider = make_user('dev3')
        self.project = Project.objects.create(name='LMS', description='d', category='Web')
        ProjectMember.objects.create(project=self.project, user=self.lead, role=MemberRoleChoices.TEAM_LEAD)
        ProjectMember.objects.create(project=self.project, user=self.member)
        ProjectMember.objects.create(project=self.project, user=self.other_member)
        self.task = Task.objects.create(project=self.project, title='API уроков')
        self.url = f'/api/ru/projects/{self.project.id}/tasks/{self.task.id}/comments/'

    def test_member_comments_and_sees_it_in_task(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(self.url, {'text': 'Начал'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.client.get(f'/api/ru/projects/{self.project.id}/tasks/{self.task.id}/')
        self.assertEqual(response.data['comments'][0]['author']['id'], self.member.id)

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


# ---------- Заявки клиентов ----------

REQUEST_DATA = {
    'name': 'Марат', 'company': 'ТОО Финтех', 'email': 'marat@fintech.kg', 'phone': '+996700123456',
    'title': 'CRM', 'description': 'Нужен CRM', 'project_type': 'CRM',
}


class ClientRequestTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.admin = UserProfile.objects.create_user('admin', password='Pass12345!word', role=RoleChoices.ADMIN)
        self.member = UserProfile.objects.create_user('dev1', password='Pass12345!word')

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

    def test_requests_are_limited(self):
        for _ in range(10):
            self.client.post('/api/ru/client-requests/', REQUEST_DATA)
        response = self.client.post('/api/ru/client-requests/', REQUEST_DATA)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


# ---------- Статистика и справочники ----------

class StatsTests(APITestCase):
    def test_stats_count_only_real_things(self):
        UserProfile.objects.create_user('dev1', status=StatusChoices.ACTIVE)
        UserProfile.objects.create_user('dev2', status=StatusChoices.INACTIVE)
        UserProfile.objects.create_user('admin', role=RoleChoices.ADMIN, status=StatusChoices.ACTIVE)
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


class ChoicesTests(APITestCase):
    def test_choices(self):
        response = self.client.get('/api/ru/choices/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn({'value': 'UI_UX_Designer', 'label': 'UI/UX Designer'}, response.data['positions'])


class HealthTests(APITestCase):
    def test_health(self):
        response = self.client.get('/api/ru/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'status': 'ok'})


class DocsTests(APITestCase):
    def test_swagger_works(self):
        response = self.client.get('/api/docs.json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('/api/{lang}/teams/', response.json()['paths'])
        self.assertEqual(self.client.get('/api/docs/').status_code, status.HTTP_200_OK)


class LanguageTests(APITestCase):
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

    def test_english_falls_back_to_russian(self):
        project = Project.objects.create(name='LMS', category='Web', description_ru='Платформа')
        response = self.client.get(f'/api/en/projects/{project.id}/')
        self.assertEqual(response.data['description'], 'Платформа')
