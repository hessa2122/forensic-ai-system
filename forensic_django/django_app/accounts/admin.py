"""
accounts/admin.py
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.core.management import call_command
from django.contrib import messages

from .models import AuditLog, BackupRecord, Notification, SystemSetting, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    fk_name = 'user'
    can_delete = False
    extra = 0
    fields = ('role', 'department', 'phone', 'badge_number', 'is_approved')


try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ('username', 'email', 'role', 'department', 'is_approved', 'created_at')
    list_editable = ('role',)
    list_filter   = ('role', 'is_approved')
    search_fields = ('user__username', 'user__email', 'department', 'badge_number')
    readonly_fields = ('created_at', 'updated_at', 'last_active')
    actions = ['approve_users']

    def username(self, obj):
        return obj.user.username

    def email(self, obj):
        return obj.user.email

    def approve_users(self, request, queryset):
        from django.utils import timezone
        queryset.update(is_approved=True, approved_by=request.user, approved_at=timezone.now())
    approve_users.short_description = 'Approve selected users'


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display  = ('timestamp', 'user', 'action', 'model_name', 'object_id', 'target')
    list_filter   = ('action', 'timestamp')
    search_fields = ('user__username', 'model_name', 'target', 'details')
    readonly_fields = ('user', 'action', 'model_name', 'object_id', 'target', 'ip_address',
                       'details', 'timestamp')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'description')
    search_fields = ('key', 'description')
    actions = ['run_database_backup']

    def run_database_backup(self, request, queryset):
        call_command('create_forensic_backup', created_by=request.user.pk)
        self.message_user(request, 'Database backup created.', messages.SUCCESS)
    run_database_backup.short_description = 'Run database backup'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'notification_type', 'is_read', 'related_object_type', 'related_object_id')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('user__username', 'message', 'related_object_type', 'related_object_id')


@admin.register(BackupRecord)
class BackupRecordAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'filename', 'database_engine', 'size_bytes', 'status', 'created_by')
    list_filter = ('status', 'database_engine', 'created_at')
    search_fields = ('filename', 'checksum_sha256', 'error_message')
    readonly_fields = ('filename', 'database_engine', 'size_bytes', 'checksum_sha256', 'created_by', 'status', 'error_message', 'created_at')
