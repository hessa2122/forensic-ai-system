from django.utils import timezone

from .models import Notification


def create_notification(user, message, notification_type='system', related_object=None):
    if user is None:
        return None
    related_type = ''
    related_id = ''
    if related_object is not None:
        related_type = related_object.__class__.__name__
        related_id = str(getattr(related_object, 'pk', '') or '')
    return Notification.objects.create(
        user=user,
        message=message,
        notification_type=notification_type,
        related_object_type=related_type,
        related_object_id=related_id,
    )


def mark_notification_read(notification):
    notification.is_read = True
    notification.read_at = timezone.now()
    notification.save(update_fields=['is_read', 'read_at'])
    return notification
