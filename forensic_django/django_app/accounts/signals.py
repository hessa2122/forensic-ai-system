from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from accounts.models import AuditLog, UserProfile
from cases.models import Case
from evidence.models import Evidence


def _actor(instance):
    return getattr(instance, 'created_by', None) or getattr(instance, 'uploaded_by', None) or getattr(instance, 'user', None)


def _log(instance, action):
    AuditLog.objects.create(
        user=_actor(instance),
        action=action,
        model_name=instance.__class__.__name__,
        object_id=str(instance.pk or ''),
        target=str(instance),
        details=f'{action.title()} {instance.__class__.__name__}',
    )


@receiver(post_save, sender=Case)
@receiver(post_save, sender=Evidence)
@receiver(post_save, sender=UserProfile)
def log_model_save(sender, instance, created, **kwargs):
    _log(instance, 'create' if created else 'update')


@receiver(post_delete, sender=Case)
@receiver(post_delete, sender=Evidence)
@receiver(post_delete, sender=UserProfile)
def log_model_delete(sender, instance, **kwargs):
    _log(instance, 'delete')
