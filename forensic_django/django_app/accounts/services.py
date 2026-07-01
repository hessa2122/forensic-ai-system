from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Notification


def _safe_action_url(action_url):
    if not action_url:
        return ''
    if url_has_allowed_host_and_scheme(action_url, allowed_hosts=None, require_https=False):
        return ''
    return action_url if str(action_url).startswith('/') and not str(action_url).startswith('//') else ''


def create_notification(user, message, notification_type='system', related_object=None, title='', priority='normal', action_url=''):
    if user is None:
        return None
    related_type = ''
    related_id = ''
    if related_object is not None:
        related_type = related_object.__class__.__name__
        related_id = str(getattr(related_object, 'pk', '') or '')
    return Notification.objects.create(
        user=user,
        title=title or message[:120],
        message=message,
        notification_type=notification_type,
        priority=priority,
        related_object_type=related_type,
        related_object_id=related_id,
        action_url=_safe_action_url(action_url),
    )


def notify_user(user, *args, **kwargs):
    return create_notification(user, *args, **kwargs)


def notify_admins(message, notification_type='system', related_object=None, title='', priority='normal', action_url=''):
    notifications = []
    admins = User.objects.filter(is_active=True).filter(is_staff=True) | User.objects.filter(is_active=True, is_superuser=True)
    for user in admins.distinct():
        notifications.append(create_notification(user, message, notification_type, related_object, title, priority, action_url))
    return notifications


def notify_case_members(case, message, notification_type='case', related_object=None, title='', priority='normal', action_url=''):
    users = []
    if getattr(case, 'assigned_to', None):
        users.append(case.assigned_to)
    if getattr(case, 'created_by', None) and getattr(case.created_by, 'is_staff', False):
        users.append(case.created_by)
    seen = set()
    created = []
    for user in users:
        if user and user.id not in seen:
            seen.add(user.id)
            created.append(create_notification(user, message, notification_type, related_object, title, priority, action_url))
    return created


def broadcast_notification(users, message, notification_type='system', title='', priority='normal', action_url=''):
    created = []
    with transaction.atomic():
        for user in users:
            created.append(create_notification(user, message, notification_type, None, title, priority, action_url))
    return created


def mark_notification_read(notification):
    notification.is_read = True
    notification.read_at = timezone.now()
    notification.save(update_fields=['is_read', 'read_at'])
    return notification


def mark_all_notifications_read(user):
    now = timezone.now()
    return Notification.objects.filter(user=user, is_read=False).update(is_read=True, read_at=now)
