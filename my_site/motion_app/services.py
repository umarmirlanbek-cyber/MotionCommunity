import re

from django.core.signing import TimestampSigner
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import get_language
from rest_framework.exceptions import ValidationError

from .choices import RoleChoices, NotificationTypeChoices
from .models import UserProfile, ProjectMember, Task, TaskHistory, Notification

TASK_HISTORY_FIELDS = ('title', 'status', 'priority', 'type', 'labels', 'assignee', 'due_date')
MENTION_RE = re.compile(r'(?<!\w)@([\w.+-]+)')
MAX_MENTIONS = 50
TASK_FILE_LINK_MAX_AGE = 60 * 60
task_file_signer = TimestampSigner(salt='task-file')


def history_value(task, field):
    value = getattr(task, field)
    if value is None:
        return ''
    if field == 'labels':
        value = ', '.join(value)
    elif field == 'assignee' and str(value) != value.username:
        value = f'{value} (@{value.username})'
    return str(value)[:255]


def compared_value(task, field):
    return getattr(task, 'assignee_id' if field == 'assignee' else field)


def notify(users, actor, task, notification_type, comment=None):
    actor_id = actor.id if actor else None
    recipients = {user.id: user for user in users if user and user.is_active and user.id != actor_id}
    Notification.objects.bulk_create([
        Notification(user=user, actor=actor, task=task, type=notification_type, comment=comment)
        for user in recipients.values()
    ])


def task_created(task, actor):
    notify([task.assignee], actor, task, NotificationTypeChoices.ASSIGNED)


def task_changed(old, task, actor):
    TaskHistory.objects.bulk_create([
        TaskHistory(
            task=task, user=actor, field=field,
            old_value=history_value(old, field), new_value=history_value(task, field),
        )
        for field in TASK_HISTORY_FIELDS
        if compared_value(old, field) != compared_value(task, field)
    ])
    if task.assignee_id != old.assignee_id:
        notify([task.assignee], actor, task, NotificationTypeChoices.ASSIGNED)


def comment_created(comment):
    task = comment.task
    names = list(dict.fromkeys(name.rstrip('.') for name in MENTION_RE.findall(comment.text)))[:MAX_MENTIONS]
    mentioned = list(UserProfile.objects.filter(username__in=names, project_memberships__project_id=task.project_id))
    notify(mentioned, comment.author, task, NotificationTypeChoices.MENTION, comment)
    member_ids = set(ProjectMember.objects.filter(
        project_id=task.project_id, user_id__in=[task.assignee_id, task.author_id]
    ).values_list('user_id', flat=True))
    others = [
        user for user in (task.assignee, task.author)
        if user and user.id in member_ids and user not in mentioned
    ]
    notify(others, comment.author, task, NotificationTypeChoices.COMMENT, comment)


def visible_notifications(user_id):
    return Notification.objects.filter(user_id=user_id, task__project__members__user_id=user_id)


def member_removed(member, actor):
    Notification.objects.filter(user_id=member.user_id, task__project_id=member.project_id).delete()
    tasks = list(
        Task.objects.filter(project_id=member.project_id, assignee_id=member.user_id).select_related('assignee')
    )
    if not tasks:
        return
    Task.objects.filter(pk__in=[task.pk for task in tasks]).update(assignee=None, updated_at=timezone.now())
    old_value = history_value(tasks[0], 'assignee')
    TaskHistory.objects.bulk_create([
        TaskHistory(task=task, user=actor, field='assignee', old_value=old_value, new_value='') for task in tasks
    ])


LAST_ADMIN_ERROR = 'Нельзя удалить или понизить последнего Admin'


def leaves_no_admin(users, lock=False):
    if not any(user.role == RoleChoices.ADMIN for user in users):
        return False
    admins = UserProfile.objects.filter(role=RoleChoices.ADMIN, is_active=True).order_by('pk')
    if lock:
        admins = admins.select_for_update()
    removed = {user.pk for user in users}
    return not [pk for pk in admins.values_list('pk', flat=True) if pk not in removed]


def check_not_last_admin(user):
    if leaves_no_admin([user], lock=True):
        raise ValidationError({'detail': LAST_ADMIN_ERROR})


def task_file_url(attachment):
    return reverse('task-file', kwargs={'lang': get_language(), 'token': task_file_signer.sign(str(attachment.pk))})


def task_file_id(token):
    return int(task_file_signer.unsign(token, max_age=TASK_FILE_LINK_MAX_AGE))
