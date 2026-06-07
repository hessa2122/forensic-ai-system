from django.urls import path
from .views import CaseListView, CaseDetailView, StatsView
from . import views
from .report_views import download_case_report


urlpatterns = [
    path("cases/",          CaseListView.as_view(),   name="case-list"),
    path("cases/<int:pk>/", CaseDetailView.as_view(), name="case-detail"),
    path("stats/",          StatsView.as_view(),      name="stats"),
    path('cases/<int:case_id>/report/', download_case_report, name='case_report'),
]

