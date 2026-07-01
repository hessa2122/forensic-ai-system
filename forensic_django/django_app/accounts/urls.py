"""
accounts/urls.py
"""

from django.urls import path
from . import views


urlpatterns = [
    # Authentication
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),

    # Normal user dashboard
    path("dashboard/", views.home, name="home"),

    # Admin user management
    path(
        "admin-panel/users/",
        views.admin_users,
        name="admin_users",
    ),
    path(
        "admin-panel/users/<int:user_id>/",
        views.admin_user_detail,
        name="admin_user_detail",
    ),
    path(
        "admin-panel/users/<int:user_id>/approve/",
        views.admin_approve_user,
        name="admin_approve_user",
    ),
    path(
        "admin-panel/users/<int:user_id>/revoke/",
        views.admin_revoke_user,
        name="admin_revoke_user",
    ),
    path(
        "admin-panel/users/<int:user_id>/delete/",
        views.admin_delete_user,
        name="admin_delete_user",
    ),
    path(
        "admin-panel/audit-log/",
        views.admin_audit_log,
        name="admin_audit_log",
    ),
    path("notifications/", views.notifications_page, name="notifications_page"),
    path("api/notifications/unread-count/", views.api_unread_count, name="api_unread_count"),
    path("notifications/<int:notification_id>/read/", views.notification_read, name="notification_read"),
    path("notifications/read-all/", views.notifications_read_all, name="notifications_read_all"),
    path("notifications/<int:notification_id>/delete/", views.notification_delete, name="notification_delete"),
    path("admin-panel/notifications/send/", views.admin_send_notification, name="admin_send_notification"),

    # API
    path(
        "api/admin/user-stats/",
        views.api_admin_user_stats,
        name="api_admin_user_stats",
    ),
]
