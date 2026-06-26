from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.static import serve

from .views import landing_page


admin.site.enable_nav_sidebar = False
admin.site.site_header = "ForensicAI Administration"
admin.site.site_title = "ForensicAI Admin"
admin.site.index_title = "Forensic Control Center"


urlpatterns = [
    # Public landing page
    path("", landing_page, name="landing_page"),

    # Django admin
    path("admin/", admin.site.urls),

    # Login, register, logout and dashboard
    path("", include("accounts.urls")),

    # API URLs
    path("api/", include("cases.urls")),
    path("api/evidence/", include("evidence.urls")),
    path("api/reconstruction/", include("reconstruction.urls")),

    # Web page URLs
    path("cases/", include("cases.urls")),
    path("evidence/", include("evidence.urls")),
    path("reconstruction/", include("reconstruction.urls")),
]


if settings.DEBUG or getattr(settings, "SERVE_MEDIA_FILES", False):
    if settings.DEBUG:
        urlpatterns += static(
            settings.MEDIA_URL,
            document_root=settings.MEDIA_ROOT,
        )
    else:
        urlpatterns += [
            path(
                "media/<path:path>",
                serve,
                {"document_root": settings.MEDIA_ROOT},
            ),
        ]
