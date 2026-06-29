"""
accounts/models.py
Extended user model with roles, profile and audit trail.
"""
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin',        'Admin'),
        ('investigator', 'Investigator'),
        ('analyst',      'Analyst'),
    ]

    user         = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role         = models.CharField(max_length=20, choices=ROLE_CHOICES, default='investigator')
    department   = models.CharField(max_length=100, blank=True)
    phone        = models.CharField(max_length=20, blank=True)
    badge_number = models.CharField(max_length=50, blank=True)
    is_approved  = models.BooleanField(default=False)   # Admin must approve new users
    approved_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='approved_users')
    approved_at  = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)
    last_active  = models.DateTimeField(null=True, blank=True)
    notes        = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def display_role(self):
        return dict(self.ROLE_CHOICES).get(self.role, self.role)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Auto-create profile when a new User is created."""
    if created:
        UserProfile.objects.get_or_create(user=instance)


class AuditLog(models.Model):
    """System-level audit trail for admin monitoring."""
    ACTION_CHOICES = [
        ('create',          'Create'),
        ('update',          'Update'),
        ('delete',          'Delete'),
        ('login',           'User Login'),
        ('logout',          'User Logout'),
        ('register',        'User Registered'),
        ('approved',        'User Approved'),
        ('role_changed',    'Role Changed'),
        ('case_created',    'Case Created'),
        ('case_updated',    'Case Updated'),
        ('case_deleted',    'Case Deleted'),
        ('evidence_upload', 'Evidence Uploaded'),
        ('evidence_delete', 'Evidence Deleted'),
        ('analysis_run',    'Analysis Run'),
        ('request_submitted', 'Analysis Request Submitted'),
        ('request_approved', 'Analysis Request Approved'),
        ('request_rejected', 'Analysis Request Rejected'),
        ('reconstruction_run', 'Reconstruction Run'),
        ('report_generated', 'Report Generated'),
        ('report_download', 'Report Downloaded'),
        ('backup_created', 'Backup Created'),
    ]

    user       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action     = models.CharField(max_length=30, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100, blank=True, default='')
    object_id  = models.CharField(max_length=100, blank=True, default='')
    target     = models.CharField(max_length=200, blank=True)   # e.g. "Case #CASE-001"
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    details    = models.TextField(blank=True)
    timestamp  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user} | {self.action} | {self.timestamp:%Y-%m-%d %H:%M}"


def log_action(user, action, target='', details='', request=None):
    """Helper to write an audit log entry."""
    ip = None
    if request:
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')
    AuditLog.objects.create(user=user, action=action, target=target,
                            model_name=target.split(' #')[0] if target else '',
                            ip_address=ip, details=details)


class SystemSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['key']

    def __str__(self):
        return self.key


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('user', 'User'),
        ('case', 'Case'),
        ('analysis', 'Analysis'),
        ('reconstruction', 'Reconstruction'),
        ('report', 'Report'),
        ('backup', 'Backup'),
        ('system', 'System'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES, default='system')
    related_object_type = models.CharField(max_length=80, blank=True, default='')
    related_object_id = models.CharField(max_length=80, blank=True, default='')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user}: {self.notification_type}"


class BackupRecord(models.Model):
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    filename = models.CharField(max_length=500)
    database_engine = models.CharField(max_length=120)
    size_bytes = models.BigIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64, blank=True, default='')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success')
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.filename
