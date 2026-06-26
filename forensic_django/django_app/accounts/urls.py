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

    # API
    path(
        "api/admin/user-stats/",
        views.api_admin_user_stats,
        name="api_admin_user_stats",
    ),
]