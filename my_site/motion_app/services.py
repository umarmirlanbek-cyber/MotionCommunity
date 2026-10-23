import re

from django.core.signing import TimestampSigner

from .choices import NotificationTypeChoices
from .models import UserProfile, TaskHistory, Notification

TASK_HISTORY_FIELDS = ('title', 'status', 'priority', 'type', 'labels', 'assignee', 'due_date')
MENTION_RE = re.compile(r'@([\w.+-]+)')
TASK_FILE_LINK_MAX_AGE = 60 * 60
task_file_signer = TimestampSigner(salt='task-file')


def history_value(task, field):
    value = getattr(task, field)
    if value is None:
        return ''
    if field == 'labels':
        value = ', '.join(value)
    return str(value)[:255]


def notify(users, actor, task, notification_type, comment=None):
    actor_id = actor.id if actor else None
    recipients = {user.id: user for user in users if user and user.id != actor_id}
    Notification.objects.bulk_create([
        Notification(user=user, actor=actor, task=task, type=notification_type, comment=comment)
        for user in recipients.values()
    ])


def task_created(task, actor):
    notify([task.assignee], actor, task, NotificationTypeChoices.ASSIGNED)


def task_changed(old, task, actor):
    TaskHistory.objects.bulk_create([
        TaskHistory(task=task, user=actor, field=field, old_value=old_value, new_value=new_value)
        for field in TASK_HISTORY_FIELDS
        if (old_value := history_value(old, field)) != (new_value := history_value(task, field))
    ])
    if task.assignee_id != old.assignee_id:
        notify([task.assignee], actor, task, NotificationTypeChoices.ASSIGNED)


def comment_created(comment):
    task = comment.task
    names = {name.rstrip('.') for name in MENTION_RE.findall(comment.text)}
    mentioned = list(UserProfile.objects.filter(username__in=names, project_memberships__project_id=task.project_id))
    notify(mentioned, comment.author, task, NotificationTypeChoices.MENTION, comment)
    others = [user for user in (task.assignee, task.author) if user not in mentioned]
    notify(others, comment.author, task, NotificationTypeChoices.COMMENT, comment)


def task_file_token(attachment):
    return task_file_signer.sign(str(attachment.pk))


def task_file_id(token):
    return int(task_file_signer.unsign(token, max_age=TASK_FILE_LINK_MAX_AGE))
