"""
forensic_project/urls.py — Main URL configuration
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import home

admin.site.enable_nav_sidebar = False

urlpatterns = [
    # Home (requires login + approval)
    path('', home, name='home'),

    # Django admin
    path('admin/', admin.site.urls),

    # Auth + user management (login, logout, register, admin panel)
    path('', include('accounts.urls')),

    # API
    path('api/', include('cases.urls')),
    path('api/evidence/', include('evidence.urls')),
    path('api/reconstruction/', include('reconstruction.urls')),
    path('api/', include('reconstruction.urls')),

    # Django-template views
    path('cases/',         include('cases.urls')),
    path('evidence/',      include('evidence.urls')),
    path('reconstruction/', include('reconstruction.urls')),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
